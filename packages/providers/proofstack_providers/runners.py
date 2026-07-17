"""Constrained native and opt-in Docker validation runners."""

from __future__ import annotations

import os
import re
import shutil
import signal
import subprocess
import tempfile
import threading
import time
import uuid
from collections.abc import Callable, Sequence
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO, ClassVar, Protocol, runtime_checkable

from proofstack_core import TestExecutionRecord, TestStatus


class CommandRejectedError(ValueError):
    """Raised when a command falls outside the native runner policy."""


@dataclass(slots=True, frozen=True)
class CommandSpec:
    args: tuple[str, ...]
    label: str = "validation"
    timeout_seconds: float | None = None
    optional: bool = False

    def __post_init__(self) -> None:
        if not self.args or any(not isinstance(item, str) or not item for item in self.args):
            raise ValueError("Command arguments must be non-empty strings")


@dataclass(slots=True)
class ExecutionPlan:
    working_directory: Path
    commands: tuple[CommandSpec, ...]
    environment: dict[str, str] = field(default_factory=dict)
    default_timeout_seconds: float = 120.0


@dataclass(slots=True)
class ExecutionResult:
    status: TestStatus
    executions: list[TestExecutionRecord]
    runner: str
    message: str = ""


@runtime_checkable
class ExecutionRunner(Protocol):
    def execute(self, plan: ExecutionPlan) -> ExecutionResult:
        """Run a prevalidated execution plan in an isolated environment."""


class CommandPolicy:
    _metacharacters = re.compile(r"[;&|`\n\r\x00]|\$\(|[<>]")
    _safe_scripts: ClassVar[set[str]] = {
        "test",
        "lint",
        "typecheck",
        "build",
        "check",
        "test:unit",
        "test:integration",
    }

    def validate(self, args: Sequence[str]) -> None:
        if not args:
            raise CommandRejectedError("Empty commands are not allowed")
        if any(self._metacharacters.search(item) for item in args):
            raise CommandRejectedError(
                "Shell metacharacters are not allowed in validation arguments"
            )
        executable = Path(args[0]).name.lower()
        tail = list(args[1:])
        if executable in {"python", "python3", "python3.11", "python3.12", "python3.13"}:
            self._validate_python(tail)
            return
        if executable == "pytest":
            self._reject_dangerous_options(tail)
            return
        if executable == "ruff" and tail and tail[0] in {"check", "format"}:
            if tail[0] == "format" and "--check" not in tail:
                raise CommandRejectedError("Ruff format may only run in check mode")
            self._reject_dangerous_options(tail)
            return
        if executable == "mypy":
            self._reject_dangerous_options(tail)
            return
        if executable in {"npm", "pnpm", "yarn"}:
            self._validate_package_manager(executable, tail)
            return
        raise CommandRejectedError(
            f"The executable {executable} is not on the validation allowlist"
        )

    def _validate_python(self, args: list[str]) -> None:
        if len(args) < 2 or args[0] != "-m":
            raise CommandRejectedError("Python may only execute an approved module with -m")
        module = args[1]
        if module not in {"compileall", "pytest", "ruff", "mypy"}:
            raise CommandRejectedError(f"The Python module {module} is not approved")
        if module == "ruff" and (len(args) < 3 or args[2] not in {"check", "format"}):
            raise CommandRejectedError("Only Ruff check and format validation are approved")
        if module == "ruff" and args[2] == "format" and "--check" not in args:
            raise CommandRejectedError("Ruff format may only run in check mode")
        self._reject_dangerous_options(args[2:])

    def _validate_package_manager(self, executable: str, args: list[str]) -> None:
        if not args:
            raise CommandRejectedError("A package manager script is required")
        script = (args[1] if len(args) > 1 else "") if args[0] == "run" else args[0]
        if script not in self._safe_scripts:
            raise CommandRejectedError(
                f"The package script {script or '<missing>'} is not approved"
            )
        if executable == "npm" and "--ignore-scripts=false" in args:
            raise CommandRejectedError(
                "Lifecycle scripts cannot be enabled by a validation command"
            )
        self._reject_dangerous_options(args)

    @staticmethod
    def _reject_dangerous_options(args: Sequence[str]) -> None:
        denied = {"-c", "--config-file", "--plugins", "--override-ini=addopts"}
        for item in args:
            normalized = item.replace("\\", "/")
            if (
                item in denied
                or any(item.startswith(f"{option}=") for option in denied)
                or item.startswith("--basetemp=/")
                or item.startswith("--rootdir=/")
                or normalized.startswith("/")
                or re.search(r"(?:^|[/=])\.\.(?:/|$)", normalized)
            ):
                raise CommandRejectedError(f"The validation option {item} is not allowed")


