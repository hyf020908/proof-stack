"""CLI smoke tests for version, policy validation, and diagnostics."""

from pathlib import Path

from proofstack_cli.main import app
from typer.testing import CliRunner

runner = CliRunner()


def test_version_json_output() -> None:
    result = runner.invoke(app, ["--json", "version"])
    assert result.exit_code == 0
    assert '"version": "0.1.0"' in result.stdout


def test_policy_validate(tmp_path: Path) -> None:
    policy = tmp_path / "policy.yml"
    policy.write_text(
        """name: strict
version: 1
rules:
  - id: no-critical
    metric: findings.critical
    operator: eq
    value: 0
    outcome: fail
""",
        encoding="utf-8",
    )
    result = runner.invoke(app, ["--json", "policy", "validate", str(policy)])
    assert result.exit_code == 0
    assert '"valid": true' in result.stdout


def test_doctor_does_not_require_optional_tools() -> None:
    result = runner.invoke(app, ["--json", "doctor"])
    assert result.exit_code == 0
    assert '"python_supported": true' in result.stdout
