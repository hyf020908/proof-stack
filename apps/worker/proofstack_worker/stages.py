"""Application stages that connect source, execution, policy, and evidence adapters."""

from __future__ import annotations

import hashlib
import shutil
from collections.abc import Mapping, Sequence
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from time import monotonic
from typing import Any

from proofstack_analyzers import ChangeType, DiffDocument, DiffFile, SemgrepAdapter
from proofstack_analyzers.stages import DiscoverFilesStage, ScanSecurityStage
from proofstack_core import AnalysisContext, Finding, FindingCategory, Severity, StageResult
from proofstack_core.evidence import EvidenceBundleGenerator, EvidenceBundlePayload
from proofstack_policies import PolicyEngine, RiskFactors, RiskScorer, parse_policy
from proofstack_providers import (
    CommandSpec,
    DockerSandboxRunner,
    ExecutionPlan,
    GitHubSourceProvider,
    LocalSourceProvider,
    NativeSafeRunner,
    SafeZipSourceProvider,
    SourceLimits,
    SourceRequest,
)
from proofstack_providers import SourceType as ProviderSourceType
from proofstack_shared.config import Settings

DEFAULT_POLICY = """name: default
version: 1
rules:
  - id: no-critical-findings
    description: Critical findings are not allowed
    metric: findings.critical
    operator: eq
    value: 0
    outcome: fail
  - id: limit-high-findings
    description: No more than two high-severity findings
    metric: findings.high
    operator: lte
    value: 2
    outcome: fail
  - id: require-validation
    description: At least one validation command must pass
    metric: validation.passed
    operator: gte
    value: 1
    outcome: fail
  - id: requirement-coverage
    description: Requirement coverage must be at least 70 percent
    metric: requirements.coverage
    operator: gte
    value: 0.7
    outcome: warn
  - id: test-evidence
    description: Changed production code should have related tests
    metric: tests.evidence_score
    operator: gte
    value: 0.6
    outcome: warn
"""


def _completed(
    name: str,
    started_at: datetime,
    started_clock: float,
    *,
    output: Mapping[str, Any] | None = None,
    findings: Sequence[Finding] = (),
) -> StageResult:
    return StageResult.completed(
        name,
        started_at,
        started_clock,
        output=output,
        findings=findings,
    )


def _source_limits(settings: Settings) -> SourceLimits:
    return SourceLimits(
        max_repository_bytes=settings.max_repository_bytes,
        max_file_count=settings.max_file_count,
        max_diff_bytes=min(settings.max_repository_bytes, 10 * 1024 * 1024),
    )


def _read_source_files(
    root: Path, *, max_files: int, max_file_bytes: int = 2_000_000
) -> dict[str, str]:
    resolved_root = root.resolve()
    ignored = {".git", ".hg", ".svn", "node_modules", ".venv", "dist", "build"}
    result: dict[str, str] = {}
    for candidate in sorted(resolved_root.rglob("*")):
        try:
            relative = candidate.relative_to(resolved_root)
        except ValueError:
            continue
        if any(part in ignored for part in relative.parts):
            continue
        if candidate.is_symlink() or not candidate.is_file():
            continue
        if len(result) >= max_files:
            raise ValueError("Source file count exceeds the configured analysis limit")
        if candidate.stat().st_size > max_file_bytes:
            continue
        content = candidate.read_bytes()
        if b"\x00" in content[:8192]:
            continue
        result[relative.as_posix()] = content.decode("utf-8", errors="replace")
    return result


