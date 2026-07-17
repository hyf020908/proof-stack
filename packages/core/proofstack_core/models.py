"""Framework-neutral objects shared by analysis, policy, and evidence code."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


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


class Severity(StrEnum):
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


class Verdict(StrEnum):
    PASS = "pass"  # noqa: S105
    WARN = "warn"
    FAIL = "fail"
    UNKNOWN = "unknown"


@dataclass(slots=True)
class Finding:
    category: FindingCategory
    severity: Severity
    title: str
    description: str
    rule_id: str
    remediation: str
    fingerprint: str
    file_path: str | None = None
    start_line: int | None = None
    end_line: int | None = None
    evidence: dict[str, Any] = field(default_factory=dict)
    status: FindingStatus = FindingStatus.OPEN
    id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class TestExecutionRecord:
    command: tuple[str, ...]
    status: TestStatus
    exit_code: int | None
    duration_ms: int
    stdout_excerpt: str = ""
    stderr_excerpt: str = ""
    timed_out: bool = False
    environment: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["command"] = list(self.command)
        return value
