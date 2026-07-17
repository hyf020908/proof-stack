"""Composable pipeline stages for the offline deterministic analysis path."""

from __future__ import annotations

import hashlib
import re
from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from time import monotonic
from typing import Any

from proofstack_core import (
    AnalysisContext,
    Finding,
    FindingCategory,
    Severity,
    StageResult,
)

from .configuration import ConfigurationAnalyzer
from .database import DatabaseImpactAnalyzer
from .dependencies import DependencyAnalyzer
from .diff import DiffDocument, parse_unified_diff
from .graph import PythonGraphBuilder
from .impact import ImpactAnalyzer
from .python_ast import PythonAnalysis, PythonAnalyzer
from .requirements import (
    DeterministicRequirementMapper,
    RequirementSpec,
    build_evidence_candidates,
)
from .routes import FastAPIRouteExtractor
from .security import SecurityAnalyzer
from .test_gaps import TestGapAnalyzer


class DeterministicStage(ABC):
    name: str

    def run(self, context: AnalysisContext) -> StageResult:
        started_at = datetime.now(UTC)
        started_clock = monotonic()
        output, findings = self.analyze(context)
        return StageResult.completed(
            self.name,
            started_at,
            started_clock,
            output=output,
            findings=findings,
        )

    @abstractmethod
    def analyze(self, context: AnalysisContext) -> tuple[dict[str, Any], list[Finding]]:
        """Return stage output and normalized findings."""


class DiscoverFilesStage(DeterministicStage):
    name = "DISCOVER_FILES"

    def __init__(self, *, max_files: int = 20_000, max_file_bytes: int = 2_000_000) -> None:
        self.max_files = max_files
        self.max_file_bytes = max_file_bytes

    def analyze(self, context: AnalysisContext) -> tuple[dict[str, Any], list[Finding]]:
        files: dict[str, str] = {}
        skipped_binary = 0
        ignored = {".git", ".hg", ".svn", "node_modules", ".venv", "dist", "build"}
        for path in sorted(context.workspace.rglob("*")):
            if any(part in ignored for part in path.relative_to(context.workspace).parts):
                continue
            if path.is_symlink() or not path.is_file() or path.stat().st_size > self.max_file_bytes:
                continue
            if len(files) >= self.max_files:
                raise ValueError("Source file count exceeds the analysis limit")
            content = path.read_bytes()
            if b"\x00" in content[:8192]:
                skipped_binary += 1
                continue
            relative = path.relative_to(context.workspace).as_posix()
            files[relative] = content.decode("utf-8", errors="replace")
        return {
            "source_files": files,
            "file_count": len(files),
            "binary_files_skipped": skipped_binary,
        }, []


class ParseDiffStage(DeterministicStage):
    name = "PARSE_DIFF"

    def analyze(self, context: AnalysisContext) -> tuple[dict[str, Any], list[Finding]]:
        document = (
            parse_unified_diff(context.diff_text) if context.diff_text.strip() else DiffDocument()
        )
        return {
            "diff_document": document,
            "changed_file_count": len(document.files),
            "diff_additions": document.additions,
            "diff_deletions": document.deletions,
        }, []


class ExtractSymbolsStage(DeterministicStage):
    name = "EXTRACT_SYMBOLS"

    def __init__(self, analyzer: PythonAnalyzer | None = None) -> None:
        self.analyzer = analyzer or PythonAnalyzer()

    def analyze(self, context: AnalysisContext) -> tuple[dict[str, Any], list[Finding]]:
        files = _files(context)
        analyses = [
            self.analyzer.analyze_source(source, path=path)
            for path, source in sorted(files.items())
            if path.endswith(".py")
        ]
        previous_files = context.data.get("previous_files", {})
        previous_analyses = (
            [
                self.analyzer.analyze_source(source, path=path)
                for path, source in sorted(previous_files.items())
                if path.endswith(".py")
            ]
            if isinstance(previous_files, Mapping)
            else []
        )
        findings: list[Finding] = []
        for analysis in analyses:
            for warning in analysis.warnings:
                findings.append(
                    _finding(
                        FindingCategory.IMPACT,
                        warning.rule_id,
                        Severity.MEDIUM,
                        "Python analysis warning",
                        warning.message,
                        warning.path,
                        warning.line,
                        "Use static imports and valid syntax so the impact graph remains complete.",
                    )
                )
        return {
            "python_analyses": analyses,
            "previous_python_analyses": previous_analyses,
        }, findings


