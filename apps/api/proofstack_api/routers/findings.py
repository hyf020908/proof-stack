"""Finding queries and reviewer-controlled lifecycle updates."""

from fastapi import APIRouter, Depends, Query, Request
from proofstack_shared.enums import FindingCategory, FindingSeverity, FindingStatus, Role
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from proofstack_api.audit import record_audit
from proofstack_api.auth import get_current_user, require_role
from proofstack_api.database import get_db
from proofstack_api.models import Finding, User
from proofstack_api.repositories import get_analysis_for_user, get_finding_for_user
from proofstack_api.schemas import FindingResponse, FindingUpdate, Page

router = APIRouter(tags=["findings"])


@router.get("/analyses/{analysis_id}/findings", response_model=Page[FindingResponse])
def list_findings(
    analysis_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    severity: FindingSeverity | None = None,
    category: FindingCategory | None = None,
    finding_status: FindingStatus | None = Query(default=None, alias="status"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Page[FindingResponse]:
    analysis = get_analysis_for_user(db, analysis_id, user)
    predicates = [Finding.analysis_run_id == analysis.id]
    if severity:
        predicates.append(Finding.severity == severity)
    if category:
        predicates.append(Finding.category == category)
    if finding_status:
        predicates.append(Finding.status == finding_status)
    total = db.scalar(select(func.count()).select_from(Finding).where(*predicates)) or 0
    severity_rank = {
        FindingSeverity.CRITICAL: 0,
        FindingSeverity.HIGH: 1,
        FindingSeverity.MEDIUM: 2,
        FindingSeverity.LOW: 3,
        FindingSeverity.INFO: 4,
    }
    items = list(
        db.scalars(
            select(Finding).where(*predicates).offset((page - 1) * page_size).limit(page_size)
        )
    )
    items.sort(
        key=lambda item: (severity_rank[item.severity], item.file_path or "", item.start_line or 0)
    )
    return Page(
        items=[FindingResponse.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
        pages=(total + page_size - 1) // page_size,
    )


@router.patch("/findings/{finding_id}", response_model=FindingResponse)
def update_finding(
    finding_id: str,
    payload: FindingUpdate,
    request: Request,
    user: User = Depends(require_role(Role.REVIEWER)),
    db: Session = Depends(get_db),
) -> Finding:
    finding = get_finding_for_user(db, finding_id, user)
    previous = finding.status
    finding.status = payload.status
    record_audit(
        db,
        user=user,
        action="finding.status_changed",
        resource_type="finding",
        resource_id=finding.id,
        metadata={"from": previous.value, "to": payload.status.value},
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
    db.refresh(finding)
    return finding