class PrepareSourceStage:
    name = "PREPARE_SOURCE"

    def run(self, context: AnalysisContext) -> StageResult:
        started_at = datetime.now(UTC)
        started_clock = monotonic()
        settings = context.data.get("settings")
        if not isinstance(settings, Settings):
            raise ValueError("Validated settings are required to prepare a source")
        source_type = str(context.data.get("source_type", "path"))
        reference = str(context.data.get("source_reference", ""))
        workspace_parent = settings.workspace_root.resolve()
        workspace_parent.mkdir(parents=True, exist_ok=True)
        limits = _source_limits(settings)
        previous_root: Path | None = None
        if source_type == "demo":
            demo_root = (Path.cwd() / reference).resolve()
            source_root = demo_root / "changed"
            previous_root = demo_root / "base"
            diff_path = demo_root / "change.diff"
            prepared = LocalSourceProvider().prepare(
                SourceRequest(
                    source_type=ProviderSourceType.DEMO,
                    source_path=source_root,
                    diff_path=diff_path if diff_path.is_file() else None,
                    limits=limits,
                )
            )
            if not context.requirement_text:
                requirement_path = demo_root / "requirements.md"
                if requirement_path.is_file():
                    context.requirement_text = requirement_path.read_text(encoding="utf-8")
            policy_path = demo_root / "policy.yml"
            if policy_path.is_file() and not context.data.get("policy_document"):
                context.data["policy_document"] = policy_path.read_text(encoding="utf-8")
        elif source_type in {"upload", "zip"}:
            prepared = SafeZipSourceProvider().prepare(
                SourceRequest(
                    source_type=ProviderSourceType.ZIP,
                    archive_path=Path(reference),
                    destination_parent=workspace_parent,
                    limits=limits,
                )
            )
        elif source_type == "github":
            token = settings.github_token.get_secret_value() if settings.github_token else ""
            prepared = GitHubSourceProvider(timeout_seconds=settings.command_timeout).prepare(
                SourceRequest(
                    source_type=ProviderSourceType.GITHUB,
                    github_url=reference,
                    destination_parent=workspace_parent,
                    github_token=token,
                    limits=limits,
                )
            )
        else:
            prepared = LocalSourceProvider().prepare(
                SourceRequest(
                    source_type=ProviderSourceType.PATH,
                    source_path=Path(reference) if reference else context.workspace,
                    limits=limits,
                )
            )
        context.workspace = prepared.root.resolve()
        context.diff_text = context.diff_text or prepared.diff_text
        if previous_root is not None and previous_root.is_dir():
            context.data["previous_files"] = _read_source_files(
                previous_root,
                max_files=settings.max_file_count,
            )
        context.data.update(
            {
                "prepared_source": prepared,
                "source_metadata": prepared.metadata,
                "base_revision": prepared.base_revision,
                "head_revision": prepared.head_revision,
                "cleanup_path": prepared.cleanup_path,
            }
        )
        return _completed(
            self.name,
            started_at,
            started_clock,
            output={"workspace": str(context.workspace)},
        )


class CompleteDiscoverFilesStage(DiscoverFilesStage):
    """Discover text files and treat a diff-less snapshot as an added source set."""

    def analyze(self, context: AnalysisContext) -> tuple[dict[str, Any], list[Finding]]:
        output, findings = super().analyze(context)
        current = context.data.get("diff_document")
        if not isinstance(current, DiffDocument) or not current.files:
            files = output.get("source_files", {})
            if isinstance(files, Mapping):
                output["diff_document"] = DiffDocument(
                    files=[
                        DiffFile(old_path=None, new_path=str(path), change_type=ChangeType.ADDED)
                        for path in sorted(files)
                    ]
                )
                output["changed_file_count"] = len(files)
        return output, findings


class CompleteSecurityStage(ScanSecurityStage):
    """Run built-in security checks and the explicitly enabled optional adapter."""

    def analyze(self, context: AnalysisContext) -> tuple[dict[str, Any], list[Finding]]:
        output, findings = super().analyze(context)
        settings = context.data.get("settings")
        if not isinstance(settings, Settings) or not settings.semgrep_enabled:
            output["semgrep_status"] = "disabled"
            return output, findings
        semgrep = SemgrepAdapter(timeout_seconds=min(settings.command_timeout, 300)).scan(
            context.workspace
        )
        output["semgrep_result"] = semgrep
        output["semgrep_status"] = semgrep.status
        return output, [*findings, *semgrep.findings]