class BuildDependencyGraphStage(DeterministicStage):
    name = "BUILD_DEPENDENCY_GRAPH"

    def analyze(self, context: AnalysisContext) -> tuple[dict[str, Any], list[Finding]]:
        analyses = _analyses(context)
        diff_document = _diff(context)
        by_path = {analysis.path: analysis for analysis in analyses}
        changed_symbols: list[str] = []
        analyzer = PythonAnalyzer()
        for diff_file in diff_document.files:
            analysis = by_path.get(diff_file.path)
            if analysis:
                changed_symbols.extend(
                    symbol.qualified_name
                    for symbol in analyzer.changed_symbols(analysis, diff_file)
                )
        graph = PythonGraphBuilder().build(analyses, changed_symbols=changed_symbols)
        radius = graph.blast_radius(f"symbol:{name}" for name in changed_symbols)
        return {
            "dependency_graph": graph,
            "changed_symbols": sorted(set(changed_symbols)),
            "blast_radius": radius,
            "graph_data": graph.to_visualization(blast_radius=radius),
        }, []


class MapRequirementsStage(DeterministicStage):
    name = "MAP_REQUIREMENTS"

    def analyze(self, context: AnalysisContext) -> tuple[dict[str, Any], list[Finding]]:
        raw_requirements = context.data.get("requirements")
        requirements = _coerce_requirements(raw_requirements, context.requirement_text)
        files = _files(context)
        diff_document = _diff(context)
        changed_files = [item.path for item in diff_document.files] or list(files)
        tests = [path for path in files if _is_test_path(path)]
        routes = [
            f"{route.method} {route.path}"
            for path, source in files.items()
            if path.endswith(".py")
            for route in FastAPIRouteExtractor().extract(source)
        ]
        candidates = build_evidence_candidates(
            changed_files=changed_files,
            changed_symbols=context.data.get("changed_symbols", []),
            tests=tests,
            routes=routes,
            file_contents=files,
        )
        result = DeterministicRequirementMapper().map_requirements(requirements, candidates)
        findings = [
            _finding(
                FindingCategory.REQUIREMENT,
                "requirement.unsupported",
                Severity.MEDIUM,
                "Requirement lacks supporting evidence",
                f"Requirement {requirement_id} has no strong link to changed code or tests.",
                None,
                None,
                (
                    "Add an implementation and a test that explicitly reference the "
                    "acceptance criterion."
                ),
            )
            for requirement_id in result.unsupported_requirement_ids
        ]
        return {"requirements": requirements, "requirement_mapping": result}, findings


class AnalyzeImpactStage(DeterministicStage):
    name = "ANALYZE_IMPACT"

    def analyze(self, context: AnalysisContext) -> tuple[dict[str, Any], list[Finding]]:
        files = _files(context)
        previous_files = context.data.get("previous_files", {})
        extractor = FastAPIRouteExtractor()
        current_routes = [
            route
            for path, source in files.items()
            if path.endswith(".py")
            for route in extractor.extract(source)
        ]
        previous_routes = (
            [
                route
                for path, source in previous_files.items()
                if path.endswith(".py")
                for route in extractor.extract(source)
            ]
            if isinstance(previous_files, Mapping)
            else []
        )
        result = ImpactAnalyzer().analyze(
            context.data.get("previous_python_analyses", []),
            _analyses(context),
            context.data["dependency_graph"],
            context.data.get("changed_symbols", []),
            previous_routes=previous_routes,
            current_routes=current_routes,
        )
        return {"impact_result": result, "fastapi_routes": current_routes}, result.findings


class AnalyzeTestGapsStage(DeterministicStage):
    name = "ANALYZE_TEST_GAPS"

    def analyze(self, context: AnalysisContext) -> tuple[dict[str, Any], list[Finding]]:
        files = _files(context)
        document = _diff(context)
        changed_sources = [
            item.path for item in document.files if not item.is_test and item.path.endswith(".py")
        ]
        changed_tests = [item.path for item in document.files if item.is_test]
        impact = context.data.get("impact_result")
        public_api_sources = []
        if impact is not None and impact.route_changes:
            public_api_sources = changed_sources
        result = TestGapAnalyzer().analyze(
            files,
            changed_sources,
            changed_symbols=context.data.get("changed_symbols", []),
            high_risk_sources=[item.path for item in document.files if item.is_security_sensitive],
            public_api_sources=public_api_sources,
            changed_tests=changed_tests,
            requirement_mapping=context.data.get("requirement_mapping"),
        )
        return {
            "test_gap_result": result,
            "test_evidence_score": result.evidence_score,
        }, result.findings


