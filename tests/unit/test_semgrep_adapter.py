from __future__ import annotations

import json
import subprocess
from pathlib import Path

from proofstack_analyzers import SemgrepAdapter


class MockSemgrepRunner:
    def run(
        self, args: list[str], *, cwd: Path, timeout: float
    ) -> subprocess.CompletedProcess[str]:
        assert args[:2] == ["semgrep", "scan"]
        assert cwd.is_absolute()
        assert timeout == 2
        payload = {
            "results": [
                {
                    "check_id": "python.lang.security.eval",
                    "path": "app.py",
                    "start": {"line": 4},
                    "end": {"line": 4},
                    "extra": {
                        "severity": "ERROR",
                        "message": "Avoid eval",
                        "metadata": {"fix": "Use a parser"},
                    },
                }
            ]
        }
        return subprocess.CompletedProcess(args, 1, json.dumps(payload), "")


def test_semgrep_adapter_normalizes_mock_results(tmp_path: Path) -> None:
    result = SemgrepAdapter(runner=MockSemgrepRunner(), timeout_seconds=2).scan(tmp_path)

    assert result.status == "completed"
    assert result.findings[0].rule_id == "semgrep.python.lang.security.eval"
    assert result.findings[0].severity.value == "high"
    assert result.findings[0].start_line == 4
    assert result.findings[0].remediation == "Use a parser"