class ExecuteValidationStage:
    name = "EXECUTE_VALIDATION"

    def run(self, context: AnalysisContext) -> StageResult:
        started_at = datetime.now(UTC)
        started_clock = monotonic()
        settings = context.data.get("settings")
        if not isinstance(settings, Settings):
            raise ValueError("Validated settings are required to execute validation")
        raw_commands = context.data.get("validation_commands")
        commands: list[CommandSpec] = []
        if isinstance(raw_commands, Sequence) and not isinstance(raw_commands, (str, bytes)):
            for index, value in enumerate(raw_commands):
                if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
                    args = tuple(str(item) for item in value)
                    if args:
                        commands.append(CommandSpec(args=args, label=f"validation-{index + 1}"))
        if not commands:
            commands = [
                CommandSpec(
                    args=("python3", "-m", "compileall", "-q", "."),
                    label="python-syntax",
                )
            ]
        plan = ExecutionPlan(
            working_directory=context.workspace,
            commands=tuple(commands),
            environment={"PYTHONHASHSEED": "0", "TZ": "UTC"},
            default_timeout_seconds=settings.command_timeout,
        )
        runner_name = str(context.data.get("runner", settings.runner))
        runner = (
            DockerSandboxRunner(enabled=True) if runner_name == "docker" else NativeSafeRunner()
        )
        result = runner.execute(plan)
        findings: list[Finding] = []
        for execution in result.executions:
            status_value = execution.status.value
            if status_value == "passed":
                continue
            severity = Severity.HIGH if status_value in {"failed", "timed_out"} else Severity.MEDIUM
            message = execution.stderr_excerpt or execution.stdout_excerpt or result.message
            fingerprint = hashlib.sha256(
                f"execution:{execution.command}:{status_value}".encode()
            ).hexdigest()
            findings.append(
                Finding(
                    category=FindingCategory.EXECUTION,
                    severity=severity,
                    title=f"Validation {status_value.replace('_', ' ')}",
                    description=(
                        f"The validation command {' '.join(execution.command)} was {status_value}. "
                        f"{message[:600]}"
                    ).strip(),
                    rule_id=f"execution.{status_value.replace('_', '-')}",
                    remediation=(
                        "Inspect the bounded output and repair or explicitly configure the "
                        "validation environment."
                    ),
                    fingerprint=fingerprint,
                    evidence={"command": list(execution.command), "status": status_value},
                )
            )
        return _completed(
            self.name,
            started_at,
            started_clock,
            output={"execution_result": result},
            findings=findings,
        )


def _severity_counts(findings: Sequence[Finding]) -> dict[str, int]:
    counts = {item.value: 0 for item in Severity}
    for finding in findings:
        counts[finding.severity.value] += 1
    return counts


