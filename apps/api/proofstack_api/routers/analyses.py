"""Analysis creation, upload, progress, cancellation, and result endpoints."""

from __future__ import annotations

import io
import json
import stat
import zipfile
from pathlib import Path, PurePosixPath
from typing import Annotated, Any

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from proofstack_shared.config import Settings, get_settings
from proofstack_shared.enums import AnalysisStatus, FindingSeverity, Role, SourceType
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from proofstack_api.audit import record_audit
from proofstack_api.auth import get_current_user, require_role
from proofstack_api.database import get_db
from proofstack_api.models import (
    AnalysisEvent,
    AnalysisRun,
    ChangedFile,
    CodeSymbol,
    DependencyEdge,
    EvidenceArtifact,
    Finding,
    PolicyDecision,
    Requirement,
    TestExecution,
    User,
)
from proofstack_api.repositories import get_analysis_for_user, get_project_for_user
from proofstack_api.schemas import (
    AnalysisEventResponse,
    AnalysisResponse,
    ChangedFileResponse,
    DemoAnalysisRequest,
    EvidenceArtifactResponse,
    EvidenceResponse,
    GitHubAnalysisRequest,
    GraphEdge,
    GraphNode,
    GraphResponse,
    Page,
    PolicyDecisionResponse,
    ProgressResponse,
    RequirementResponse,
    TestExecutionResponse,
)
from proofstack_api.task_dispatch import dispatch_analysis

router = APIRouter(tags=["analyses"])


def _analysis_response(db: Session, analysis: AnalysisRun) -> AnalysisResponse:
    finding_count = (
        db.scalar(
            select(func.count()).select_from(Finding).where(Finding.analysis_run_id == analysis.id)
        )
        or 0
    )
    critical_count = (
        db.scalar(
            select(func.count())
            .select_from(Finding)
            .where(
                Finding.analysis_run_id == analysis.id,
                Finding.severity == FindingSeverity.CRITICAL,
            )
        )
        or 0
    )
    changed_file_count = (
        db.scalar(
            select(func.count())
            .select_from(ChangedFile)
            .where(ChangedFile.analysis_run_id == analysis.id)
        )
        or 0
    )
    requirement_coverage = (
        db.scalar(
            select(func.avg(Requirement.coverage_score)).where(
                Requirement.analysis_run_id == analysis.id
            )
        )
        or 0.0
    )
    tests = list(
        db.scalars(select(TestExecution).where(TestExecution.analysis_run_id == analysis.id))
    )
    passed = sum(item.status.value == "passed" for item in tests)
    test_evidence = passed / len(tests) if tests else 0.0
    return AnalysisResponse.model_validate(analysis).model_copy(
        update={
            "finding_count": finding_count,
            "critical_count": critical_count,
            "changed_file_count": changed_file_count,
            "requirement_coverage": float(requirement_coverage),
            "test_evidence_score": test_evidence,
        }
    )


def _create_analysis(
    db: Session,
    *,
    project_id: str,
    user: User,
    source_type: SourceType,
    source_reference: str,
    requirements: str,
    policy_name: str,
    runner: str,
    validation_commands: list[list[str]],
    diff_text: str = "",
) -> AnalysisRun:
    for command in validation_commands:
        if not command or len(command) > 24 or any(len(argument) > 1000 for argument in command):
            raise HTTPException(
                status_code=422, detail="Validation commands contain invalid arguments"
            )
    analysis = AnalysisRun(
        project_id=project_id,
        source_type=source_type,
        source_reference=source_reference,
        created_by=user.id,
        requirements_text=requirements,
        policy_name=policy_name,
        runner_name=runner,
        validation_commands=validation_commands,
        diff_text=diff_text,
    )
    db.add(analysis)
    db.flush()
    return analysis


def _validate_zip(content: bytes, settings: Settings) -> None:
    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile as exc:
        raise HTTPException(
            status_code=422, detail="The uploaded source is not a valid ZIP archive"
        ) from exc
    infos = archive.infolist()
    if len(infos) > settings.max_file_count:
        raise HTTPException(status_code=413, detail="The archive contains too many files")
    total_size = 0
    for info in infos:
        name = info.filename.replace("\\", "/")
        path = PurePosixPath(name)
        mode = info.external_attr >> 16
        if (
            not name
            or "\x00" in name
            or path.is_absolute()
            or ".." in path.parts
            or (path.parts and ":" in path.parts[0])
            or stat.S_ISLNK(mode)
        ):
            raise HTTPException(
                status_code=422, detail="The archive contains an unsafe path or link"
            )
        total_size += info.file_size
        if total_size > settings.max_repository_bytes:
            raise HTTPException(
                status_code=413, detail="The archive expands beyond the repository limit"
            )
        if info.compress_size == 0 and info.file_size > 0:
            ratio = float("inf")
        else:
            ratio = info.file_size / max(1, info.compress_size)
        if ratio > 200 and info.file_size > 1024 * 1024:
            raise HTTPException(
                status_code=422, detail="The archive has a suspicious compression ratio"
            )


