"""Stable enumerations shared by persistence, APIs, and analyzers."""

from enum import StrEnum


class Role(StrEnum):
    OWNER = "owner"
    MAINTAINER = "maintainer"
    REVIEWER = "reviewer"
    VIEWER = "viewer"


class AnalysisStatus(StrEnum):
    QUEUED = "queued"
    PREPARING = "preparing"
    ANALYZING = "analyzing"
    TESTING = "testing"
    EVALUATING = "evaluating"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Verdict(StrEnum):
    PASS = "pass"  # noqa: S105 - This is a verdict label.
    WARN = "warn"
    FAIL = "fail"
    UNKNOWN = "unknown"


class SourceType(StrEnum):
    DEMO = "demo"
    UPLOAD = "upload"
    GITHUB = "github"
    PATH = "path"
    DIFF = "diff"


class FindingCategory(StrEnum):
    REQUIREMENT = "requirement"
    IMPACT = "impact"
    TEST = "test"
    SECURITY = "security"
    DEPENDENCY = "dependency"
    CONFIGURATION = "configuration"
    COMPATIBILITY = "compatibility"
    EXECUTION = "execution"
    POLICY = "policy"


class FindingSeverity(StrEnum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class FindingStatus(StrEnum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    FALSE_POSITIVE = "false_positive"


class TestStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    UNAVAILABLE = "unavailable"
    TIMED_OUT = "timed_out"


class PolicyOutcome(StrEnum):
    PASS = "pass"  # noqa: S105 - This is a policy outcome label.
    WARN = "warn"
    FAIL = "fail"
