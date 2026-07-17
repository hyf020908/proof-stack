"""Password hashing, JWT issuance, and tenant-aware authorization dependencies."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from proofstack_shared.config import Settings, get_settings
from proofstack_shared.enums import Role
from proofstack_shared.security import has_minimum_role
from sqlalchemy import select
from sqlalchemy.orm import Session

from proofstack_api.database import get_db
from proofstack_api.models import User

password_hasher = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=2)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, encoded: str) -> bool:
    try:
        return password_hasher.verify(encoded, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def _create_token(user: User, token_type: str, ttl_seconds: int, settings: Settings) -> str:
    issued_at = datetime.now(UTC)
    payload = {
        "sub": user.id,
        "org": user.organization_id,
        "role": user.role.value,
        "type": token_type,
        "iat": issued_at,
        "exp": issued_at + timedelta(seconds=ttl_seconds),
        "jti": str(uuid4()),
    }
    return jwt.encode(payload, settings.secret_key.get_secret_value(), algorithm="HS256")


def create_token_pair(user: User, settings: Settings) -> tuple[str, str]:
    return (
        _create_token(user, "access", settings.access_token_ttl, settings),
        _create_token(user, "refresh", settings.refresh_token_ttl, settings),
    )


def decode_token(token: str, expected_type: str, settings: Settings) -> dict[str, Any]:
    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            settings.secret_key.get_secret_value(),
            algorithms=["HS256"],
            options={"require": ["sub", "org", "type", "exp", "iat"]},
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token is invalid or expired",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    if payload.get("type") != expected_type:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Wrong token type")
    return payload


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> User:
    payload = decode_token(token, "access", settings)
    user = db.scalar(select(User).where(User.id == payload["sub"]))
    if user is None or not user.is_active or user.organization_id != payload["org"]:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User is unavailable")
    return user


def require_role(minimum: Role) -> Callable[..., User]:
    def dependency(user: User = Depends(get_current_user)) -> User:
        if not has_minimum_role(user.role, minimum):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"The {minimum.value} role or above is required",
            )
        return user

    return dependency
