from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest
from proofstack_core.evidence import (
    EvidenceBundleGenerator,
    EvidenceBundlePayload,
    EvidenceBundleVerifier,
)
from proofstack_core.redaction import REDACTED, redact_data, redact_text


def test_recursive_redaction_does_not_mutate_input() -> None:
    original = {
        "password": "correct horse battery staple",
        "nested": {
            "authorization": "Bearer abcdefghijklmnopqrstuvwxyz",
            "url": "postgresql://service:database-password@db/proofstack",
        },
        "clientSecret": "camel-case-secret",
    }

    cleaned = redact_data(original)

    assert cleaned["password"] == REDACTED
    assert cleaned["nested"]["authorization"] == REDACTED
    assert cleaned["nested"]["url"] == "postgresql://[REDACTED]@db/proofstack"
    assert cleaned["clientSecret"] == REDACTED
    assert original["password"] == "correct horse battery staple"


@pytest.mark.parametrize(
    "value",
    [
        "token=super-secret-value",
        "Authorization: Bearer abcdefghijklmnopqrstuvwxyz",
        "AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE",
        "github=ghp_abcdefghijklmnopqrstuvwxyz123456",
        "key=sk-abcdefghijklmnopqrstuvwxyz",
        'token="secret value with spaces"',
    ],
)
def test_text_redaction_removes_recognized_credential(value: str) -> None:
    assert value not in redact_text(value)
    assert REDACTED in redact_text(value)


def test_bundle_redacts_structured_and_unstructured_secrets(tmp_path: Path) -> None:
    known_secret = "opaque-credential-that-patterns-cannot-guess"
    payload = EvidenceBundlePayload(
        analysis={"id": "run-secret", "verdict": "fail", "risk_score": 90},
        findings=[
            {
                "title": "Credential found",
                "evidence": {
                    "api_key": "sk-abcdefghijklmnopqrstuvwxyz",
                    "stdout": f"token=super-secret-value and {known_secret}",
                },
            }
        ],
        input_summary={"github_token": "ghp_abcdefghijklmnopqrstuvwxyz123456"},
    )
    result = EvidenceBundleGenerator().generate(
        tmp_path / "bundle", payload, known_secrets=(known_secret,)
    )

    combined = b"\n".join(path.read_bytes() for path in result.path.iterdir())
    assert b"super-secret-value" not in combined
    assert b"opaque-credential-that-patterns-cannot-guess" not in combined
    assert b"sk-abcdefghijklmnopqrstuvwxyz" not in combined
    assert b"ghp_abcdefghijklmnopqrstuvwxyz123456" not in combined
    assert EvidenceBundleVerifier().verify(result.path).valid


def test_verifier_rejects_archive_traversal_without_extracting(tmp_path: Path) -> None:
    archive_path = tmp_path / "hostile.zip"
    escaped = tmp_path / "escaped.txt"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("../escaped.txt", "must not escape")
        archive.writestr("manifest.json", json.dumps({"schema_version": "1.0"}))

    result = EvidenceBundleVerifier().verify(archive_path)

    assert not result.valid
    assert not escaped.exists()
    assert any(issue.code == "unsafe_archive_entry" for issue in result.issues)
