"""Shared constants and value objects for ProofStack evidence bundles."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "1.0"
BUNDLE_FORMAT = "proofstack-evidence"

JSON_ARTIFACTS: dict[str, str] = {
    "analysis.json": "analysis",
    "changed-files.json": "changed_files",
    "requirements.json": "requirements",
    "dependency-graph.json": "dependency_graph",
    "findings.json": "findings",
    "test-results.json": "test_results",
    "policy-decisions.json": "policy_decisions",
    "audit-events.json": "audit_events",
}

REQUIRED_FILES = frozenset(
    {
        "manifest.json",
        "summary.md",
        *JSON_ARTIFACTS,
        "checksums.sha256",
        "report.html",
    }
)
CHECKSUMMED_FILES = REQUIRED_FILES - {"checksums.sha256"}


class EvidenceBundleError(ValueError):
    """Raised when an evidence bundle cannot be generated or verified."""


@dataclass(slots=True)
class EvidenceBundlePayload:
    """Structured inputs used to build all evidence artifacts."""

    analysis: Any
    changed_files: Any = field(default_factory=list)
    requirements: Any = field(default_factory=list)
    dependency_graph: Any = field(default_factory=lambda: {"nodes": [], "edges": []})
    findings: Any = field(default_factory=list)
    test_results: Any = field(default_factory=list)
    policy_decisions: Any = field(default_factory=list)
    audit_events: Any = field(default_factory=list)
    input_summary: Any = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> EvidenceBundlePayload:
        """Create a payload while rejecting misspelled artifact names."""

        allowed = set(cls.__dataclass_fields__)
        unknown = sorted(set(value) - allowed)
        if unknown:
            raise EvidenceBundleError(f"unknown evidence fields: {', '.join(unknown)}")
        if "analysis" not in value:
            raise EvidenceBundleError("the analysis field is required")
        return cls(
            analysis=value["analysis"],
            changed_files=value.get("changed_files", []),
            requirements=value.get("requirements", []),
            dependency_graph=value.get("dependency_graph", {"nodes": [], "edges": []}),
            findings=value.get("findings", []),
            test_results=value.get("test_results", []),
            policy_decisions=value.get("policy_decisions", []),
            audit_events=value.get("audit_events", []),
            input_summary=value.get("input_summary", {}),
        )


@dataclass(frozen=True, slots=True)
class EvidenceArtifact:
    """Metadata for one generated bundle file."""

    name: str
    content_type: str
    sha256: str
    size: int

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible representation."""

        return {
            "name": self.name,
            "content_type": self.content_type,
            "sha256": self.sha256,
            "size": self.size,
        }


@dataclass(frozen=True, slots=True)
class EvidenceBundleResult:
    """Result of an atomic evidence bundle build."""

    path: Path
    manifest: dict[str, Any]
    checksums: dict[str, str]
    artifacts: tuple[EvidenceArtifact, ...]


@dataclass(frozen=True, slots=True)
class VerificationIssue:
    """A machine-readable evidence verification failure."""

    code: str
    message: str
    file: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible representation."""

        result: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.file is not None:
            result["file"] = self.file
        return result


@dataclass(frozen=True, slots=True)
class EvidenceVerificationResult:
    """Verification status for a directory or ZIP evidence bundle."""

    valid: bool
    source: Path
    verified_files: tuple[str, ...]
    checksums: dict[str, str]
    issues: tuple[VerificationIssue, ...]
    manifest: dict[str, Any] | None = None

    def raise_for_errors(self) -> None:
        """Raise one concise error when verification did not succeed."""

        if not self.valid:
            detail = "; ".join(issue.message for issue in self.issues[:3])
            raise EvidenceBundleError(f"evidence verification failed: {detail}")

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible representation."""

        return {
            "valid": self.valid,
            "source": str(self.source),
            "verified_files": list(self.verified_files),
            "checksums": dict(self.checksums),
            "issues": [issue.to_dict() for issue in self.issues],
            "manifest": self.manifest,
        }


def sha256_bytes(content: bytes) -> str:
    """Return a lowercase SHA-256 digest for exact artifact bytes."""

    return hashlib.sha256(content).hexdigest()


def sha256_file(path: str | Path, *, chunk_size: int = 65_536) -> str:
    """Hash a regular file without loading the entire artifact into memory."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def json_bytes(value: Any) -> bytes:
    """Encode canonical, human-readable JSON with a final newline."""

    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n"
    ).encode("utf-8")


def utc_timestamp(value: datetime | None) -> str:
    """Normalize a timestamp as an RFC 3339 UTC string."""

    timestamp = value or datetime.now(UTC)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=UTC)
    return timestamp.astimezone(UTC).isoformat().replace("+00:00", "Z")
