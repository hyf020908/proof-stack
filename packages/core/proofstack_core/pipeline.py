"""Observable, failure-contained orchestration for deterministic analysis stages."""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from time import monotonic
from typing import Any, Protocol, runtime_checkable

from .models import Finding

LOGGER = logging.getLogger("proofstack.pipeline")


class StageStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(slots=True)
class StageResult:
    name: str
    status: StageStatus
    started_at: datetime
    completed_at: datetime
    duration_ms: int
    output: dict[str, Any] = field(default_factory=dict)
    findings: list[Finding] = field(default_factory=list)
    error_code: str | None = None
    user_message: str | None = None

    @classmethod
    def completed(
        cls,
        name: str,
        started_at: datetime,
        started_clock: float,
        *,
        output: Mapping[str, Any] | None = None,
        findings: Sequence[Finding] = (),
    ) -> StageResult:
        return cls(
            name=name,
            status=StageStatus.COMPLETED,
            started_at=started_at,
            completed_at=datetime.now(UTC),
            duration_ms=max(0, round((monotonic() - started_clock) * 1000)),
            output=dict(output or {}),
            findings=list(findings),
        )


@dataclass(slots=True)
class AnalysisContext:
    analysis_id: str
    workspace: Path
    diff_text: str = ""
    requirement_text: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    findings: list[Finding] = field(default_factory=list)
    stage_results: list[StageResult] = field(default_factory=list)
    progress: int = 0
    current_stage: str | None = None
    cancelled: bool = False

    def __post_init__(self) -> None:
        self.workspace = self.workspace.resolve()

    def cancel(self) -> None:
        self.cancelled = True


@runtime_checkable
class AnalysisStage(Protocol):
    name: str

    def run(self, context: AnalysisContext) -> StageResult:
        """Execute one isolated stage and return its standardized result."""


StageCallable = Callable[[AnalysisContext], tuple[Mapping[str, Any], Sequence[Finding]]]


@dataclass(slots=True)
class FunctionalStage:
    name: str
    function: StageCallable

    def run(self, context: AnalysisContext) -> StageResult:
        started_at = datetime.now(UTC)
        started_clock = monotonic()
        output, findings = self.function(context)
        return StageResult.completed(
            self.name,
            started_at,
            started_clock,
            output=output,
            findings=findings,
        )


@dataclass(slots=True)
class PipelineResult:
    analysis_id: str
    status: StageStatus
    stages: list[StageResult]
    findings: list[Finding]
    progress: int
    error_summary: str | None = None


ProgressCallback = Callable[[AnalysisContext, StageResult | None], None]


class AnalysisPipeline:
    def __init__(
        self,
        stages: Sequence[AnalysisStage],
        *,
        on_progress: ProgressCallback | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        if not stages:
            raise ValueError("An analysis pipeline requires at least one stage")
        names = [stage.name for stage in stages]
        if len(set(names)) != len(names):
            raise ValueError("Analysis stage names must be unique")
        self._stages = tuple(stages)
        self._on_progress = on_progress
        self._logger = logger or LOGGER

    def run(self, context: AnalysisContext) -> PipelineResult:
        total = len(self._stages)
        for index, stage in enumerate(self._stages):
            if context.cancelled:
                return self._cancelled(context)
            context.current_stage = stage.name
            context.progress = int(index * 100 / total)
            self._emit(context, None)
            self._logger.info(
                "analysis_stage_started",
                extra={"analysis_id": context.analysis_id, "stage": stage.name},
            )
            started_at = datetime.now(UTC)
            started_clock = monotonic()
            try:
                result = stage.run(context)
                if result.name != stage.name:
                    raise ValueError("A stage result name must match its stage")
            except Exception as exc:
                self._logger.exception(
                    "analysis_stage_failed",
                    extra={"analysis_id": context.analysis_id, "stage": stage.name},
                )
                result = StageResult(
                    name=stage.name,
                    status=StageStatus.FAILED,
                    started_at=started_at,
                    completed_at=datetime.now(UTC),
                    duration_ms=max(0, round((monotonic() - started_clock) * 1000)),
                    error_code="stage_execution_failed",
                    user_message=f"The {stage.name} stage could not be completed: {exc}",
                )
            context.stage_results.append(result)
            context.findings.extend(result.findings)
            context.data.update(result.output)
            context.progress = int((index + 1) * 100 / total)
            self._emit(context, result)
            self._logger.info(
                "analysis_stage_finished",
                extra={
                    "analysis_id": context.analysis_id,
                    "stage": stage.name,
                    "status": result.status,
                    "duration_ms": result.duration_ms,
                    "finding_count": len(result.findings),
                },
            )
            if result.status is StageStatus.FAILED:
                return PipelineResult(
                    analysis_id=context.analysis_id,
                    status=StageStatus.FAILED,
                    stages=list(context.stage_results),
                    findings=list(context.findings),
                    progress=context.progress,
                    error_summary=result.user_message,
                )
        context.current_stage = None
        return PipelineResult(
            analysis_id=context.analysis_id,
            status=StageStatus.COMPLETED,
            stages=list(context.stage_results),
            findings=list(context.findings),
            progress=100,
        )

    def _cancelled(self, context: AnalysisContext) -> PipelineResult:
        context.current_stage = None
        return PipelineResult(
            analysis_id=context.analysis_id,
            status=StageStatus.CANCELLED,
            stages=list(context.stage_results),
            findings=list(context.findings),
            progress=context.progress,
            error_summary="Analysis was cancelled before the next stage started.",
        )

    def _emit(self, context: AnalysisContext, result: StageResult | None) -> None:
        if self._on_progress is not None:
            self._on_progress(context, result)
