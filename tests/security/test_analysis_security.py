from __future__ import annotations

import stat
import zipfile
from pathlib import Path

import pytest
from proofstack_analyzers import DangerousPatternScanner, FileSecurityScanner, SecretScanner
from proofstack_providers import (
    CommandPolicy,
    CommandRejectedError,
    CommandSpec,
    ExecutionPlan,
    NativeSafeRunner,
    SafeZipSourceProvider,
    SourceLimits,
    SourcePreparationError,
    SourceRequest,
    SourceType,
    parse_github_url,
)


def test_secret_scanner_redacts_values_and_ignores_placeholders() -> None:
    secret = "ghp_1234567890abcdefghijklmnopqrstuvwxyzAB"
    source = f'GITHUB_TOKEN = "{secret}"\nEXAMPLE_TOKEN = "fake-token-placeholder"\n'
    findings = SecretScanner().scan(source, "app/config.py")

    assert findings
    serialized = repr([item.to_dict() for item in findings])
    assert secret not in serialized
    assert "[" not in findings[0].evidence["masked_value"]
    assert "fake-token-placeholder" not in serialized


def test_dangerous_pattern_scanner_covers_required_python_risks() -> None:
    source = """
import hashlib, os, pickle, subprocess, tempfile, yaml
eval(user_input)
exec(user_input)
pickle.loads(payload)
yaml.load(payload)
subprocess.run(["tool"], shell=True)
os.system("tool")
tempfile.mktemp()
hashlib.md5(data)
client.get(url, verify=False)
cursor.execute(f"SELECT * FROM users WHERE id={user_id}")
open(request.path)
"""
    rules = {item.rule_id for item in DangerousPatternScanner().scan(source, "app/unsafe.py")}

    assert {
        "python.eval",
        "python.exec",
        "python.pickle-loads",
        "python.unsafe-yaml-load",
        "python.subprocess-shell",
        "python.os-system",
        "python.insecure-tempfile",
        "python.weak-hash",
        "python.tls-verification-disabled",
        "python.sql-string-concatenation",
        "python.path-traversal-input",
    } <= rules


def test_file_scanner_detects_docker_workflow_compose_and_permissions() -> None:
    files = {
        "Dockerfile": "FROM python:latest\nRUN chmod 777 /app\nUSER root\n",
        ".github/workflows/ci.yml": "steps:\n  - uses: actions/checkout@v4\n",
        "compose.yml": "environment:\n  PASSWORD: production-value\nports:\n  - 5678:5678\n",
        ".env": "TOKEN=production-value\n",
    }
    findings = FileSecurityScanner().scan(files, modes={"compose.yml": 0o666})
    rules = {item.rule_id for item in findings}

    assert {
        "docker.floating-base-image",
        "docker.root-user",
        "docker.world-writable",
        "github-action.unpinned",
        "compose.literal-secret",
        "compose.debug-port",
        "file.committed-env",
        "file.world-writable",
    } <= rules


def test_zip_provider_rejects_zip_slip_and_symbolic_links(tmp_path: Path) -> None:
    traversal = tmp_path / "traversal.zip"
    with zipfile.ZipFile(traversal, "w") as archive:
        archive.writestr("../escape.py", "unsafe")
    request = SourceRequest(
        SourceType.ZIP,
        archive_path=traversal,
        destination_parent=tmp_path,
    )
    with pytest.raises(SourcePreparationError, match="traversal"):
        SafeZipSourceProvider().prepare(request)

    linked = tmp_path / "linked.zip"
    with zipfile.ZipFile(linked, "w") as archive:
        info = zipfile.ZipInfo("source/link")
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(info, "../../outside")
    request.archive_path = linked
    with pytest.raises(SourcePreparationError, match="Symbolic"):
        SafeZipSourceProvider().prepare(request)


def test_zip_provider_rejects_compression_bombs(tmp_path: Path) -> None:
    archive_path = tmp_path / "bomb.zip"
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("source/large.txt", "A" * 100_000)
    request = SourceRequest(
        SourceType.ZIP,
        archive_path=archive_path,
        destination_parent=tmp_path,
        limits=SourceLimits(max_archive_ratio=5, max_repository_bytes=200_000),
    )

    with pytest.raises(SourcePreparationError, match="compression ratio"):
        SafeZipSourceProvider().prepare(request)


@pytest.mark.parametrize(
    "args",
    [
        ("python3.11", "-c", "print('unsafe')"),
        ("python3.11", "-m", "pytest", ";touch", "owned"),
        ("sh", "-c", "true"),
        ("npm", "run", "postinstall"),
    ],
)
def test_command_policy_rejects_command_injection(args: tuple[str, ...]) -> None:
    with pytest.raises(CommandRejectedError):
        CommandPolicy().validate(args)


def test_native_runner_uses_a_temporary_copy_and_redacts_output(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "module.py").write_text("VALUE = 1\n", encoding="utf-8")
    plan = ExecutionPlan(
        source,
        (
            CommandSpec(
                ("python3.11", "-m", "compileall", "."),
                timeout_seconds=10,
            ),
        ),
    )
    result = NativeSafeRunner().execute(plan)

    assert result.status.value == "passed"
    assert not (source / "__pycache__").exists()


def test_native_runner_enforces_timeout_and_redacts_stdout(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    raw_secret = "ghp_1234567890abcdefghijklmnopqrstuvwxyzAB"
    (source / "test_output.py").write_text(
        (f'def test_output():\n    print("token={raw_secret}")\n    print("X" * 200_000)\n'),
        encoding="utf-8",
    )
    output_plan = ExecutionPlan(
        source,
        (CommandSpec(("python3.11", "-m", "pytest", "-s", "test_output.py")),),
    )
    output_result = NativeSafeRunner(max_output_bytes=2048).execute(output_plan)
    combined = (
        output_result.executions[0].stdout_excerpt + output_result.executions[0].stderr_excerpt
    )
    assert output_result.status.value == "passed"
    assert raw_secret not in combined
    assert "[REDACTED]" in combined
    assert "output truncated" in combined
    assert len(combined.encode()) < 2200

    (source / "test_slow.py").write_text(
        "import time\ndef test_slow():\n    time.sleep(5)\n", encoding="utf-8"
    )
    timeout_plan = ExecutionPlan(
        source,
        (
            CommandSpec(
                ("python3.11", "-m", "pytest", "test_slow.py"),
                timeout_seconds=0.2,
            ),
        ),
    )
    timeout_result = NativeSafeRunner().execute(timeout_plan)
    assert timeout_result.status.value == "timed_out"
    assert timeout_result.executions[0].timed_out


def test_native_runner_rejects_source_symlinks(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    outside = tmp_path / "outside.py"
    outside.write_text("VALUE = 1\n", encoding="utf-8")
    (source / "link.py").symlink_to(outside)
    result = NativeSafeRunner().execute(
        ExecutionPlan(source, (CommandSpec(("python3.11", "-m", "compileall", ".")),))
    )

    assert result.status.value == "unavailable"
    assert "symbolic link" in result.message


def test_github_url_parser_rejects_credential_and_non_github_urls() -> None:
    assert parse_github_url("https://github.com/openai/example/pull/12") == (
        "openai",
        "example",
        12,
    )
    for url in (
        "http://github.com/openai/example",
        "https://example.com/openai/example",
        "https://user:password@github.com/openai/example",
        "https://github.com/openai/example/issues/1",
    ):
        with pytest.raises(SourcePreparationError):
            parse_github_url(url)
