"""Secure source and execution adapters for ProofStack."""

from .archive import SafeZipExtractor, SafeZipSourceProvider
from .github import GitHubSourceProvider, parse_github_url
from .runners import (
    CommandPolicy,
    CommandRejectedError,
    CommandSpec,
    DockerSandboxRunner,
    ExecutionPlan,
    ExecutionResult,
    ExecutionRunner,
    NativeSafeRunner,
)
from .source import (
    LocalSourceProvider,
    PreparedSource,
    SourceLimits,
    SourcePreparationError,
    SourceProvider,
    SourceRequest,
    SourceType,
    read_optional_diff,
    validate_source_tree,
)

__all__ = [
    "CommandPolicy",
    "CommandRejectedError",
    "CommandSpec",
    "DockerSandboxRunner",
    "ExecutionPlan",
    "ExecutionResult",
    "ExecutionRunner",
    "GitHubSourceProvider",
    "LocalSourceProvider",
    "NativeSafeRunner",
    "PreparedSource",
    "SafeZipExtractor",
    "SafeZipSourceProvider",
    "SourceLimits",
    "SourcePreparationError",
    "SourceProvider",
    "SourceRequest",
    "SourceType",
    "parse_github_url",
    "read_optional_diff",
    "validate_source_tree",
]