class NativeSafeRunner:
    _allowed_environment: ClassVar[set[str]] = {
        "CI",
        "LANG",
        "LC_ALL",
        "NO_COLOR",
        "PYTHONDONTWRITEBYTECODE",
        "PYTHONHASHSEED",
        "TZ",
    }

    def __init__(
        self,
        *,
        policy: CommandPolicy | None = None,
        max_output_bytes: int = 64 * 1024,
    ) -> None:
        self.policy = policy or CommandPolicy()
        self.max_output_bytes = max_output_bytes

    def execute(self, plan: ExecutionPlan) -> ExecutionResult:
        root = plan.working_directory.resolve()
        if not root.is_dir():
            return ExecutionResult(
                TestStatus.UNAVAILABLE,
                [],
                "native",
                "The validation working directory does not exist.",
            )
        executions: list[TestExecutionRecord] = []
        with tempfile.TemporaryDirectory(prefix="proofstack-run-") as temporary:
            temporary_root = Path(temporary)
            sandbox_root = temporary_root / "workspace"
            try:
                _copy_source_tree(root, sandbox_root)
            except CommandRejectedError as exc:
                return ExecutionResult(TestStatus.UNAVAILABLE, [], "native", str(exc))
            runtime_root = temporary_root / "runtime"
            runtime_root.mkdir(mode=0o700)
            for command in plan.commands:
                try:
                    self.policy.validate(command.args)
                except CommandRejectedError as exc:
                    executions.append(
                        TestExecutionRecord(
                            command=command.args,
                            status=TestStatus.SKIPPED,
                            exit_code=None,
                            duration_ms=0,
                            stderr_excerpt=str(exc),
                        )
                    )
                    continue
                executable = shutil.which(command.args[0])
                if executable is None:
                    status = TestStatus.SKIPPED if command.optional else TestStatus.UNAVAILABLE
                    executions.append(
                        TestExecutionRecord(
                            command=command.args,
                            status=status,
                            exit_code=None,
                            duration_ms=0,
                            stderr_excerpt=f"The executable {command.args[0]} is unavailable.",
                        )
                    )
                    continue
                timeout = command.timeout_seconds or plan.default_timeout_seconds
                executions.append(
                    self._run_one(
                        sandbox_root,
                        runtime_root,
                        (executable, *command.args[1:]),
                        command.args,
                        plan.environment,
                        timeout,
                    )
                )
        return ExecutionResult(
            _overall_status(executions), executions, "native", _status_message(executions)
        )

    def _run_one(
        self,
        root: Path,
        runtime_root: Path,
        resolved_args: tuple[str, ...],
        display_args: tuple[str, ...],
        requested_environment: dict[str, str],
        timeout: float,
    ) -> TestExecutionRecord:
        started = time.monotonic()
        environment = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": str(runtime_root),
            "TMPDIR": str(runtime_root),
            "PYTHONDONTWRITEBYTECODE": "1",
            "CI": "true",
        }
        for key, value in requested_environment.items():
            if key in self._allowed_environment and "\x00" not in value and len(value) <= 4096:
                environment[key] = value
        process = subprocess.Popen(  # noqa: S603
            list(resolved_args),
            cwd=root,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=False,
            shell=False,
            start_new_session=True,
        )
        stdout, stderr, timed_out = _wait_bounded(
            process,
            timeout=timeout,
            output_limit=self.max_output_bytes,
        )
        duration = max(0, round((time.monotonic() - started) * 1000))
        status = (
            TestStatus.TIMED_OUT
            if timed_out
            else TestStatus.PASSED
            if process.returncode == 0
            else TestStatus.FAILED
        )
        return TestExecutionRecord(
            command=display_args,
            status=status,
            exit_code=process.returncode,
            duration_ms=duration,
            stdout_excerpt=_truncate(_redact(stdout), self.max_output_bytes),
            stderr_excerpt=_truncate(_redact(stderr), self.max_output_bytes),
            timed_out=timed_out,
            environment={
                key: value for key, value in environment.items() if key in self._allowed_environment
            },
        )