class EvaluatePoliciesStage:
    name = "EVALUATE_POLICIES"

    def run(self, context: AnalysisContext) -> StageResult:
        started_at = datetime.now(UTC)
        started_clock = monotonic()
        findings = list(context.findings)
        severity = _severity_counts(findings)
        requirement_mapping = context.data.get("requirement_mapping")
        requirement_coverage = float(getattr(requirement_mapping, "coverage_score", 1.0))
        test_gap = context.data.get("test_gap_result")
        test_score = float(getattr(test_gap, "evidence_score", 1.0))
        execution = context.data.get("execution_result")
        executions = list(getattr(execution, "executions", []))
        passed = sum(getattr(item.status, "value", "") == "passed" for item in executions)
        failed = sum(
            getattr(item.status, "value", "") in {"failed", "timed_out"} for item in executions
        )
        metrics = {
            "findings": severity,
            "validation": {
                "passed": passed,
                "failed": failed,
                "total": len(executions),
            },
            "requirements": {"coverage": requirement_coverage},
            "tests": {"evidence_score": test_score},
        }
        policy_document = str(context.data.get("policy_document") or DEFAULT_POLICY)
        evaluation = PolicyEngine().evaluate(parse_policy(policy_document), metrics)
        policy_findings = []
        for decision in evaluation.decisions:
            if decision.outcome.value == "pass":
                continue
            severity_value = Severity.HIGH if decision.outcome.value == "fail" else Severity.MEDIUM
            policy_findings.append(
                Finding(
                    category=FindingCategory.POLICY,
                    severity=severity_value,
                    title=f"Policy rule {decision.outcome.value}",
                    description=decision.explanation,
                    rule_id=f"policy.{decision.rule_id}",
                    remediation=(
                        "Provide the missing evidence or update the reviewed policy intentionally."
                    ),
                    fingerprint=hashlib.sha256(
                        f"policy:{decision.rule_id}:{decision.outcome.value}".encode()
                    ).hexdigest(),
                    evidence={
                        "observed": decision.observed_value,
                        "expected": decision.expected_value,
                    },
                )
            )
        document = context.data.get("diff_document")
        diff_files = list(document.files) if isinstance(document, DiffDocument) else []
        analyses = context.data.get("python_analyses", [])
        high_complexity = sum(
            symbol.complexity >= 10
            for analysis in analyses
            for symbol in getattr(analysis, "symbols", [])
        )
        impact = context.data.get("impact_result")
        dependency = context.data.get("dependency_result")
        configuration = context.data.get("configuration_result")
        database = context.data.get("database_result")
        secret_count = sum(
            "secret" in item.rule_id or "credential" in item.rule_id for item in findings
        )
        risk = RiskScorer().score(
            RiskFactors(
                changed_files=len(diff_files),
                additions=int(getattr(document, "additions", 0)),
                deletions=int(getattr(document, "deletions", 0)),
                high_complexity_symbols=high_complexity,
                high_fan_in_symbols=len(getattr(impact, "high_fan_in_symbols", [])),
                breaking_api_changes=sum(
                    bool(getattr(item, "breaking", False))
                    for item in getattr(impact, "route_changes", [])
                ),
                database_migrations=sum(item.is_migration for item in diff_files)
                + len(getattr(database, "operations", [])),
                dependency_changes=len(getattr(dependency, "changes", [])),
                critical_findings=severity["critical"],
                high_findings=severity["high"],
                medium_findings=severity["medium"],
                low_findings=severity["low"],
                secrets_detected=secret_count,
                test_evidence_score=test_score,
                requirement_coverage=requirement_coverage,
                failed_validations=failed,
                config_drifts=(
                    len(getattr(configuration, "undocumented_variables", []))
                    + len(getattr(configuration, "removed_keys", []))
                    + len(getattr(configuration, "compose_drift", []))
                ),
                ci_files_changed=sum(item.is_ci for item in diff_files),
            )
        )
        return _completed(
            self.name,
            started_at,
            started_clock,
            output={
                "metrics": metrics,
                "policy_evaluation": evaluation,
                "risk_assessment": risk,
                "verdict": evaluation.verdict.value,
            },
            findings=policy_findings,
        )


