"""Deterministic analysis engines shipped with ProofStack."""

from .configuration import ConfigurationAnalyzer, ConfigurationResult, EnvironmentReference
from .database import DatabaseImpactAnalyzer, DatabaseImpactResult
from .dependencies import Dependency, DependencyAnalysisResult, DependencyAnalyzer, DependencyChange
from .diff import (
    ChangeType,
    DiffDocument,
    DiffFile,
    DiffHunk,
    DiffLine,
    DiffLineType,
    DiffParseError,
    UnifiedDiffParser,
    parse_unified_diff,
)
from .graph import BlastRadius, DependencyGraph, GraphEdge, GraphNode, PythonGraphBuilder
from .impact import ImpactAnalyzer, ImpactResult
from .python_ast import (
    AnalyzerWarning,
    CallReference,
    ImportReference,
    LanguageAnalyzer,
    PythonAnalysis,
    PythonAnalyzer,
    PythonSymbol,
)
from .requirements import (
    DeterministicRequirementMapper,
    EvidenceCandidate,
    EvidenceMatch,
    MockRequirementMapper,
    OpenAICompatibleConfig,
    OpenAICompatibleRequirementMapper,
    RequirementMapperProvider,
    RequirementMapping,
    RequirementMappingResult,
    RequirementSpec,
    build_evidence_candidates,
)
from .routes import FastAPIRoute, FastAPIRouteExtractor, RouteChange, compare_routes
from .security import (
    DangerousPatternScanner,
    FileSecurityScanner,
    SecretScanner,
    SecurityAnalyzer,
    SecurityScanResult,
)
from .semgrep import SemgrepAdapter, SemgrepResult
from .stages import default_analysis_stages, parse_requirements_markdown
from .test_gaps import SuggestedTest, TestCaseEvidence, TestGapAnalyzer, TestGapResult

__all__ = [
    "AnalyzerWarning",
    "BlastRadius",
    "CallReference",
    "ChangeType",
    "ConfigurationAnalyzer",
    "ConfigurationResult",
    "DangerousPatternScanner",
    "DatabaseImpactAnalyzer",
    "DatabaseImpactResult",
    "Dependency",
    "DependencyAnalysisResult",
    "DependencyAnalyzer",
    "DependencyChange",
    "DependencyGraph",
    "DeterministicRequirementMapper",
    "DiffDocument",
    "DiffFile",
    "DiffHunk",
    "DiffLine",
    "DiffLineType",
    "DiffParseError",
    "EnvironmentReference",
    "EvidenceCandidate",
    "EvidenceMatch",
    "FastAPIRoute",
    "FastAPIRouteExtractor",
    "FileSecurityScanner",
    "GraphEdge",
    "GraphNode",
    "ImpactAnalyzer",
    "ImpactResult",
    "ImportReference",
    "LanguageAnalyzer",
    "MockRequirementMapper",
    "OpenAICompatibleConfig",
    "OpenAICompatibleRequirementMapper",
    "PythonAnalysis",
    "PythonAnalyzer",
    "PythonGraphBuilder",
    "PythonSymbol",
    "RequirementMapperProvider",
    "RequirementMapping",
    "RequirementMappingResult",
    "RequirementSpec",
    "RouteChange",
    "SecretScanner",
    "SecurityAnalyzer",
    "SecurityScanResult",
    "SemgrepAdapter",
    "SemgrepResult",
    "SuggestedTest",
    "TestCaseEvidence",
    "TestGapAnalyzer",
    "TestGapResult",
    "UnifiedDiffParser",
    "build_evidence_candidates",
    "compare_routes",
    "default_analysis_stages",
    "parse_requirements_markdown",
    "parse_unified_diff",
]