class DockerSandboxRunner:
    def __init__(
        self,
        *,
        enabled: bool = False,
        image: str = "python:3.11-slim",
        policy: CommandPolicy | None = None,
        max_output_bytes: int = 64 * 1024,
    ) -> None:
        self.enabled = enabled
        self.image = image
        self.policy = policy or CommandPolicy()
        self.max_output_bytes = max_output_bytes

    def execute(self, plan: ExecutionPlan) -> ExecutionResult:
        if not self.enabled:
            return ExecutionResult(
                TestStatus.UNAVAILABLE,
                [],
                "docker",
                "Docker sandbox execution is disabled by configuration.",
            )
        docker = shutil.which("docker")
        if docker is None:
            return ExecutionResult(
                TestStatus.UNAVAILABLE,
                [],
                "docker",
                "Docker is not installed or is not available on PATH.",
            )
        root = plan.working_directory.resolve()
        if not root.is_dir():
            return ExecutionResult(
                TestStatus.UNAVAILABLE,
                [],
                "docker",
                "The validation working directory does not exist.",
            )
        if not re.fullmatch(r"[A-Za-z0-9./:@_-]{1,255}", self.image):
            return ExecutionResult(
                TestStatus.UNAVAILABLE,
                [],
                "docker",
                "The configured sandbox image reference is invalid.",
            )
        executions: list[TestExecutionRecord] = []
        for command in plan.commands:
            try:
                self.policy.validate(command.args)
            except CommandRejectedError as exc:
                executions.append(
                    TestExecutionRecord(
                        command.args, TestStatus.SKIPPED, None, 0, stderr_excerpt=str(exc)
                    )
                )
                continue
            container_name = f"proofstack-{uuid.uuid4().hex[:16]}"
            docker_args = [
                docker,
                "run",
                "--rm",
                "--name",
                container_name,
                "--network",
                "none",
                "--read-only",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges",
                "--pids-limit",
                "128",
                "--cpus",
                "1.0",
                "--memory",
                "512m",
                "--user",
                "65532:65532",
                "--tmpfs",
                "/tmp:rw,noexec,nosuid,size=128m",  # noqa: S108
                "--mount",
                f"type=bind,src={root},dst=/workspace,readonly",
                "--workdir",
                "/workspace",
                self.image,
                *command.args,
            ]
            executions.append(
                self._run_docker_command(
                    docker_args,
                    command.args,
                    command.timeout_seconds or plan.default_timeout_seconds,
                    docker,
                    container_name,
                )
            )
        return ExecutionResult(
            _overall_status(executions), executions, "docker", _status_message(executions)
        )

    def _run_docker_command(
        self,
        args: list[str],
        display_args: tuple[str, ...],
        timeout: float,
        docker: str,
        container_name: str,
    ) -> TestExecutionRecord:
        started = time.monotonic()
        timed_out = False
        try:
            process = subprocess.Popen(  # noqa: S603
                args,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=False,
                shell=False,
                start_new_session=True,
            )
            stdout, stderr, timed_out = _wait_bounded(
                process,
                timeout=timeout,
                output_limit=self.max_output_bytes,
                on_timeout=lambda: _remove_container(docker, container_name),
            )
            return_code = process.returncode
        except OSError as exc:
            stdout = ""
            stderr = str(exc)
            return_code = None
            timed_out = False
        if timed_out:
            _remove_container(docker, container_name)
            return_code = None
        duration = max(0, round((time.monotonic() - started) * 1000))
        status = (
            TestStatus.TIMED_OUT
            if timed_out
            else TestStatus.PASSED
            if return_code == 0
            else TestStatus.FAILED
        )
        return TestExecutionRecord(
            command=display_args,
            status=status,
            exit_code=return_code,
            duration_ms=duration,
            stdout_excerpt=_truncate(_redact(stdout), self.max_output_bytes),
            stderr_excerpt=_truncate(_redact(stderr), self.max_output_bytes),
            timed_out=timed_out,
            environment={"network": "none", "source_mount": "read_only", "user": "65532:65532"},
        )


def _overall_status(executions: list[TestExecutionRecord]) -> TestStatus:
    statuses = {item.status for item in executions}
    if TestStatus.TIMED_OUT in statuses:
        return TestStatus.TIMED_OUT
    if TestStatus.FAILED in statuses:
        return TestStatus.FAILED
    if TestStatus.UNAVAILABLE in statuses:
        return TestStatus.UNAVAILABLE
    if TestStatus.PASSED in statuses:
        return TestStatus.PASSED
    return TestStatus.SKIPPED


