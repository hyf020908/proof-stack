"""RQ-compatible task entry point with complete persistence and audit handling."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from proofstack_analyzers import DiffDocument
from proofstack_api.audit import record_audit
from proofstack_api.database import SessionLocal
from proofstack_api.models import (
    AnalysisEvent,
    AnalysisRun,
    AuditEvent,
    ChangedFile,
    CodeSymbol,
    DependencyEdge,
    EvidenceArtifact,
    Project,
    Requirement,
    TestExecution,
    User,
)
from proofstack_api.models import (
    Finding as FindingModel,
)
from proofstack_api.models import (
    PolicyDecision as PolicyDecisionModel,
)
from proofstack_core import AnalysisContext, StageResult, StageStatus
from proofstack_core.evidence import sha256_file
from proofstack_core.redaction import redact_data
from proofstack_shared.config import get_settings
from proofstack_shared.enums import (
    AnalysisStatus,
    FindingCategory,
    FindingSeverity,
    FindingStatus,
    PolicyOutcome,
    TestStatus,
    Verdict,
)
from sqlalchemy import select

from proofstack_worker.analysis import build_pipeline
from proofstack_worker.stages import cleanup_prepared_source, to_jsonable


def _analysis_status(stage: str) -> AnalysisStatus:
    if stage == "PREPARE_SOURCE":
        return AnalysisStatus.PREPARING
    if stage == "EXECUTE_VALIDATION":
        return AnalysisStatus.TESTING
    if stage in {"EVALUATE_POLICIES", "BUILD_EVIDENCE", "FINALIZE"}:
        return AnalysisStatus.EVALUATING
    return AnalysisStatus.ANALYZING


def _progress_callback(db: Any, run: AnalysisRun) -> Any:
    def callback(context: AnalysisContext, result: StageResult | None) -> None:
        db.refresh(run)
        if run.status == AnalysisStatus.CANCELLED:
            context.cancel()
            return
        stage = context.current_stage or "FINALIZE"
        run.status = _analysis_status(stage)
        run.current_stage = stage
        run.progress = context.progress
        if result is None:
            db.add(
                AnalysisEvent(
                    analysis_run_id=run.id,
                    stage=stage,
                    level="info",
                    message=f"{stage} started",
                    progress=context.progress,
                    status="running",
                )
            )
        else:
            event = db.scalar(
                select(AnalysisEvent)
                .where(
                    AnalysisEvent.analysis_run_id == run.id,
                    AnalysisEvent.stage == stage,
                    AnalysisEvent.status == "running",
                )
                .order_by(AnalysisEvent.created_at.desc())
            )
            if event is None:
                event = AnalysisEvent(
                    analysis_run_id=run.id,
                    stage=stage,
                    level="info",
                    message="",
                    progress=context.progress,
                )
                db.add(event)
            event.status = result.status.value
            event.progress = context.progress
            event.duration_ms = result.duration_ms
            event.message = result.user_message or f"{stage} {result.status.value}"
            event.level = "error" if result.status == StageStatus.FAILED else "info"
        db.commit()

    return callback


def _file_risk(item: Any) -> int:
    score = min(30, int(item.additions + item.deletions) // 20)
    score += 20 if item.is_security_sensitive else 0
    score += 15 if item.is_dependency_manifest else 0
    score += 20 if item.is_migration else 0
    score += 10 if item.is_ci else 0
    score -= 10 if item.is_test else 0
    return max(0, min(100, score))


def _hash_text(value: str | None) -> str | None:
    return hashlib.sha256(value.encode()).hexdigest() if value is not None else None


def _persist_changed_files(
    db: Any, run: AnalysisRun, context: AnalysisContext
) -> dict[str, ChangedFile]:
    document = context.data.get("diff_document")
    source_files = context.data.get("source_files", {})
    previous_files = context.data.get("previous_files", {})
    if not isinstance(document, DiffDocument):
        return {}
    stored: dict[str, ChangedFile] = {}
    for item in document.files:
        current_text = source_files.get(item.path) if isinstance(source_files, dict) else None
        previous_path = item.old_path or item.path
        previous_text = (
            previous_files.get(previous_path) if isinstance(previous_files, dict) else None
        )
        model = ChangedFile(
            analysis_run_id=run.id,
            path=item.path,
            change_type=item.change_type.value,
            additions=item.additions,
            deletions=item.deletions,
            language=item.language,
            risk_score=_file_risk(item),
            is_test=item.is_test,
            is_generated=any(token in item.path.lower() for token in ("generated", "vendor/")),
            old_hash=_hash_text(previous_text),
            new_hash=_hash_text(current_text),
            metadata_json={
                "binary": item.is_binary,
                "config": item.is_config,
                "dependency": item.is_dependency_manifest,
                "migration": item.is_migration,
                "api_schema": item.is_api_schema,
                "ci": item.is_ci,
                "security_sensitive": item.is_security_sensitive,
            },
        )
        db.add(model)
        stored[item.path] = model
    db.flush()
    return stored


def _persist_symbols_and_graph(
    db: Any,
    run: AnalysisRun,
    context: AnalysisContext,
    files: dict[str, ChangedFile],
) -> None:
    changed = set(context.data.get("changed_symbols", []))
    for analysis in context.data.get("python_analyses", []):
        module_file = files.get(analysis.path)
        if not any(item.qualified_name == f"module:{analysis.module}" for item in run.symbols):
            db.add(
                CodeSymbol(
                    analysis_run_id=run.id,
                    file_id=module_file.id if module_file is not None else None,
                    qualified_name=f"module:{analysis.module}",
                    symbol_type="module",
                    start_line=1,
                    end_line=max(
                        1,
                        len(
                            context.data.get("source_files", {}).get(analysis.path, "").splitlines()
                        ),
                    ),
                    signature="",
                    complexity=1,
                    exported=True,
                    changed=any(
                        symbol.module == analysis.module
                        for symbol in analysis.symbols
                        if symbol.qualified_name in changed
                    ),
                )
            )
        for symbol in analysis.symbols:
            symbol_file = files.get(symbol.path)
            db.add(
                CodeSymbol(
                    analysis_run_id=run.id,
                    file_id=symbol_file.id if symbol_file is not None else None,
                    qualified_name=f"symbol:{symbol.qualified_name}",
                    symbol_type=symbol.symbol_type,
                    start_line=symbol.start_line,
                    end_line=symbol.end_line,
                    signature=symbol.signature,
                    complexity=symbol.complexity,
                    exported=symbol.exported,
                    changed=symbol.qualified_name in changed,
                )
            )
    graph = context.data.get("dependency_graph")
    for edge in getattr(graph, "edges", []):
        db.add(
            DependencyEdge(
                analysis_run_id=run.id,
                source_symbol=edge.source,
                target_symbol=edge.target,
                edge_type=edge.edge_type,
                confidence=edge.confidence,
            )
        )


def _persist_requirements(db: Any, run: AnalysisRun, context: AnalysisContext) -> None:
    mapping_result = context.data.get("requirement_mapping")
    mappings = {item.requirement_id: item for item in getattr(mapping_result, "mappings", [])}
    for spec in context.data.get("requirements", []):
        mapping = mappings.get(spec.id)
        evidence = {
            "supported": bool(getattr(mapping, "supported", False)),
            "matches": to_jsonable(getattr(mapping, "evidence", [])),
            "changed_files": list(getattr(mapping, "changed_files", [])),
            "changed_symbols": list(getattr(mapping, "changed_symbols", [])),
            "tests": list(getattr(mapping, "tests", [])),
            "routes": list(getattr(mapping, "routes", [])),
        }
        db.add(
            Requirement(
                analysis_run_id=run.id,
                external_id=spec.id,
                title=spec.title,
                description=spec.description,
                acceptance_criteria=list(spec.acceptance_criteria),
                source=spec.source,
                confidence=float(getattr(mapping, "score", 0.0)),
                coverage_score=float(getattr(mapping, "score", 0.0)),
                evidence=evidence,
            )
        )


def _persist_findings(db: Any, run: AnalysisRun, context: AnalysisContext) -> None:
    for item in context.findings:
        db.add(
            FindingModel(
                analysis_run_id=run.id,
                category=FindingCategory(item.category.value),
                severity=FindingSeverity(item.severity.value),
                title=item.title,
                description=item.description,
                file_path=item.file_path,
                start_line=item.start_line,
                end_line=item.end_line,
                rule_id=item.rule_id,
                remediation=item.remediation,
                evidence=redact_data(item.evidence),
                fingerprint=item.fingerprint,
                status=FindingStatus(item.status.value),
            )
        )


def _persist_execution_and_policy(db: Any, run: AnalysisRun, context: AnalysisContext) -> None:
    execution = context.data.get("execution_result")
    for item in getattr(execution, "executions", []):
        db.add(
            TestExecution(
                analysis_run_id=run.id,
                command=list(item.command),
                status=TestStatus(item.status.value),
                exit_code=item.exit_code,
                duration_ms=item.duration_ms,
                stdout_excerpt=item.stdout_excerpt,
                stderr_excerpt=item.stderr_excerpt,
                timed_out=item.timed_out,
                environment=item.environment,
            )
        )
    evaluation = context.data.get("policy_evaluation")
    for item in getattr(evaluation, "decisions", []):
        db.add(
            PolicyDecisionModel(
                analysis_run_id=run.id,
                policy_name=item.policy_name,
                rule_id=item.rule_id,
                outcome=PolicyOutcome(item.outcome.value),
                explanation=item.explanation,
                observed_value=item.observed_value,
                expected_value=item.expected_value,
                evidence_references=list(item.evidence_references),
            )
        )


def _persist_artifacts(db: Any, run: AnalysisRun, context: AnalysisContext) -> None:
    result = context.data.get("evidence_result")
    if result is None:
        return
    bundle_path = Path(result.path)
    for path in sorted(bundle_path.iterdir()):
        if path.is_file():
            db.add(
                EvidenceArtifact(
                    analysis_run_id=run.id,
                    artifact_type="bundle_file",
                    name=path.name,
                    content_type=(
                        "application/json"
                        if path.suffix == ".json"
                        else "text/html"
                        if path.suffix == ".html"
                        else "text/plain"
                    ),
                    storage_path=str(path),
                    sha256=sha256_file(path),
                    size=path.stat().st_size,
                )
            )
    archive = context.data.get("evidence_archive")
    if isinstance(archive, Path):
        db.add(
            EvidenceArtifact(
                analysis_run_id=run.id,
                artifact_type="bundle_zip",
                name=archive.name,
                content_type="application/zip",
                storage_path=str(archive),
                sha256=sha256_file(archive),
                size=archive.stat().st_size,
            )
        )


def _persist_results(db: Any, run: AnalysisRun, context: AnalysisContext) -> None:
    files = _persist_changed_files(db, run, context)
    _persist_symbols_and_graph(db, run, context, files)
    _persist_requirements(db, run, context)
    _persist_findings(db, run, context)
    _persist_execution_and_policy(db, run, context)
    _persist_artifacts(db, run, context)


def run_analysis(analysis_id: str) -> None:
    settings = get_settings()
    db = SessionLocal()
    context: AnalysisContext | None = None
    try:
        run = db.get(AnalysisRun, analysis_id)
        if run is None or run.status == AnalysisStatus.CANCELLED:
            return
        project = db.get(Project, run.project_id)
        user = db.get(User, run.created_by)
        if project is None or user is None:
            raise RuntimeError("The analysis owner or project is unavailable")
        run.started_at = datetime.now(UTC)
        run.status = AnalysisStatus.PREPARING
        run.current_stage = "PREPARE_SOURCE"
        db.commit()
        audit_events = list(
            db.scalars(
                select(AuditEvent)
                .where(AuditEvent.organization_id == project.organization_id)
                .order_by(AuditEvent.created_at.desc())
                .limit(100)
            )
        )
        context = AnalysisContext(
            analysis_id=run.id,
            workspace=settings.workspace_root / run.id,
            diff_text=run.diff_text,
            requirement_text=run.requirements_text,
            data={
                "settings": settings,
                "source_type": run.source_type.value,
                "source_reference": run.source_reference,
                "runner": run.runner_name,
                "validation_commands": run.validation_commands,
                "evidence_output_directory": (
                    settings.artifact_root / run.id / "evidence-bundle"
                ).resolve(),
                "audit_events": [
                    {
                        "id": item.id,
                        "action": item.action,
                        "resource_type": item.resource_type,
                        "resource_id": item.resource_id,
                        "user_id": item.user_id,
                        "created_at": item.created_at.isoformat(),
                    }
                    for item in audit_events
                ],
                "known_secrets": [
                    settings.github_token.get_secret_value() if settings.github_token else "",
                    settings.llm_api_key.get_secret_value() if settings.llm_api_key else "",
                ],
            },
        )
        result = build_pipeline(on_progress=_progress_callback(db, run)).run(context)
        if result.status == StageStatus.CANCELLED or run.status == AnalysisStatus.CANCELLED:
            run.status = AnalysisStatus.CANCELLED
            run.current_stage = "CANCELLED"
            db.commit()
            return
        _persist_results(db, run, context)
        if result.status == StageStatus.FAILED:
            run.status = AnalysisStatus.FAILED
            run.error_summary = result.error_summary
            run.current_stage = context.current_stage or "FAILED"
            run.completed_at = datetime.now(UTC)
        else:
            risk = context.data.get("risk_assessment")
            run.status = AnalysisStatus.COMPLETED
            run.verdict = Verdict(str(context.data.get("verdict", "unknown")))
            run.risk_score = int(getattr(risk, "score", 0))
            run.risk_components = to_jsonable(risk)
            run.progress = 100
            run.current_stage = "FINALIZE"
            run.completed_at = datetime.now(UTC)
            run.base_revision = context.data.get("base_revision")
            run.head_revision = context.data.get("head_revision")
            run.workspace_path = str(context.workspace)
            record_audit(
                db,
                user=user,
                action="analysis.completed",
                resource_type="analysis",
                resource_id=run.id,
                metadata={"verdict": run.verdict.value, "risk_score": run.risk_score},
            )
        db.commit()
    except Exception as exc:
        db.rollback()
        run = db.get(AnalysisRun, analysis_id)
        if run is not None and run.status != AnalysisStatus.CANCELLED:
            run.status = AnalysisStatus.FAILED
            run.error_summary = f"Analysis could not be completed: {exc}"
            run.completed_at = datetime.now(UTC)
            db.commit()
    finally:
        if context is not None:
            cleanup_prepared_source(context)
        run = db.get(AnalysisRun, analysis_id)
        if run is not None and run.source_type.value == "upload":
            upload = Path(run.source_reference).resolve()
            uploads_root = (settings.workspace_root / "uploads").resolve()
            try:
                upload.relative_to(uploads_root)
            except ValueError:
                pass
            else:
                if upload.is_file():
                    upload.unlink()
        db.close()
