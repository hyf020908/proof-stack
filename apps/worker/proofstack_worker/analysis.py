"""Reusable pipeline assembly for database tasks and the local CLI."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from proofstack_analyzers import default_analysis_stages
from proofstack_analyzers.stages import ParseDiffStage
from proofstack_core import (
    AnalysisContext,
    AnalysisPipeline,
    AnalysisStage,
    PipelineResult,
    StageStatus,
)
from proofstack_shared.config import Settings

from proofstack_worker.stages import (
    BuildEvidenceStage,
    CompleteDiscoverFilesStage,
    CompleteSecurityStage,
    EvaluatePoliciesStage,
    ExecuteValidationStage,
    FinalizeStage,
    PrepareSourceStage,
    cleanup_prepared_source,
)


@dataclass(slots=True)
class LocalAnalysisResult:
    analysis_id: str
    verdict: str
    risk_score: int
    finding_count: int
    bundle_path: Path
    archive_path: Path
    pipeline: PipelineResult

    def to_dict(self) -> dict[str, Any]:
        return {
            "analysis_id": self.analysis_id,
            "verdict": self.verdict,
            "risk_score": self.risk_score,
            "finding_count": self.finding_count,
            "bundle_path": str(self.bundle_path),
            "archive_path": str(self.archive_path),
            "status": self.pipeline.status.value,
        }


def build_pipeline(*, on_progress: Any = None) -> AnalysisPipeline:
    deterministic: list[AnalysisStage] = []
    for stage in default_analysis_stages():
        if stage.name in {"DISCOVER_FILES", "PARSE_DIFF"}:
            continue
        deterministic.append(CompleteSecurityStage() if stage.name == "SCAN_SECURITY" else stage)
    stages: list[AnalysisStage] = [
        PrepareSourceStage(),
        ParseDiffStage(),
        CompleteDiscoverFilesStage(),
        *deterministic,
        ExecuteValidationStage(),
        EvaluatePoliciesStage(),
        BuildEvidenceStage(),
        FinalizeStage(),
    ]
    return AnalysisPipeline(stages, on_progress=on_progress)


def run_local_analysis(
    source: Path,
    *,
    settings: Settings,
    output_directory: Path,
    diff_text: str = "",
    requirements: str = "",
    policy_document: str | None = None,
    runner: str = "native",
    validation_commands: list[list[str]] | None = None,
    source_type: str = "path",
    source_reference: str | None = None,
) -> LocalAnalysisResult:
    analysis_id = str(uuid4())
    context = AnalysisContext(
        analysis_id=analysis_id,
        workspace=source,
        diff_text=diff_text,
        requirement_text=requirements,
        data={
            "settings": settings,
            "source_type": source_type,
            "source_reference": source_reference or str(source),
            "runner": runner,
            "validation_commands": validation_commands or [],
            "evidence_output_directory": output_directory.resolve(),
            "policy_document": policy_document,
            "audit_events": [],
            "known_secrets": [
                settings.github_token.get_secret_value() if settings.github_token else "",
                settings.llm_api_key.get_secret_value() if settings.llm_api_key else "",
            ],
        },
    )
    try:
        result = build_pipeline().run(context)
        if result.status is not StageStatus.COMPLETED:
            raise RuntimeError(
                result.error_summary or "The local analysis pipeline did not complete"
            )
        archive = context.data.get("evidence_archive")
        if not isinstance(archive, Path):
            raise RuntimeError("The analysis completed without an evidence archive")
        risk = context.data.get("risk_assessment")
        return LocalAnalysisResult(
            analysis_id=analysis_id,
            verdict=str(context.data.get("verdict", "unknown")),
            risk_score=int(getattr(risk, "score", 0)),
            finding_count=len(context.findings),
            bundle_path=output_directory.resolve(),
            archive_path=archive,
            pipeline=result,
        )
    finally:
        cleanup_prepared_source(context)