async def _read_upload(upload: UploadFile, limit: int) -> bytes:
    chunks: list[bytes] = []
    size = 0
    while chunk := await upload.read(1024 * 1024):
        size += len(chunk)
        if size > limit:
            raise HTTPException(
                status_code=413, detail="The uploaded file exceeds the configured limit"
            )
        chunks.append(chunk)
    return b"".join(chunks)


@router.post(
    "/projects/{project_id}/analyses/demo",
    response_model=AnalysisResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def start_demo_analysis(
    project_id: str,
    payload: DemoAnalysisRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    user: User = Depends(require_role(Role.MAINTAINER)),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AnalysisResponse:
    if not settings.demo_mode:
        raise HTTPException(status_code=404, detail="Demo mode is disabled")
    project = get_project_for_user(db, project_id, user)
    analysis = _create_analysis(
        db,
        project_id=project.id,
        user=user,
        source_type=SourceType.DEMO,
        source_reference="examples/demo-python-service",
        requirements=payload.requirements,
        policy_name=payload.policy_name,
        runner=payload.runner,
        validation_commands=payload.validation_commands,
    )
    record_audit(
        db,
        user=user,
        action="analysis.started",
        resource_type="analysis",
        resource_id=analysis.id,
        metadata={"source_type": "demo"},
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
    dispatch_analysis(analysis.id, background_tasks=background_tasks, settings=settings)
    return _analysis_response(db, analysis)


@router.post(
    "/projects/{project_id}/analyses/github",
    response_model=AnalysisResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def start_github_analysis(
    project_id: str,
    payload: GitHubAnalysisRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    user: User = Depends(require_role(Role.MAINTAINER)),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AnalysisResponse:
    project = get_project_for_user(db, project_id, user)
    analysis = _create_analysis(
        db,
        project_id=project.id,
        user=user,
        source_type=SourceType.GITHUB,
        source_reference=str(payload.url),
        requirements=payload.requirements,
        policy_name=payload.policy_name,
        runner=payload.runner,
        validation_commands=payload.validation_commands,
    )
    record_audit(
        db,
        user=user,
        action="analysis.started",
        resource_type="analysis",
        resource_id=analysis.id,
        metadata={"source_type": "github", "host": payload.url.host},
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
    dispatch_analysis(analysis.id, background_tasks=background_tasks, settings=settings)
    return _analysis_response(db, analysis)


@router.post(
    "/projects/{project_id}/analyses/upload",
    response_model=AnalysisResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_upload_analysis(
    project_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    source: Annotated[UploadFile, File(description="Repository source ZIP")],
    diff: Annotated[UploadFile | None, File(description="Optional unified diff")] = None,
    requirements: Annotated[str, Form(max_length=100000)] = "",
    policy_name: Annotated[str, Form(max_length=100)] = "default",
    runner: Annotated[str, Form(pattern=r"^(native|docker)$")] = "native",
    validation_commands: Annotated[str, Form(max_length=10000)] = "[]",
    user: User = Depends(require_role(Role.MAINTAINER)),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AnalysisResponse:
    project = get_project_for_user(db, project_id, user)
    if not source.filename or not source.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=422, detail="Source upload must be a .zip file")
    source_content = await _read_upload(source, settings.max_upload_bytes)
    _validate_zip(source_content, settings)
    diff_text = ""
    if diff is not None:
        if not diff.filename or not diff.filename.lower().endswith((".diff", ".patch")):
            raise HTTPException(status_code=422, detail="Diff upload must use .diff or .patch")
        diff_bytes = await _read_upload(diff, min(settings.max_upload_bytes, 5 * 1024 * 1024))
        try:
            diff_text = diff_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise HTTPException(status_code=422, detail="Diff upload must be UTF-8 text") from exc
    try:
        commands_value = json.loads(validation_commands)
        if not isinstance(commands_value, list) or any(
            not isinstance(item, list) for item in commands_value
        ):
            raise ValueError
        commands = [[str(argument) for argument in item] for item in commands_value]
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(
            status_code=422, detail="validation_commands must be a JSON array of arrays"
        ) from exc
    analysis = _create_analysis(
        db,
        project_id=project.id,
        user=user,
        source_type=SourceType.UPLOAD,
        source_reference="pending-upload",
        requirements=requirements,
        policy_name=policy_name,
        runner=runner,
        validation_commands=commands,
        diff_text=diff_text,
    )
    upload_dir = settings.workspace_root / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    upload_path = (upload_dir / f"{analysis.id}.zip").resolve()
    upload_path.write_bytes(source_content)
    analysis.source_reference = str(upload_path)
    record_audit(
        db,
        user=user,
        action="analysis.started",
        resource_type="analysis",
        resource_id=analysis.id,
        metadata={"source_type": "upload", "bytes": len(source_content)},
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
    dispatch_analysis(analysis.id, background_tasks=background_tasks, settings=settings)
    return _analysis_response(db, analysis)


@router.get("/analyses/{analysis_id}", response_model=AnalysisResponse)
def get_analysis(
    analysis_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AnalysisResponse:
    return _analysis_response(db, get_analysis_for_user(db, analysis_id, user))


@router.post("/analyses/{analysis_id}/cancel", response_model=AnalysisResponse)
def cancel_analysis(
    analysis_id: str,
    request: Request,
    user: User = Depends(require_role(Role.MAINTAINER)),
    db: Session = Depends(get_db),
) -> AnalysisResponse:
    analysis = get_analysis_for_user(db, analysis_id, user)
    if analysis.status in {
        AnalysisStatus.COMPLETED,
        AnalysisStatus.FAILED,
        AnalysisStatus.CANCELLED,
    }:
        raise HTTPException(status_code=409, detail="Only an active analysis can be cancelled")
    analysis.status = AnalysisStatus.CANCELLED
    analysis.current_stage = "CANCELLED"
    record_audit(
        db,
        user=user,
        action="analysis.cancelled",
        resource_type="analysis",
        resource_id=analysis.id,
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
    return _analysis_response(db, analysis)


@router.get("/analyses/{analysis_id}/progress", response_model=ProgressResponse)
def analysis_progress(
    analysis_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProgressResponse:
    analysis = get_analysis_for_user(db, analysis_id, user)
    events = list(
        db.scalars(
            select(AnalysisEvent)
            .where(AnalysisEvent.analysis_run_id == analysis.id)
            .order_by(AnalysisEvent.created_at)
        )
    )
    return ProgressResponse(
        analysis_id=analysis.id,
        status=analysis.status,
        progress=analysis.progress,
        current_stage=analysis.current_stage,
        verdict=analysis.verdict,
        error_summary=analysis.error_summary,
        stages=[
            {
                "name": event.stage,
                "status": event.status,
                "progress": event.progress,
                "duration_ms": event.duration_ms,
            }
            for event in events
        ],
    )


@router.get("/analyses/{analysis_id}/events", response_model=list[AnalysisEventResponse])
def analysis_events(
    analysis_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[AnalysisEvent]:
    analysis = get_analysis_for_user(db, analysis_id, user)
    return list(
        db.scalars(
            select(AnalysisEvent)
            .where(AnalysisEvent.analysis_run_id == analysis.id)
            .order_by(AnalysisEvent.created_at)
        )
    )


@router.get("/analyses/{analysis_id}/changed-files", response_model=Page[ChangedFileResponse])
def changed_files(
    analysis_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=500),
    risk_min: int = Query(default=0, ge=0, le=100),
    is_test: bool | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Page[ChangedFileResponse]:
    analysis = get_analysis_for_user(db, analysis_id, user)
    predicates = [ChangedFile.analysis_run_id == analysis.id, ChangedFile.risk_score >= risk_min]
    if is_test is not None:
        predicates.append(ChangedFile.is_test == is_test)
    total = db.scalar(select(func.count()).select_from(ChangedFile).where(*predicates)) or 0
    items = list(
        db.scalars(
            select(ChangedFile)
            .where(*predicates)
            .order_by(ChangedFile.risk_score.desc(), ChangedFile.path)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return Page(
        items=[ChangedFileResponse.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
        pages=(total + page_size - 1) // page_size,
    )


@router.get("/analyses/{analysis_id}/graph", response_model=GraphResponse)
def analysis_graph(
    analysis_id: str,
    limit: int = Query(default=500, ge=10, le=2000),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> GraphResponse:
    analysis = get_analysis_for_user(db, analysis_id, user)
    files = list(
        db.scalars(
            select(ChangedFile)
            .where(ChangedFile.analysis_run_id == analysis.id)
            .order_by(ChangedFile.risk_score.desc())
            .limit(limit)
        )
    )
    remaining = max(0, limit - len(files))
    symbols = list(
        db.scalars(
            select(CodeSymbol).where(CodeSymbol.analysis_run_id == analysis.id).limit(remaining)
        )
    )
    file_path_by_id = {item.id: item.path for item in files}
    nodes = [
        GraphNode(
            id=f"file:{item.path}",
            label=item.path,
            type="file",
            file_path=item.path,
            changed=True,
            risk_score=item.risk_score,
        )
        for item in files
    ]
    nodes.extend(
        GraphNode(
            id=symbol.qualified_name,
            label=symbol.qualified_name.rsplit(".", 1)[-1],
            type=symbol.symbol_type,
            file_path=file_path_by_id.get(symbol.file_id) if symbol.file_id else None,
            changed=symbol.changed,
            risk_score=0,
        )
        for symbol in symbols
    )
    node_ids = {node.id for node in nodes}
    edges = [
        GraphEdge(
            id=edge.id,
            source=edge.source_symbol,
            target=edge.target_symbol,
            type=edge.edge_type,
            confidence=edge.confidence,
        )
        for edge in db.scalars(
            select(DependencyEdge)
            .where(DependencyEdge.analysis_run_id == analysis.id)
            .limit(limit * 4)
        )
        if edge.source_symbol in node_ids and edge.target_symbol in node_ids
    ]
    total_nodes = (
        db.scalar(
            select(func.count())
            .select_from(CodeSymbol)
            .where(CodeSymbol.analysis_run_id == analysis.id)
        )
        or 0
    )
    total_nodes += (
        db.scalar(
            select(func.count())
            .select_from(ChangedFile)
            .where(ChangedFile.analysis_run_id == analysis.id)
        )
        or 0
    )
    return GraphResponse(nodes=nodes, edges=edges, truncated=total_nodes > len(nodes))


@router.get("/analyses/{analysis_id}/requirements", response_model=list[RequirementResponse])
def analysis_requirements(
    analysis_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[Requirement]:
    analysis = get_analysis_for_user(db, analysis_id, user)
    return list(
        db.scalars(
            select(Requirement)
            .where(Requirement.analysis_run_id == analysis.id)
            .order_by(Requirement.external_id, Requirement.title)
        )
    )


@router.get("/analyses/{analysis_id}/tests", response_model=list[TestExecutionResponse])
def analysis_tests(
    analysis_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[TestExecution]:
    analysis = get_analysis_for_user(db, analysis_id, user)
    return list(
        db.scalars(select(TestExecution).where(TestExecution.analysis_run_id == analysis.id))
    )


@router.get("/analyses/{analysis_id}/policy-decisions", response_model=list[PolicyDecisionResponse])
def analysis_policy_decisions(
    analysis_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[PolicyDecision]:
    analysis = get_analysis_for_user(db, analysis_id, user)
    return list(
        db.scalars(select(PolicyDecision).where(PolicyDecision.analysis_run_id == analysis.id))
    )


@router.get("/analyses/{analysis_id}/evidence", response_model=EvidenceResponse)
def analysis_evidence(
    analysis_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> EvidenceResponse:
    analysis = get_analysis_for_user(db, analysis_id, user)
    artifacts = list(
        db.scalars(select(EvidenceArtifact).where(EvidenceArtifact.analysis_run_id == analysis.id))
    )
    manifest: dict[str, Any] | None = None
    verification: dict[str, Any] | None = None
    manifest_artifact = next((item for item in artifacts if item.name == "manifest.json"), None)
    if manifest_artifact:
        path = Path(manifest_artifact.storage_path)
        if path.is_file():
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
                manifest = loaded if isinstance(loaded, dict) else None
            except (OSError, json.JSONDecodeError):
                manifest = None
            try:
                from proofstack_core import EvidenceBundleVerifier

                verification = EvidenceBundleVerifier().verify(path.parent).to_dict()
            except (OSError, ValueError):
                verification = {"valid": False, "issues": [{"code": "verification_failed"}]}
    return EvidenceResponse(
        analysis_id=analysis.id,
        ready=any(item.artifact_type == "bundle_zip" for item in artifacts),
        artifacts=[EvidenceArtifactResponse.model_validate(item) for item in artifacts],
        manifest=manifest,
        verification=verification,
    )


@router.get("/analyses/{analysis_id}/evidence/download")
def download_evidence(
    analysis_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FileResponse:
    analysis = get_analysis_for_user(db, analysis_id, user)
    artifact = db.scalar(
        select(EvidenceArtifact).where(
            EvidenceArtifact.analysis_run_id == analysis.id,
            EvidenceArtifact.artifact_type == "bundle_zip",
        )
    )
    if artifact is None or not Path(artifact.storage_path).is_file():
        raise HTTPException(status_code=409, detail="Evidence bundle is not ready")
    return FileResponse(
        artifact.storage_path,
        media_type="application/zip",
        filename=f"proofstack-evidence-{analysis.id}.zip",
    )
