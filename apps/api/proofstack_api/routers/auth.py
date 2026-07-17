"""Registration, login, demo access, refresh, and identity endpoints."""

import re
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, status
from proofstack_shared.config import Settings, get_settings
from proofstack_shared.enums import Role
from sqlalchemy import select
from sqlalchemy.orm import Session

from proofstack_api.audit import record_audit
from proofstack_api.auth import (
    create_token_pair,
    decode_token,
    get_current_user,
    hash_password,
    verify_password,
)
from proofstack_api.database import get_db
from proofstack_api.models import Organization, User
from proofstack_api.schemas import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenPair,
    UserResponse,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:80] or "organization"


def _tokens(user: User, settings: Settings) -> TokenPair:
    access, refresh = create_token_pair(user, settings)
    return TokenPair(
        access_token=access,
        refresh_token=refresh,
        expires_in=settings.access_token_ttl,
    )


@router.post("/register", response_model=TokenPair, status_code=status.HTTP_201_CREATED)
def register(
    payload: RegisterRequest,
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> TokenPair:
    slug_base = _slugify(payload.organization_name)
    slug = slug_base
    counter = 1
    while db.scalar(select(Organization.id).where(Organization.slug == slug)) is not None:
        counter += 1
        slug = f"{slug_base[:90]}-{counter}"
    organization = Organization(name=payload.organization_name, slug=slug)
    db.add(organization)
    db.flush()
    user = User(
        organization_id=organization.id,
        email=str(payload.email).lower(),
        display_name=payload.display_name,
        password_hash=hash_password(payload.password),
        role=Role.OWNER,
    )
    db.add(user)
    db.flush()
    record_audit(
        db,
        user=user,
        action="user.registered",
        resource_type="user",
        resource_id=user.id,
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
    return _tokens(user, settings)


@router.post("/login", response_model=TokenPair)
def login(
    payload: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> TokenPair:
    statement = select(User).join(Organization).where(User.email == str(payload.email).lower())
    if payload.organization_slug:
        statement = statement.where(Organization.slug == payload.organization_slug)
    candidates = list(db.scalars(statement))
    if len(candidates) != 1 or not verify_password(payload.password, candidates[0].password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    user = candidates[0]
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled")
    record_audit(
        db,
        user=user,
        action="user.logged_in",
        resource_type="user",
        resource_id=user.id,
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
    return _tokens(user, settings)


@router.post("/demo", response_model=TokenPair)
def demo_login(
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> TokenPair:
    if not settings.demo_mode:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Demo mode is disabled")
    organization = db.scalar(select(Organization).where(Organization.slug == "proofstack-demo"))
    if organization is None:
        organization = Organization(name="ProofStack Demo", slug="proofstack-demo")
        db.add(organization)
        db.flush()
    user = db.scalar(
        select(User).where(
            User.organization_id == organization.id,
            User.email == "demo@proofstack.local",
        )
    )
    if user is None:
        user = User(
            organization_id=organization.id,
            email="demo@proofstack.local",
            display_name="Demo Maintainer",
            password_hash=hash_password(secrets.token_urlsafe(32)),
            role=Role.MAINTAINER,
        )
        db.add(user)
        db.flush()
    record_audit(
        db,
        user=user,
        action="user.demo_login",
        resource_type="user",
        resource_id=user.id,
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
    return _tokens(user, settings)


@router.post("/refresh", response_model=TokenPair)
def refresh(
    payload: RefreshRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> TokenPair:
    claims = decode_token(payload.refresh_token, "refresh", settings)
    user = db.scalar(select(User).where(User.id == claims["sub"]))
    if user is None or not user.is_active or user.organization_id != claims["org"]:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User is unavailable")
    return _tokens(user, settings)


@router.get("/me", response_model=UserResponse)
def me(user: User = Depends(get_current_user)) -> User:
    return user
