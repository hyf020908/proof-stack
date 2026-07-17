"""Paginated, tenant-isolated audit log queries."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from proofstack_api.auth import get_current_user
from proofstack_api.database import get_db
from proofstack_api.models import AuditEvent, User
from proofstack_api.schemas import AuditEventResponse, Page

router = APIRouter(prefix="/audit-events", tags=["audit"])


@router.get("", response_model=Page[AuditEventResponse])
def list_audit_events(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    action: str | None = Query(default=None, max_length=200),
    resource_type: str | None = Query(default=None, max_length=100),
    user_id: str | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Page[AuditEventResponse]:
    predicates = [AuditEvent.organization_id == user.organization_id]
    if action:
        predicates.append(AuditEvent.action == action)
    if resource_type:
        predicates.append(AuditEvent.resource_type == resource_type)
    if user_id:
        predicates.append(AuditEvent.user_id == user_id)
    total = db.scalar(select(func.count()).select_from(AuditEvent).where(*predicates)) or 0
    items = list(
        db.scalars(
            select(AuditEvent)
            .where(*predicates)
            .order_by(AuditEvent.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return Page(
        items=[AuditEventResponse.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
        pages=(total + page_size - 1) // page_size,
    )