class ScanSecurityStage(DeterministicStage):
    name = "SCAN_SECURITY"

    def analyze(self, context: AnalysisContext) -> tuple[dict[str, Any], list[Finding]]:
        files = _files(context)
        modes: dict[str, int] = {}
        for path in files:
            candidate = context.workspace / path
            if candidate.is_file() and not candidate.is_symlink():
                modes[path] = candidate.stat().st_mode & 0o777
        result = SecurityAnalyzer().scan(files, modes=modes)
        return {"security_result": result}, result.findings


class ScanDependenciesStage(DeterministicStage):
    name = "SCAN_DEPENDENCIES"

    def analyze(self, context: AnalysisContext) -> tuple[dict[str, Any], list[Finding]]:
        result = DependencyAnalyzer().analyze(
            _files(context), previous_files=_mapping(context.data.get("previous_files"))
        )
        return {"dependency_result": result}, result.findings


class DetectConfigChangesStage(DeterministicStage):
    name = "DETECT_CONFIG_CHANGES"

    def analyze(self, context: AnalysisContext) -> tuple[dict[str, Any], list[Finding]]:
        result = ConfigurationAnalyzer().analyze(
            _files(context), previous_files=_mapping(context.data.get("previous_files"))
        )
        database = DatabaseImpactAnalyzer().analyze(
            _files(context), previous_files=_mapping(context.data.get("previous_files"))
        )
        return {"configuration_result": result, "database_result": database}, [
            *result.findings,
            *database.findings,
        ]


def default_analysis_stages() -> list[DeterministicStage]:
    return [
        DiscoverFilesStage(),
        ParseDiffStage(),
        ExtractSymbolsStage(),
        BuildDependencyGraphStage(),
        MapRequirementsStage(),
        AnalyzeImpactStage(),
        AnalyzeTestGapsStage(),
        ScanSecurityStage(),
        ScanDependenciesStage(),
        DetectConfigChangesStage(),
    ]


def _files(context: AnalysisContext) -> dict[str, str]:
    return _mapping(context.data.get("source_files"))


def _mapping(value: Any) -> dict[str, str]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): str(item) for key, item in value.items()}


def _analyses(context: AnalysisContext) -> list[PythonAnalysis]:
    value = context.data.get("python_analyses", [])
    return (
        [item for item in value if isinstance(item, PythonAnalysis)]
        if isinstance(value, Sequence)
        else []
    )


def _diff(context: AnalysisContext) -> DiffDocument:
    value = context.data.get("diff_document")
    return value if isinstance(value, DiffDocument) else DiffDocument()


def _coerce_requirements(value: Any, markdown: str) -> list[RequirementSpec]:
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        requirements = [item for item in value if isinstance(item, RequirementSpec)]
        if requirements:
            return requirements
    return parse_requirements_markdown(markdown)


def parse_requirements_markdown(markdown: str) -> list[RequirementSpec]:
    sections: list[tuple[str, list[str]]] = []
    current_title = ""
    current_lines: list[str] = []
    for line in markdown.splitlines():
        heading = re.match(r"^#{1,6}\s+(.+)$", line.strip())
        if heading:
            if current_title or current_lines:
                sections.append(
                    (current_title or f"Requirement {len(sections) + 1}", current_lines)
                )
            current_title = heading.group(1).strip()
            current_lines = []
        elif line.strip():
            current_lines.append(line.strip().lstrip("-* "))
    if current_title or current_lines:
        sections.append((current_title or "Requirement 1", current_lines))
    return [
        RequirementSpec(
            id=f"REQ-{index:03d}",
            title=title,
            description=" ".join(lines),
            acceptance_criteria=tuple(
                line
                for line in lines
                if re.match(r"(?i)(given|when|then|accept|must|should)", line)
            ),
            source="markdown",
        )
        for index, (title, lines) in enumerate(sections, 1)
    ]


def _is_test_path(path: str) -> bool:
    lowered = path.lower()
    return bool(
        re.search(r"(^|/)(tests?|specs?)(/|$)|(^|/)(test_|.*(_test|\.spec|\.test)\.)", lowered)
    )


def _finding(
    category: FindingCategory,
    rule_id: str,
    severity: Severity,
    title: str,
    description: str,
    path: str | None,
    line: int | None,
    remediation: str,
) -> Finding:
    fingerprint = hashlib.sha256(f"{rule_id}:{path}:{line}:{description}".encode()).hexdigest()
    return Finding(
        category=category,
        severity=severity,
        title=title,
        description=description,
        rule_id=rule_id,
        remediation=remediation,
        fingerprint=fingerprint,
        file_path=path,
        start_line=line,
        end_line=line,
    )
