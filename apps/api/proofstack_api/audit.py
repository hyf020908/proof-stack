"""Audit helpers that capture security-relevant state transitions."""

from typing import Any

from sqlalchemy.orm import Session

from proofstack_api.models import AuditEvent, User


def record_audit(
    db: Session,
    *,
    user: User,
    action: str,
    resource_type: str,
    resource_id: str | None,
    metadata: dict[str, Any] | None = None,
    ip_address: str | None = None,
) -> AuditEvent:
    event = AuditEvent(
        organization_id=user.organization_id,
        user_id=user.id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        metadata_json=metadata or {},
        ip_address=ip_address,
    )
    db.add(event)
    return event