def to_jsonable(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return to_jsonable(asdict(value))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    if isinstance(value, Mapping):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [to_jsonable(item) for item in value]
    return value


def changed_files_payload(context: AnalysisContext) -> list[dict[str, Any]]:
    document = context.data.get("diff_document")
    if not isinstance(document, DiffDocument):
        return []
    return [
        {
            "path": item.path,
            "old_path": item.old_path,
            "new_path": item.new_path,
            "change_type": item.change_type.value,
            "additions": item.additions,
            "deletions": item.deletions,
            "language": item.language,
            "is_test": item.is_test,
            "is_config": item.is_config,
            "is_dependency_manifest": item.is_dependency_manifest,
            "is_migration": item.is_migration,
            "is_ci": item.is_ci,
            "is_binary": item.is_binary,
        }
        for item in document.files
    ]


def requirements_payload(context: AnalysisContext) -> list[dict[str, Any]]:
    requirements = context.data.get("requirements", [])
    mapping_result = context.data.get("requirement_mapping")
    mappings = {item.requirement_id: item for item in getattr(mapping_result, "mappings", [])}
    result: list[dict[str, Any]] = []
    for requirement in requirements:
        mapping = mappings.get(requirement.id)
        result.append(
            {
                "id": requirement.id,
                "title": requirement.title,
                "description": requirement.description,
                "acceptance_criteria": list(requirement.acceptance_criteria),
                "source": requirement.source,
                "coverage_score": float(getattr(mapping, "score", 0.0)),
                "supported": bool(getattr(mapping, "supported", False)),
                "evidence": to_jsonable(getattr(mapping, "evidence", [])),
                "changed_files": list(getattr(mapping, "changed_files", [])),
                "changed_symbols": list(getattr(mapping, "changed_symbols", [])),
                "tests": list(getattr(mapping, "tests", [])),
            }
        )
    return result


class BuildEvidenceStage:
    name = "BUILD_EVIDENCE"

    def run(self, context: AnalysisContext) -> StageResult:
        started_at = datetime.now(UTC)
        started_clock = monotonic()
        output_directory = context.data.get("evidence_output_directory")
        if not isinstance(output_directory, Path):
            raise ValueError("An evidence output directory is required")
        risk = context.data.get("risk_assessment")
        evaluation = context.data.get("policy_evaluation")
        execution = context.data.get("execution_result")
        analysis_payload = {
            "id": context.analysis_id,
            "status": "completed",
            "verdict": context.data.get("verdict", "unknown"),
            "risk_score": int(getattr(risk, "score", 0)),
            "risk": to_jsonable(risk),
            "progress": context.progress,
            "source_type": context.data.get("source_type"),
            "source_reference": context.data.get("source_reference"),
            "base_revision": context.data.get("base_revision"),
            "head_revision": context.data.get("head_revision"),
        }
        payload = EvidenceBundlePayload(
            analysis=analysis_payload,
            changed_files=changed_files_payload(context),
            requirements=requirements_payload(context),
            dependency_graph=to_jsonable(
                context.data.get("graph_data", {"nodes": [], "edges": []})
            ),
            findings=[to_jsonable(item) for item in context.findings],
            test_results=to_jsonable(getattr(execution, "executions", [])),
            policy_decisions=to_jsonable(getattr(evaluation, "decisions", [])),
            audit_events=to_jsonable(context.data.get("audit_events", [])),
            input_summary={
                "source_type": context.data.get("source_type"),
                "source_reference": context.data.get("source_reference"),
                "diff_sha256": hashlib.sha256(context.diff_text.encode()).hexdigest(),
                "requirements_sha256": hashlib.sha256(
                    context.requirement_text.encode()
                ).hexdigest(),
            },
        )
        generator = EvidenceBundleGenerator()
        result = generator.generate(
            output_directory,
            payload,
            known_secrets=tuple(
                str(item) for item in context.data.get("known_secrets", []) if item
            ),
        )
        archive_path = generator.create_zip(result.path)
        return _completed(
            self.name,
            started_at,
            started_clock,
            output={"evidence_result": result, "evidence_archive": archive_path},
        )


class FinalizeStage:
    name = "FINALIZE"

    def run(self, context: AnalysisContext) -> StageResult:
        started_at = datetime.now(UTC)
        started_clock = monotonic()
        return _completed(
            self.name,
            started_at,
            started_clock,
            output={
                "finalized": True,
                "final_verdict": context.data.get("verdict", "unknown"),
                "final_risk_score": int(getattr(context.data.get("risk_assessment"), "score", 0)),
            },
        )


def cleanup_prepared_source(context: AnalysisContext) -> None:
    cleanup_path = context.data.get("cleanup_path")
    settings = context.data.get("settings")
    if not isinstance(cleanup_path, Path) or not isinstance(settings, Settings):
        return
    candidate = cleanup_path.resolve()
    allowed = settings.workspace_root.resolve()
    try:
        candidate.relative_to(allowed)
    except ValueError:
        return
    if candidate.is_dir() and candidate != allowed:
        shutil.rmtree(candidate)
