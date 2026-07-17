"""Tenant settings and organization member reads."""

from fastapi import APIRouter, Depends, HTTPException, Request
from proofstack_shared.enums import Role
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from proofstack_api.audit import record_audit
from proofstack_api.auth import get_current_user, hash_password, require_role
from proofstack_api.database import get_db
from proofstack_api.models import Organization, User
from proofstack_api.schemas import (
    MemberCreate,
    MemberResponse,
    MemberUpdate,
    OrganizationResponse,
    OrganizationUpdate,
    Page,
)

router = APIRouter(prefix="/organizations/current", tags=["organizations"])


@router.get("", response_model=OrganizationResponse)
def current_organization(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> Organization:
    return db.get_one(Organization, user.organization_id)


@router.patch("", response_model=OrganizationResponse)
def update_organization(
    payload: OrganizationUpdate,
    request: Request,
    user: User = Depends(require_role(Role.OWNER)),
    db: Session = Depends(get_db),
) -> Organization:
    organization = db.get_one(Organization, user.organization_id)
    updates = payload.model_dump(exclude_unset=True)
    if "slug" in updates:
        duplicate = db.scalar(
            select(Organization.id).where(
                Organization.slug == updates["slug"],
                Organization.id != organization.id,
            )
        )
        if duplicate is not None:
            raise HTTPException(status_code=409, detail="This organization slug is already in use")
    for key, value in updates.items():
        setattr(organization, key, value)
    record_audit(
        db,
        user=user,
        action="organization.updated",
        resource_type="organization",
        resource_id=organization.id,
        metadata={"fields": sorted(updates)},
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
    db.refresh(organization)
    return organization


@router.get("/members", response_model=Page[MemberResponse])
def members(
    page: int = 1,
    page_size: int = 25,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Page[MemberResponse]:
    page = max(1, page)
    page_size = min(100, max(1, page_size))
    predicate = User.organization_id == user.organization_id
    total = db.scalar(select(func.count()).select_from(User).where(predicate)) or 0
    items = list(
        db.scalars(
            select(User)
            .where(predicate)
            .order_by(User.created_at)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return Page(
        items=[MemberResponse.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
        pages=(total + page_size - 1) // page_size,
    )


@router.post("/members", response_model=MemberResponse, status_code=201)
def create_member(
    payload: MemberCreate,
    request: Request,
    user: User = Depends(require_role(Role.OWNER)),
    db: Session = Depends(get_db),
) -> User:
    normalized_email = str(payload.email).lower()
    duplicate = db.scalar(
        select(User.id).where(
            User.organization_id == user.organization_id,
            User.email == normalized_email,
        )
    )
    if duplicate is not None:
        raise HTTPException(status_code=409, detail="A member with this email already exists")
    member = User(
        organization_id=user.organization_id,
        email=normalized_email,
        display_name=payload.display_name,
        password_hash=hash_password(payload.password),
        role=payload.role,
    )
    db.add(member)
    db.flush()
    record_audit(
        db,
        user=user,
        action="user.created",
        resource_type="user",
        resource_id=member.id,
        metadata={"role": member.role.value},
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
    db.refresh(member)
    return member


@router.patch("/members/{member_id}", response_model=MemberResponse)
def update_member(
    member_id: str,
    payload: MemberUpdate,
    request: Request,
    user: User = Depends(require_role(Role.OWNER)),
    db: Session = Depends(get_db),
) -> User:
    member = db.scalar(
        select(User).where(
            User.id == member_id,
            User.organization_id == user.organization_id,
        )
    )
    if member is None:
        raise HTTPException(status_code=404, detail="Organization member not found")
    updates = payload.model_dump(exclude_unset=True)
    removes_active_owner = member.role == Role.OWNER and (
        updates.get("role", Role.OWNER) != Role.OWNER or updates.get("is_active") is False
    )
    if removes_active_owner:
        active_owners = (
            db.scalar(
                select(func.count())
                .select_from(User)
                .where(
                    User.organization_id == user.organization_id,
                    User.role == Role.OWNER,
                    User.is_active.is_(True),
                )
            )
            or 0
        )
        if active_owners <= 1:
            raise HTTPException(
                status_code=409, detail="An organization must retain an active owner"
            )
    for key, value in updates.items():
        setattr(member, key, value)
    record_audit(
        db,
        user=user,
        action="user.updated",
        resource_type="user",
        resource_id=member.id,
        metadata={"fields": sorted(updates)},
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
    db.refresh(member)
    return member
