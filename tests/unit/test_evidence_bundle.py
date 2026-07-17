from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from proofstack_core.evidence import (
    CHECKSUMMED_FILES,
    REQUIRED_FILES,
    SCHEMA_VERSION,
    EvidenceBundleError,
    EvidenceBundleGenerator,
    EvidenceBundlePayload,
    EvidenceBundleVerifier,
)


def _payload() -> EvidenceBundlePayload:
    return EvidenceBundlePayload(
        analysis={"id": "run-123", "verdict": "warn", "risk_score": 42},
        changed_files=[{"path": "src/service.py", "additions": 7, "deletions": 2}],
        requirements=[{"id": "REQ-1", "coverage": 0.8}],
        dependency_graph={"nodes": [{"id": "service.run"}], "edges": []},
        findings=[
            {
                "severity": "high",
                "category": "security",
                "title": "Unsafe process invocation",
                "file_path": "src/service.py",
            }
        ],
        test_results=[{"command": ["pytest"], "status": "passed", "duration_ms": 21}],
        policy_decisions=[
            {"rule_id": "test-evidence", "outcome": "warn", "explanation": "Coverage is low."}
        ],
        audit_events=[{"action": "analysis.completed", "resource_id": "run-123"}],
        input_summary={"source_type": "upload", "sha256": "a" * 64},
    )


def test_generator_creates_complete_verifiable_bundle(tmp_path: Path) -> None:
    bundle = tmp_path / "evidence-bundle"
    generated = EvidenceBundleGenerator().generate(
        bundle,
        _payload(),
        generated_at=datetime(2025, 1, 2, 3, 4, tzinfo=UTC),
    )

    assert {path.name for path in bundle.iterdir()} == REQUIRED_FILES
    assert set(generated.checksums) == CHECKSUMMED_FILES
    for filename in ["manifest.json", "analysis.json", "changed-files.json"]:
        content = json.loads((bundle / filename).read_text(encoding="utf-8"))
        assert content["schema_version"] == SCHEMA_VERSION
    assert "WARN" in (bundle / "summary.md").read_text(encoding="utf-8")
    assert "requires no network access" in (bundle / "report.html").read_text(encoding="utf-8")

    verification = EvidenceBundleVerifier().verify(bundle)
    assert verification.valid, verification.issues
    assert set(verification.verified_files) == CHECKSUMMED_FILES
    assert verification.manifest is not None
    assert verification.manifest["analysis_id"] == "run-123"


def test_bundle_output_is_stable_for_fixed_time(tmp_path: Path) -> None:
    timestamp = datetime(2025, 1, 2, 3, 4, tzinfo=UTC)
    first = EvidenceBundleGenerator().generate(tmp_path / "one", _payload(), generated_at=timestamp)
    second = EvidenceBundleGenerator().generate(
        tmp_path / "two", _payload(), generated_at=timestamp
    )

    assert first.checksums == second.checksums
    assert (first.path / "checksums.sha256").read_bytes() == (
        second.path / "checksums.sha256"
    ).read_bytes()


def test_zip_round_trip_and_tamper_detection(tmp_path: Path) -> None:
    generator = EvidenceBundleGenerator()
    result = generator.generate(tmp_path / "bundle", _payload())
    archive = generator.create_zip(result.path)

    assert EvidenceBundleVerifier().verify(archive).valid
    findings_path = result.path / "findings.json"
    findings_path.write_text("{}\n", encoding="utf-8")
    verification = EvidenceBundleVerifier().verify(result.path)
    assert not verification.valid
    assert any(issue.code == "checksum_mismatch" for issue in verification.issues)


def test_generator_refuses_to_overwrite(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    marker = bundle / "keep.txt"
    marker.write_text("user data", encoding="utf-8")

    with pytest.raises(EvidenceBundleError, match="already exists"):
        EvidenceBundleGenerator().generate(bundle, _payload())
    assert marker.read_text(encoding="utf-8") == "user data"
