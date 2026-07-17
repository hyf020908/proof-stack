"""Optional Semgrep adapter that normalizes output without making it mandatory."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from proofstack_core import Finding, FindingCategory, Severity


@dataclass(slots=True)
class SemgrepResult:
    status: str
    findings: list[Finding]
    message: str


class SemgrepCommandRunner(Protocol):
    def run(
        self, args: list[str], *, cwd: Path, timeout: float
    ) -> subprocess.CompletedProcess[str]:
        """Execute a fixed Semgrep argument array."""


class SubprocessSemgrepRunner:
    def run(
        self, args: list[str], *, cwd: Path, timeout: float
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(  # noqa: S603
            args,
            cwd=cwd,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
        )


class SemgrepAdapter:
    def __init__(
        self, *, runner: SemgrepCommandRunner | None = None, timeout_seconds: float = 60.0
    ) -> None:
        self.runner = runner or SubprocessSemgrepRunner()
        self.timeout_seconds = timeout_seconds

    def scan(self, root: Path, *, config: str = "auto") -> SemgrepResult:
        if isinstance(self.runner, SubprocessSemgrepRunner) and shutil.which("semgrep") is None:
            return SemgrepResult(
                "unavailable", [], "Semgrep is not installed; built-in scanners still ran."
            )
        try:
            process = self.runner.run(
                ["semgrep", "scan", "--json", "--config", config, "--disable-version-check", "."],
                cwd=root.resolve(),
                timeout=self.timeout_seconds,
            )
        except (OSError, subprocess.TimeoutExpired):
            return SemgrepResult(
                "unavailable", [], "Semgrep could not complete within the configured limit."
            )
        try:
            data = json.loads(process.stdout or "{}")
        except json.JSONDecodeError:
            return SemgrepResult("failed", [], "Semgrep returned output that could not be parsed.")
        findings = [_convert(item) for item in data.get("results", []) if isinstance(item, dict)]
        status = "completed" if process.returncode in {0, 1} else "failed"
        return SemgrepResult(
            status,
            findings,
            "Semgrep scan completed." if status == "completed" else "Semgrep scan failed.",
        )


def _convert(item: dict[str, object]) -> Finding:
    extra = _object_mapping(item.get("extra"))
    metadata = _object_mapping(extra.get("metadata"))
    severity_name = str(extra.get("severity", "WARNING")).lower()
    severity = {
        "error": Severity.HIGH,
        "critical": Severity.CRITICAL,
        "warning": Severity.MEDIUM,
        "info": Severity.LOW,
    }.get(severity_name, Severity.MEDIUM)
    path = str(item.get("path", "")) or None
    start = _object_mapping(item.get("start"))
    end = _object_mapping(item.get("end"))
    start_line = _line_number(start.get("line"))
    end_line = _line_number(end.get("line")) or start_line
    rule_id = f"semgrep.{item.get('check_id', 'unknown')}"
    message = str(extra.get("message", "Semgrep reported a code pattern."))
    fingerprint = hashlib.sha256(f"{rule_id}:{path}:{start_line}:{message}".encode()).hexdigest()
    return Finding(
        category=FindingCategory.SECURITY,
        severity=severity,
        title=str(item.get("check_id", "Semgrep finding")),
        description=message,
        rule_id=rule_id,
        remediation=str(
            metadata.get("fix", "Review the matched code and apply the rule guidance.")
        ),
        fingerprint=fingerprint,
        file_path=path,
        start_line=start_line,
        end_line=end_line,
        evidence={"engine": "semgrep"},
    )


def _object_mapping(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    return {str(key): item for key, item in value.items()}


def _line_number(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, str) and value.isdigit():
        parsed = int(value)
        return parsed if parsed > 0 else None
    return None
