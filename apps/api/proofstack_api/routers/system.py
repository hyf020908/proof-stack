"""Health, readiness, metrics, public configuration, and dashboard endpoints."""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Response, status
from proofstack_shared.config import Settings, get_settings
from proofstack_shared.enums import AnalysisStatus, FindingSeverity, Verdict
from proofstack_shared.version import VERSION
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from proofstack_api.auth import get_current_user
from proofstack_api.database import get_db
from proofstack_api.models import AnalysisRun, AuditEvent, Finding, Project, User
from proofstack_api.schemas import (
    AnalysisResponse,
    AuditEventResponse,
    DashboardResponse,
    PublicConfigResponse,
)

router = APIRouter(tags=["system"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "healthy", "service": "proofstack-api", "version": VERSION}


@router.get("/ready")
def ready(
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    is_ready = True
    checks: dict[str, str] = {
        "database": "ready",
        "worker": "inline" if settings.task_backend == "inline" else "ready",
    }
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        checks["database"] = "unavailable"
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        is_ready = False
    if settings.task_backend == "rq":
        try:
            from redis import Redis

            connection = Redis.from_url(
                settings.redis_url,
                socket_connect_timeout=1,
                socket_timeout=1,
            )
            connection.ping()
        except Exception:
            checks["worker"] = "unavailable"
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
            is_ready = False
    return {"status": "ready" if is_ready else "not_ready", "checks": checks}


@router.get("/version")
def version() -> dict[str, str]:
    return {"version": VERSION, "schema_version": "1.0"}


@router.get("/system/public-config", response_model=PublicConfigResponse)
def public_config(settings: Settings = Depends(get_settings)) -> PublicConfigResponse:
    return PublicConfigResponse(
        version=VERSION,
        environment=settings.env,
        demo_mode=settings.demo_mode,
        task_backend=settings.task_backend,
        runner=settings.runner,
        github_token_configured=settings.github_token is not None,
        semgrep_enabled=settings.semgrep_enabled,
        llm_enabled=settings.llm_enabled,
    )


@router.get("/metrics", response_class=Response)
def metrics(db: Session = Depends(get_db)) -> Response:
    total = db.scalar(select(func.count()).select_from(AnalysisRun)) or 0
    running = (
        db.scalar(
            select(func.count())
            .select_from(AnalysisRun)
            .where(
                AnalysisRun.status.in_(
                    [
                        AnalysisStatus.QUEUED,
                        AnalysisStatus.PREPARING,
                        AnalysisStatus.ANALYZING,
                        AnalysisStatus.TESTING,
                        AnalysisStatus.EVALUATING,
                    ]
                )
            )
        )
        or 0
    )
    failed = (
        db.scalar(
            select(func.count())
            .select_from(AnalysisRun)
            .where(AnalysisRun.status == AnalysisStatus.FAILED)
        )
        or 0
    )
    body = "\n".join(
        [
            "# HELP proofstack_analyses_total Total analyses created.",
            "# TYPE proofstack_analyses_total counter",
            f"proofstack_analyses_total {total}",
            "# HELP proofstack_analyses_running Analyses currently running.",
            "# TYPE proofstack_analyses_running gauge",
            f"proofstack_analyses_running {running}",
            "# HELP proofstack_analyses_failed Analyses that failed.",
            "# TYPE proofstack_analyses_failed gauge",
            f"proofstack_analyses_failed {failed}",
            "",
        ]
    )
    return Response(body, media_type="text/plain; version=0.0.4")


def _duration_seconds(started: datetime | None, completed: datetime | None) -> float | None:
    if started is None or completed is None:
        return None
    return max(0.0, (completed - started).total_seconds())


@router.get("/dashboard", response_model=DashboardResponse)
def dashboard(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> DashboardResponse:
    project_ids = select(Project.id).where(Project.organization_id == user.organization_id)
    project_count = (
        db.scalar(
            select(func.count())
            .select_from(Project)
            .where(Project.organization_id == user.organization_id)
        )
        or 0
    )
    analysis_predicate = AnalysisRun.project_id.in_(project_ids)
    analysis_count = (
        db.scalar(select(func.count()).select_from(AnalysisRun).where(analysis_predicate)) or 0
    )
    verdict_counts = {item.value: 0 for item in Verdict}
    for verdict, count in db.execute(
        select(AnalysisRun.verdict, func.count())
        .where(analysis_predicate)
        .group_by(AnalysisRun.verdict)
    ):
        verdict_counts[verdict.value] = count
    severe_finding_count = (
        db.scalar(
            select(func.count())
            .select_from(Finding)
            .join(AnalysisRun)
            .where(
                analysis_predicate,
                Finding.severity.in_([FindingSeverity.CRITICAL, FindingSeverity.HIGH]),
            )
        )
        or 0
    )
    recent = list(
        db.scalars(
            select(AnalysisRun)
            .where(analysis_predicate)
            .order_by(AnalysisRun.created_at.desc())
            .limit(10)
        )
    )
    completed = list(
        db.scalars(
            select(AnalysisRun)
            .where(analysis_predicate, AnalysisRun.status == AnalysisStatus.COMPLETED)
            .order_by(AnalysisRun.created_at.desc())
            .limit(30)
        )
    )
    durations = [
        value
        for item in completed
        if (value := _duration_seconds(item.started_at, item.completed_at)) is not None
    ]
    audits = list(
        db.scalars(
            select(AuditEvent)
            .where(AuditEvent.organization_id == user.organization_id)
            .order_by(AuditEvent.created_at.desc())
            .limit(8)
        )
    )
    risk_trend = [
        {
            "date": item.created_at.date().isoformat(),
            "risk": item.risk_score,
            "verdict": item.verdict.value,
        }
        for item in reversed(completed[:14])
    ]
    return DashboardResponse(
        project_count=project_count,
        analysis_count=analysis_count,
        verdict_counts=verdict_counts,
        risk_trend=risk_trend,
        severe_finding_count=severe_finding_count,
        average_duration_seconds=sum(durations) / len(durations) if durations else 0.0,
        recent_analyses=[AnalysisResponse.model_validate(item) for item in recent],
        recent_audit_events=[AuditEventResponse.model_validate(item) for item in audits],
    )
