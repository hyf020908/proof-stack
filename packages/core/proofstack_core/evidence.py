"""Public generation and verification API for ProofStack evidence bundles."""

from __future__ import annotations

import os
import re
import shutil
import tempfile
import zipfile
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from .evidence_report import build_report, build_summary
from .evidence_types import (
    BUNDLE_FORMAT,
    CHECKSUMMED_FILES,
    JSON_ARTIFACTS,
    REQUIRED_FILES,
    SCHEMA_VERSION,
    EvidenceArtifact,
    EvidenceBundleError,
    EvidenceBundlePayload,
    EvidenceBundleResult,
    EvidenceVerificationResult,
    VerificationIssue,
    json_bytes,
    sha256_bytes,
    sha256_file,
    utc_timestamp,
)
from .evidence_verify import EvidenceBundleVerifier, verify_evidence_bundle
from .redaction import redact_data


def _mapping_value(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(key, default)
    return default


class EvidenceBundleGenerator:
    """Build complete, redacted evidence bundles through an atomic directory swap."""

    def __init__(self, *, tool_version: str = "0.1.0") -> None:
        if re.fullmatch(r"[0-9A-Za-z][0-9A-Za-z.+-]{0,63}", tool_version) is None:
            raise EvidenceBundleError("tool version contains invalid characters")
        self.tool_version = tool_version

    def generate(
        self,
        output_directory: str | Path,
        payload: EvidenceBundlePayload | Mapping[str, Any],
        *,
        generated_at: datetime | None = None,
        known_secrets: tuple[str, ...] = (),
    ) -> EvidenceBundleResult:
        """Generate a new bundle without overwriting an existing path."""

        if not isinstance(payload, EvidenceBundlePayload):
            payload = EvidenceBundlePayload.from_mapping(payload)
        destination = Path(output_directory)
        if destination.exists() or destination.is_symlink():
            raise EvidenceBundleError(f"output path already exists: {destination}")
        parent = destination.parent
        parent.mkdir(parents=True, exist_ok=True)
        if not parent.is_dir():
            raise EvidenceBundleError(f"output parent is not a directory: {parent}")

        generated_text = utc_timestamp(generated_at)
        raw_payload: dict[str, Any] = {
            "analysis": payload.analysis,
            "changed_files": payload.changed_files,
            "requirements": payload.requirements,
            "dependency_graph": payload.dependency_graph,
            "findings": payload.findings,
            "test_results": payload.test_results,
            "policy_decisions": payload.policy_decisions,
            "audit_events": payload.audit_events,
            "input_summary": payload.input_summary,
        }
        redacted = redact_data(raw_payload, known_secrets=known_secrets)
        if not isinstance(redacted, dict):
            raise EvidenceBundleError("redacted evidence payload must be an object")
        cleaned = cast(dict[str, Any], redacted)

        staging = Path(tempfile.mkdtemp(prefix=f".{destination.name}-", dir=parent))
        artifacts: list[EvidenceArtifact] = []
        manifest: dict[str, Any] = {}
        checksums: dict[str, str] = {}
        try:
            for filename, field_name in JSON_ARTIFACTS.items():
                wrapped = {"schema_version": SCHEMA_VERSION, field_name: cleaned[field_name]}
                artifacts.append(self._write(staging, filename, json_bytes(wrapped)))
            artifacts.append(
                self._write(
                    staging,
                    "summary.md",
                    build_summary(cleaned, generated_text).encode("utf-8"),
                )
            )
            artifacts.append(
                self._write(
                    staging,
                    "report.html",
                    build_report(cleaned, generated_text, SCHEMA_VERSION).encode("utf-8"),
                )
            )

            analysis = cleaned["analysis"]
            manifest = {
                "schema_version": SCHEMA_VERSION,
                "bundle_format": BUNDLE_FORMAT,
                "tool": {"name": "ProofStack", "version": self.tool_version},
                "generated_at": generated_text,
                "analysis_id": _mapping_value(
                    analysis, "id", _mapping_value(analysis, "analysis_id", None)
                ),
                "input_summary": cleaned["input_summary"],
                "input_sha256": sha256_bytes(json_bytes(cleaned["input_summary"])),
                "artifacts": [
                    artifact.to_dict() for artifact in sorted(artifacts, key=lambda item: item.name)
                ],
            }
            artifacts.append(self._write(staging, "manifest.json", json_bytes(manifest)))
            checksums = {
                artifact.name: artifact.sha256
                for artifact in sorted(artifacts, key=lambda item: item.name)
            }
            checksum_text = "".join(
                f"{digest}  {name}\n" for name, digest in sorted(checksums.items())
            )
            self._write(staging, "checksums.sha256", checksum_text.encode("ascii"))
            os.replace(staging, destination)
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise

        return EvidenceBundleResult(
            path=destination,
            manifest=manifest,
            checksums=checksums,
            artifacts=tuple(sorted(artifacts, key=lambda artifact: artifact.name)),
        )

    build = generate

    @staticmethod
    def _write(directory: Path, name: str, content: bytes) -> EvidenceArtifact:
        path = directory / name
        path.write_bytes(content)
        content_types = {
            ".json": "application/json",
            ".md": "text/markdown; charset=utf-8",
            ".html": "text/html; charset=utf-8",
            ".sha256": "text/plain; charset=us-ascii",
        }
        return EvidenceArtifact(
            name=name,
            content_type=content_types.get(path.suffix, "application/octet-stream"),
            sha256=sha256_bytes(content),
            size=len(content),
        )

    def create_zip(
        self,
        bundle_directory: str | Path,
        destination: str | Path | None = None,
    ) -> Path:
        """Create a deterministic flat ZIP after verifying the source bundle."""

        bundle = Path(bundle_directory)
        EvidenceBundleVerifier().verify(bundle).raise_for_errors()
        archive_path = Path(destination) if destination is not None else bundle.with_suffix(".zip")
        if archive_path.exists() or archive_path.is_symlink():
            raise EvidenceBundleError(f"archive path already exists: {archive_path}")
        if archive_path.resolve().is_relative_to(bundle.resolve()):
            raise EvidenceBundleError("archive destination must be outside the bundle directory")
        archive_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with zipfile.ZipFile(
                archive_path, mode="x", compression=zipfile.ZIP_DEFLATED, compresslevel=9
            ) as archive:
                for name in sorted(REQUIRED_FILES):
                    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                    info.compress_type = zipfile.ZIP_DEFLATED
                    info.external_attr = 0o100644 << 16
                    archive.writestr(info, (bundle / name).read_bytes())
            EvidenceBundleVerifier().verify(archive_path).raise_for_errors()
        except Exception:
            if archive_path.exists() and archive_path.is_file():
                archive_path.unlink()
            raise
        return archive_path


__all__ = [
    "BUNDLE_FORMAT",
    "CHECKSUMMED_FILES",
    "JSON_ARTIFACTS",
    "REQUIRED_FILES",
    "SCHEMA_VERSION",
    "EvidenceArtifact",
    "EvidenceBundleError",
    "EvidenceBundleGenerator",
    "EvidenceBundlePayload",
    "EvidenceBundleResult",
    "EvidenceBundleVerifier",
    "EvidenceVerificationResult",
    "VerificationIssue",
    "sha256_bytes",
    "sha256_file",
    "verify_evidence_bundle",
]
