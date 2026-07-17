"""Focused authentication, token, role, and redaction tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi import HTTPException
from proofstack_api.auth import decode_token, hash_password, verify_password
from proofstack_shared.config import Settings
from proofstack_shared.enums import Role
from proofstack_shared.security import has_minimum_role, redact_text


def test_password_hash_is_salted_and_verifiable() -> None:
    first = hash_password("a-secure-passphrase")
    second = hash_password("a-secure-passphrase")
    assert first != second
    assert verify_password("a-secure-passphrase", first)
    assert not verify_password("incorrect-passphrase", first)


def test_expired_and_wrong_type_tokens_are_rejected() -> None:
    settings = Settings()
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": "user",
            "org": "organization",
            "type": "refresh",
            "iat": now - timedelta(minutes=2),
            "exp": now - timedelta(minutes=1),
        },
        settings.secret_key.get_secret_value(),
        algorithm="HS256",
    )
    with pytest.raises(HTTPException):
        decode_token(token, "refresh", settings)


def test_role_hierarchy_and_redaction() -> None:
    assert has_minimum_role(Role.OWNER, Role.MAINTAINER)
    assert has_minimum_role(Role.REVIEWER, Role.VIEWER)
    assert not has_minimum_role(Role.VIEWER, Role.REVIEWER)
    redacted = redact_text("Authorization: Bearer super-secret-token-value password=hunter22")
    assert "super-secret-token-value" not in redacted
    assert "hunter22" not in redacted