def _status_message(executions: list[TestExecutionRecord]) -> str:
    if not executions:
        return "No validation commands were requested."
    counts = {status: sum(item.status is status for item in executions) for status in TestStatus}
    return ", ".join(f"{status.value}: {count}" for status, count in counts.items() if count)


def _truncate(value: str, limit: int) -> str:
    encoded = value.encode("utf-8", errors="replace")
    if len(encoded) <= limit:
        return value
    half = max(1, (limit - 64) // 2)
    return (
        encoded[:half].decode(errors="replace")
        + "\n...[output truncated]...\n"
        + encoded[-half:].decode(errors="replace")
    )


def _redact(value: str) -> str:
    patterns = (
        re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/-]{8,}"),
        re.compile(r"(?i)((?:token|secret|password|api[_-]?key)\s*[=:]\s*)[^\s]+"),
        re.compile(r"(?i)(://[^\s:@/]+:)[^\s@/]+(@)"),
        re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
        re.compile(r"AKIA[0-9A-Z]{16}"),
    )
    result = value
    for pattern in patterns:
        if pattern.groups == 2:
            result = pattern.sub(r"\1[REDACTED]\2", result)
        elif pattern.groups == 1:
            result = pattern.sub(r"\1[REDACTED]", result)
        else:
            result = pattern.sub("[REDACTED]", result)
    return result


class _BoundedOutput:
    def __init__(self, limit: int) -> None:
        self.limit = max(1024, limit)
        self.head_limit = (self.limit - 64) // 2
        self.tail_limit = self.limit - 64 - self.head_limit
        self.head = bytearray()
        self.tail = bytearray()
        self.total = 0

    def feed(self, chunk: bytes) -> None:
        self.total += len(chunk)
        head_remaining = self.head_limit - len(self.head)
        if head_remaining > 0:
            self.head.extend(chunk[:head_remaining])
            chunk = chunk[head_remaining:]
        if chunk:
            self.tail.extend(chunk)
            if len(self.tail) > self.tail_limit:
                del self.tail[: len(self.tail) - self.tail_limit]

    def render(self) -> str:
        if self.total <= self.head_limit:
            value = bytes(self.head)
        elif self.total <= self.head_limit + self.tail_limit:
            value = bytes(self.head + self.tail)
        else:
            value = bytes(self.head) + b"\n...[output truncated]...\n" + bytes(self.tail)
        return value.decode("utf-8", errors="replace")


def _read_stream(stream: BinaryIO, capture: _BoundedOutput) -> None:
    try:
        while chunk := stream.read(8192):
            capture.feed(chunk)
    finally:
        stream.close()


def _wait_bounded(
    process: subprocess.Popen[bytes],
    *,
    timeout: float,
    output_limit: int,
    on_timeout: Callable[[], None] | None = None,
) -> tuple[str, str, bool]:
    if process.stdout is None or process.stderr is None:
        raise RuntimeError("Validation output pipes were not created")
    stdout_capture = _BoundedOutput(output_limit)
    stderr_capture = _BoundedOutput(output_limit)
    threads = [
        threading.Thread(
            target=_read_stream,
            args=(process.stdout, stdout_capture),
            daemon=True,
        ),
        threading.Thread(
            target=_read_stream,
            args=(process.stderr, stderr_capture),
            daemon=True,
        ),
    ]
    for thread in threads:
        thread.start()
    timed_out = False
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        with suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)
        if on_timeout is not None:
            on_timeout()
        process.wait()
    for thread in threads:
        thread.join(timeout=5)
    return stdout_capture.render(), stderr_capture.render(), timed_out


def _remove_container(docker: str, container_name: str) -> None:
    try:
        subprocess.run(  # noqa: S603
            [docker, "rm", "--force", container_name],
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=15,
            shell=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return


def _copy_source_tree(source: Path, destination: Path) -> None:
    ignored_parts = {
        ".git",
        ".hg",
        ".svn",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "__pycache__",
        "build",
        "coverage",
        "dist",
        "htmlcov",
        "node_modules",
    }
    for candidate in source.rglob("*"):
        relative = candidate.relative_to(source)
        if any(part in ignored_parts for part in relative.parts):
            continue
        if candidate.is_symlink():
            raise CommandRejectedError(
                "Native validation rejected a symbolic link in the source tree."
            )
        if not candidate.is_dir() and not candidate.is_file():
            raise CommandRejectedError(
                "Native validation rejected a special file in the source tree."
            )
    shutil.copytree(
        source,
        destination,
        symlinks=False,
        ignore=shutil.ignore_patterns(*sorted(ignored_parts)),
    )
