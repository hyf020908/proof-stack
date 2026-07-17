"""Hostile-input-safe verification for ProofStack evidence bundles."""

from __future__ import annotations

import json
import re
import stat
import zipfile
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any, cast

from .evidence_types import (
    BUNDLE_FORMAT,
    CHECKSUMMED_FILES,
    JSON_ARTIFACTS,
    REQUIRED_FILES,
    SCHEMA_VERSION,
    EvidenceBundleError,
    EvidenceVerificationResult,
    VerificationIssue,
    sha256_bytes,
)
from .redaction import contains_high_confidence_secret


class EvidenceBundleVerifier:
    """Verify bundle shape, hashes, schemas, redaction, and ZIP safety."""

    def __init__(
        self,
        *,
        max_bundle_bytes: int = 100 * 1024 * 1024,
        max_compression_ratio: int = 200,
    ) -> None:
        if max_bundle_bytes <= 0 or max_compression_ratio <= 0:
            raise ValueError("evidence verification limits must be positive")
        self.max_bundle_bytes = max_bundle_bytes
        self.max_compression_ratio = max_compression_ratio

    def verify(self, source: str | Path) -> EvidenceVerificationResult:
        """Verify an evidence directory or ZIP without extracting untrusted archives."""

        path = Path(source)
        issues: list[VerificationIssue] = []
        try:
            if path.is_symlink():
                raise EvidenceBundleError("bundle source must not be a symbolic link")
            if path.is_dir():
                files = self._read_directory(path, issues)
            elif path.is_file() and path.suffix.lower() == ".zip":
                files = self._read_zip(path, issues)
            else:
                raise EvidenceBundleError("bundle source must be a directory or .zip file")
        except (EvidenceBundleError, OSError, RuntimeError, ValueError, zipfile.BadZipFile) as exc:
            issues.append(VerificationIssue("source_error", str(exc)))
            return EvidenceVerificationResult(False, path, (), {}, tuple(issues))
        return self._verify_files(path, files, issues)

    def _read_directory(self, directory: Path, issues: list[VerificationIssue]) -> dict[str, bytes]:
        files: dict[str, bytes] = {}
        entries = list(directory.iterdir())
        names = {entry.name for entry in entries}
        self._check_file_set(names, issues)
        total = 0
        for entry in entries:
            if entry.name not in REQUIRED_FILES:
                continue
            if entry.is_symlink() or not entry.is_file():
                issues.append(
                    VerificationIssue(
                        "unsafe_file", "Bundle entries must be regular files.", entry.name
                    )
                )
                continue
            total += entry.stat().st_size
            if total > self.max_bundle_bytes:
                raise EvidenceBundleError("bundle exceeds the configured size limit")
            files[entry.name] = entry.read_bytes()
        return files

    def _read_zip(self, archive_path: Path, issues: list[VerificationIssue]) -> dict[str, bytes]:
        if archive_path.stat().st_size > self.max_bundle_bytes:
            raise EvidenceBundleError("ZIP exceeds the configured size limit")
        files: dict[str, bytes] = {}
        with zipfile.ZipFile(archive_path) as archive:
            infos = archive.infolist()
            if len(infos) > len(REQUIRED_FILES) + 8:
                raise EvidenceBundleError("ZIP contains too many entries")
            names: set[str] = set()
            total = 0
            for info in infos:
                pure_name = PurePosixPath(info.filename)
                unsafe_name = (
                    pure_name.is_absolute()
                    or ".." in pure_name.parts
                    or len(pure_name.parts) != 1
                    or "\\" in info.filename
                    or "\x00" in info.filename
                    or not info.filename
                )
                mode = info.external_attr >> 16
                if unsafe_name or stat.S_ISLNK(mode) or info.is_dir():
                    issues.append(
                        VerificationIssue(
                            "unsafe_archive_entry",
                            "ZIP entry has an unsafe path or type.",
                            info.filename,
                        )
                    )
                    continue
                if info.flag_bits & 0x1:
                    issues.append(
                        VerificationIssue(
                            "encrypted_archive_entry",
                            "Encrypted ZIP entries are not accepted.",
                            info.filename,
                        )
                    )
                    continue
                if info.filename in names:
                    issues.append(
                        VerificationIssue(
                            "duplicate_archive_entry",
                            "ZIP entry name is duplicated.",
                            info.filename,
                        )
                    )
                    continue
                names.add(info.filename)
                total += info.file_size
                if total > self.max_bundle_bytes:
                    raise EvidenceBundleError("uncompressed ZIP exceeds the configured size limit")
                compressed = max(1, info.compress_size)
                if info.file_size / compressed > self.max_compression_ratio:
                    issues.append(
                        VerificationIssue(
                            "suspicious_compression",
                            "ZIP entry exceeds the compression-ratio limit.",
                            info.filename,
                        )
                    )
                    continue
                if info.filename in REQUIRED_FILES:
                    files[info.filename] = archive.read(info)
            self._check_file_set(names, issues)
        return files

    @staticmethod
    def _check_file_set(names: set[str], issues: list[VerificationIssue]) -> None:
        for name in sorted(REQUIRED_FILES - names):
            issues.append(VerificationIssue("missing_file", "Required file is missing.", name))
        for name in sorted(names - REQUIRED_FILES):
            issues.append(VerificationIssue("unexpected_file", "Unexpected file is present.", name))

    def _verify_files(
        self,
        source: Path,
        files: dict[str, bytes],
        issues: list[VerificationIssue],
    ) -> EvidenceVerificationResult:
        checksums = self._parse_checksums(files.get("checksums.sha256"), issues)
        self._verify_checksum_file_set(checksums, issues)

        verified: list[str] = []
        for name in sorted(CHECKSUMMED_FILES):
            content = files.get(name)
            expected = checksums.get(name)
            if content is None or expected is None:
                continue
            observed = sha256_bytes(content)
            if observed != expected:
                issues.append(
                    VerificationIssue("checksum_mismatch", "SHA-256 checksum does not match.", name)
                )
            else:
                verified.append(name)

        parsed_json: dict[str, dict[str, Any]] = {}
        for name in ("manifest.json", *JSON_ARTIFACTS):
            content = files.get(name)
            if content is None:
                continue
            try:
                decoded: Any = json.loads(content)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                issues.append(VerificationIssue("invalid_json", f"Invalid JSON: {exc}.", name))
                continue
            if not isinstance(decoded, dict):
                issues.append(
                    VerificationIssue("invalid_schema", "JSON root must be an object.", name)
                )
                continue
            value = cast(dict[str, Any], decoded)
            parsed_json[name] = value
            if value.get("schema_version") != SCHEMA_VERSION:
                issues.append(
                    VerificationIssue(
                        "schema_version_mismatch",
                        f"Expected schema version {SCHEMA_VERSION}.",
                        name,
                    )
                )
            expected_root = JSON_ARTIFACTS.get(name)
            if expected_root is not None and expected_root not in value:
                issues.append(
                    VerificationIssue(
                        "invalid_schema", f"JSON root must include '{expected_root}'.", name
                    )
                )

        manifest = parsed_json.get("manifest.json")
        if manifest is not None:
            self._verify_manifest(manifest, files, issues)
        for name, content in files.items():
            if name == "checksums.sha256":
                continue
            text = content.decode("utf-8", errors="replace")
            if contains_high_confidence_secret(text):
                issues.append(
                    VerificationIssue(
                        "secret_exposure",
                        "A high-confidence secret pattern remains in the bundle.",
                        name,
                    )
                )

        return EvidenceVerificationResult(
            valid=not issues,
            source=source,
            verified_files=tuple(verified),
            checksums=checksums,
            issues=tuple(issues),
            manifest=manifest,
        )

    @staticmethod
    def _verify_checksum_file_set(
        checksums: Mapping[str, str], issues: list[VerificationIssue]
    ) -> None:
        missing = CHECKSUMMED_FILES - set(checksums)
        extra = set(checksums) - CHECKSUMMED_FILES
        if missing:
            issues.append(
                VerificationIssue(
                    "checksum_entries_missing",
                    f"Checksum index omits: {', '.join(sorted(missing))}.",
                    "checksums.sha256",
                )
            )
        if extra:
            issues.append(
                VerificationIssue(
                    "checksum_entries_unexpected",
                    f"Checksum index includes unexpected names: {', '.join(sorted(extra))}.",
                    "checksums.sha256",
                )
            )

    @staticmethod
    def _parse_checksums(content: bytes | None, issues: list[VerificationIssue]) -> dict[str, str]:
        if content is None:
            return {}
        try:
            text = content.decode("ascii")
        except UnicodeDecodeError:
            issues.append(
                VerificationIssue(
                    "invalid_checksum_index", "Checksum index must be ASCII.", "checksums.sha256"
                )
            )
            return {}
        checksums: dict[str, str] = {}
        pattern = re.compile(r"^([0-9a-f]{64})  ([A-Za-z0-9][A-Za-z0-9.-]*)$")
        for line_number, line in enumerate(text.splitlines(), start=1):
            match = pattern.fullmatch(line)
            if match is None:
                issues.append(
                    VerificationIssue(
                        "invalid_checksum_line",
                        f"Checksum line {line_number} is malformed.",
                        "checksums.sha256",
                    )
                )
                continue
            digest, name = match.groups()
            if name in checksums:
                issues.append(
                    VerificationIssue(
                        "duplicate_checksum",
                        f"Checksum for {name} is duplicated.",
                        "checksums.sha256",
                    )
                )
                continue
            checksums[name] = digest
        return checksums

    @staticmethod
    def _verify_manifest(
        manifest: Mapping[str, Any],
        files: Mapping[str, bytes],
        issues: list[VerificationIssue],
    ) -> None:
        if manifest.get("bundle_format") != BUNDLE_FORMAT:
            issues.append(
                VerificationIssue(
                    "bundle_format_mismatch",
                    "Manifest bundle format is not recognized.",
                    "manifest.json",
                )
            )
        tool = manifest.get("tool")
        if (
            not isinstance(tool, Mapping)
            or tool.get("name") != "ProofStack"
            or not isinstance(tool.get("version"), str)
            or not isinstance(manifest.get("generated_at"), str)
            or not isinstance(manifest.get("input_sha256"), str)
        ):
            issues.append(
                VerificationIssue(
                    "invalid_manifest", "Manifest metadata is incomplete.", "manifest.json"
                )
            )
        artifacts = manifest.get("artifacts")
        if not isinstance(artifacts, list):
            issues.append(
                VerificationIssue(
                    "invalid_manifest", "Manifest artifacts must be a list.", "manifest.json"
                )
            )
            return
        expected_names = CHECKSUMMED_FILES - {"manifest.json"}
        observed_names: set[str] = set()
        for artifact in artifacts:
            if not isinstance(artifact, Mapping):
                issues.append(
                    VerificationIssue(
                        "invalid_manifest_artifact",
                        "Manifest artifact entries must be objects.",
                        "manifest.json",
                    )
                )
                continue
            name = artifact.get("name")
            if not isinstance(name, str) or name not in expected_names:
                issues.append(
                    VerificationIssue(
                        "invalid_manifest_artifact",
                        "Manifest references an unknown artifact.",
                        "manifest.json",
                    )
                )
                continue
            if name in observed_names:
                issues.append(
                    VerificationIssue(
                        "duplicate_manifest_artifact",
                        "Manifest references an artifact more than once.",
                        name,
                    )
                )
                continue
            observed_names.add(name)
            content = files.get(name)
            if content is None:
                continue
            metadata_valid = (
                artifact.get("sha256") == sha256_bytes(content)
                and artifact.get("size") == len(content)
                and isinstance(artifact.get("content_type"), str)
            )
            if not metadata_valid:
                issues.append(
                    VerificationIssue(
                        "manifest_artifact_mismatch",
                        "Manifest metadata does not match the artifact.",
                        name,
                    )
                )
        if observed_names != expected_names:
            issues.append(
                VerificationIssue(
                    "manifest_artifacts_incomplete",
                    "Manifest does not enumerate every payload artifact exactly once.",
                    "manifest.json",
                )
            )


def verify_evidence_bundle(source: str | Path) -> EvidenceVerificationResult:
    """Convenience wrapper around the default evidence verifier."""

    return EvidenceBundleVerifier().verify(source)


__all__ = ["EvidenceBundleVerifier", "verify_evidence_bundle"]
