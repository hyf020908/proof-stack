"""User-facing CLI for local analysis, policy checks, reports, and services."""

from __future__ import annotations

import json
import platform
import shlex
import shutil
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

import typer
from proofstack_core import EvidenceBundleVerifier
from proofstack_policies import PolicyValidationError, parse_policy
from proofstack_shared.config import Settings
from proofstack_shared.version import VERSION
from proofstack_worker.analysis import LocalAnalysisResult, run_local_analysis
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

app = typer.Typer(
    name="proofstack",
    help="Build verifiable acceptance evidence for AI-generated code changes.",
    no_args_is_help=True,
    add_completion=False,
)
analyze_app = typer.Typer(help="Analyze a repository, diff, or public GitHub source.")
policy_app = typer.Typer(help="Validate deterministic acceptance policies.")
report_app = typer.Typer(help="Inspect an evidence report.")
evidence_app = typer.Typer(help="Verify evidence bundle integrity.")
app.add_typer(analyze_app, name="analyze")
app.add_typer(policy_app, name="policy")
app.add_typer(report_app, name="report")
app.add_typer(evidence_app, name="evidence")

console = Console()


@dataclass(slots=True)
class OutputOptions:
    json_output: bool = False
    quiet: bool = False


@app.callback()
def callback(
    ctx: typer.Context,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit machine-readable JSON output."),
    ] = False,
    quiet: Annotated[
        bool,
        typer.Option("--quiet", "-q", help="Suppress non-essential output."),
    ] = False,
) -> None:
    ctx.obj = OutputOptions(json_output=json_output, quiet=quiet)


def _options(ctx: typer.Context) -> OutputOptions:
    return ctx.ensure_object(OutputOptions)


def _emit(ctx: typer.Context, value: dict[str, Any], *, title: str = "ProofStack") -> None:
    options = _options(ctx)
    if options.quiet:
        return
    if options.json_output:
        typer.echo(json.dumps(value, sort_keys=True, default=str))
        return
    table = Table(show_header=False, box=None, pad_edge=False)
    table.add_column(style="bold #f97316")
    table.add_column()
    for key, item in value.items():
        table.add_row(key.replace("_", " ").title(), str(item))
    console.print(Panel(table, title=title, border_style="#fb7185"))


def _failure(ctx: typer.Context, message: str, *, suggestion: str | None = None) -> None:
    options = _options(ctx)
    payload = {"error": message}
    if suggestion:
        payload["suggestion"] = suggestion
    if options.json_output:
        typer.echo(json.dumps(payload, sort_keys=True), err=True)
    elif not options.quiet:
        console.print(f"[bold red]Error:[/bold red] {message}", highlight=False)
        if suggestion:
            console.print(f"[dim]Next:[/dim] {suggestion}", highlight=False)


def _default_output(prefix: str = "proofstack-evidence") -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    candidate = Path.cwd() / f"{prefix}-{stamp}"
    counter = 1
    while candidate.exists():
        counter += 1
        candidate = Path.cwd() / f"{prefix}-{stamp}-{counter}"
    return candidate


def _read_text(path: Path, *, limit: int = 10 * 1024 * 1024) -> str:
    resolved = path.resolve()
    if not resolved.is_file():
        raise ValueError(f"File does not exist: {path}")
    if resolved.stat().st_size > limit:
        raise ValueError(f"File exceeds the {limit}-byte limit: {path}")
    content = resolved.read_bytes()
    if b"\x00" in content:
        raise ValueError(f"Text file contains binary data: {path}")
    return content.decode("utf-8")


def _commands(values: list[str] | None) -> list[list[str]]:
    result = []
    for value in values or []:
        parsed = shlex.split(value)
        if not parsed:
            raise ValueError("Validation commands cannot be empty")
        result.append(parsed)
    return result


def _policy(path: Path | None) -> str | None:
    return _read_text(path, limit=1024 * 1024) if path else None


def _show_analysis(ctx: typer.Context, result: LocalAnalysisResult) -> None:
    _emit(ctx, result.to_dict(), title="Analysis complete")


@app.command()
def version(ctx: typer.Context) -> None:
    """Show the installed ProofStack version."""

    _emit(ctx, {"version": VERSION}, title="ProofStack")


@app.command()
def demo(
    ctx: typer.Context,
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="New directory for the evidence bundle."),
    ] = None,
) -> None:
    """Run the repository's intentionally risky demo through the full pipeline."""

    settings = Settings()
    if not settings.demo_mode:
        _failure(ctx, "Demo mode is disabled", suggestion="Set PROOFSTACK_DEMO_MODE=true locally.")
        raise typer.Exit(2)
    destination = output or _default_output("proofstack-demo-evidence")
    try:
        result = run_local_analysis(
            Path.cwd(),
            settings=settings,
            output_directory=destination,
            source_type="demo",
            source_reference="examples/demo-python-service",
        )
    except Exception as exc:
        _failure(
            ctx, str(exc), suggestion="Run `proofstack doctor` and inspect the selected source."
        )
        raise typer.Exit(1) from exc
    _show_analysis(ctx, result)


@analyze_app.command("path")
def analyze_path(
    ctx: typer.Context,
    repository: Annotated[Path, typer.Argument(help="Repository directory to analyze.")],
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
    requirements: Annotated[Path | None, typer.Option("--requirements", "-r")] = None,
    policy: Annotated[Path | None, typer.Option("--policy", "-p")] = None,
    runner: Annotated[str, typer.Option(help="native or docker")] = "native",
    validate: Annotated[
        list[str] | None,
        typer.Option("--validate", help="Repeat an allowlisted validation command."),
    ] = None,
) -> None:
    """Analyze a local repository snapshot without requiring Docker."""

    try:
        result = run_local_analysis(
            repository.resolve(),
            settings=Settings(),
            output_directory=output or _default_output(),
            requirements=_read_text(requirements) if requirements else "",
            policy_document=_policy(policy),
            runner=runner,
            validation_commands=_commands(validate),
        )
    except Exception as exc:
        _failure(
            ctx,
            str(exc),
            suggestion="Confirm the path and use only allowlisted validation commands.",
        )
        raise typer.Exit(1) from exc
    _show_analysis(ctx, result)


@analyze_app.command("diff")
def analyze_diff(
    ctx: typer.Context,
    patch: Annotated[Path, typer.Argument(help="Unified .diff or .patch file.")],
    source: Annotated[Path, typer.Option("--source", help="Changed source repository.")],
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
    requirements: Annotated[Path | None, typer.Option("--requirements", "-r")] = None,
    policy: Annotated[Path | None, typer.Option("--policy", "-p")] = None,
    runner: Annotated[str, typer.Option(help="native or docker")] = "native",
    validate: Annotated[list[str] | None, typer.Option("--validate")] = None,
) -> None:
    """Analyze a local source tree against a Git-style unified diff."""

    if patch.suffix.lower() not in {".diff", ".patch"}:
        _failure(ctx, "Diff file must end in .diff or .patch")
        raise typer.Exit(2)
    try:
        result = run_local_analysis(
            source.resolve(),
            settings=Settings(),
            output_directory=output or _default_output(),
            diff_text=_read_text(patch),
            requirements=_read_text(requirements) if requirements else "",
            policy_document=_policy(policy),
            runner=runner,
            validation_commands=_commands(validate),
        )
    except Exception as exc:
        _failure(ctx, str(exc), suggestion="Validate the diff and source tree, then retry.")
        raise typer.Exit(1) from exc
    _show_analysis(ctx, result)


@analyze_app.command("github")
def analyze_github(
    ctx: typer.Context,
    url: Annotated[str, typer.Argument(help="Public GitHub repository or pull request URL.")],
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
    requirements: Annotated[Path | None, typer.Option("--requirements", "-r")] = None,
    policy: Annotated[Path | None, typer.Option("--policy", "-p")] = None,
    runner: Annotated[str, typer.Option(help="native or docker")] = "native",
    validate: Annotated[list[str] | None, typer.Option("--validate")] = None,
) -> None:
    """Analyze a public GitHub repository or pull request through bounded HTTP adapters."""

    try:
        result = run_local_analysis(
            Path.cwd(),
            settings=Settings(),
            output_directory=output or _default_output(),
            requirements=_read_text(requirements) if requirements else "",
            policy_document=_policy(policy),
            runner=runner,
            validation_commands=_commands(validate),
            source_type="github",
            source_reference=url,
        )
    except Exception as exc:
        _failure(
            ctx,
            str(exc),
            suggestion="Check the public URL or configure a read-only PROOFSTACK_GITHUB_TOKEN.",
        )
        raise typer.Exit(1) from exc
    _show_analysis(ctx, result)


@policy_app.command("validate")
def policy_validate(
    ctx: typer.Context,
    path: Annotated[Path, typer.Argument(help="YAML policy file.")],
) -> None:
    """Parse and validate a policy without executing an analysis."""

    try:
        policy = parse_policy(_read_text(path, limit=1024 * 1024))
    except (ValueError, PolicyValidationError) as exc:
        _failure(ctx, str(exc), suggestion="Fix the reported rule location and validate again.")
        raise typer.Exit(1) from exc
    _emit(
        ctx,
        {"valid": True, "name": policy.name, "version": policy.version, "rules": len(policy.rules)},
        title="Policy valid",
    )


@report_app.command("show")
def report_show(
    ctx: typer.Context,
    bundle: Annotated[Path, typer.Argument(help="Evidence bundle directory or ZIP.")],
) -> None:
    """Verify and summarize an evidence bundle."""

    result = EvidenceBundleVerifier().verify(bundle)
    if not result.valid:
        _failure(ctx, "Evidence bundle verification failed", suggestion=str(result.issues[:3]))
        raise typer.Exit(1)
    manifest = result.manifest or {}
    _emit(
        ctx,
        {
            "valid": True,
            "analysis_id": manifest.get("analysis_id"),
            "generated_at": manifest.get("generated_at"),
            "tool_version": manifest.get("tool", {}).get("version"),
            "verified_files": len(result.verified_files),
        },
        title="Evidence report",
    )


@evidence_app.command("verify")
def evidence_verify(
    ctx: typer.Context,
    bundle: Annotated[Path, typer.Argument(help="Evidence bundle directory or ZIP.")],
) -> None:
    """Verify manifest structure, paths, and every SHA-256 checksum."""

    result = EvidenceBundleVerifier().verify(bundle)
    payload = result.to_dict()
    if not result.valid:
        _failure(ctx, "Evidence verification failed", suggestion=json.dumps(payload["issues"][:3]))
        raise typer.Exit(1)
    _emit(
        ctx,
        {"valid": True, "source": str(bundle), "verified_files": len(result.verified_files)},
        title="Evidence verified",
    )


@app.command()
def server(
    host: Annotated[str, typer.Option(help="Bind address.")] = "127.0.0.1",
    port: Annotated[int, typer.Option(help="Bind port.", min=1, max=65535)] = 8000,
    reload: Annotated[bool, typer.Option(help="Enable development reload.")] = False,
) -> None:
    """Start the FastAPI service using Uvicorn."""

    import uvicorn

    uvicorn.run("proofstack_api.main:app", host=host, port=port, reload=reload)


@app.command()
def doctor(ctx: typer.Context) -> None:
    """Inspect local prerequisites without changing the machine."""

    settings = Settings()
    python_ok = sys.version_info >= (3, 11)
    checks = {
        "proofstack_version": VERSION,
        "python": platform.python_version(),
        "python_supported": python_ok,
        "node": shutil.which("node") or "unavailable",
        "docker": shutil.which("docker") or "unavailable (optional)",
        "semgrep": shutil.which("semgrep") or "unavailable (optional)",
        "database": "sqlite" if settings.database_url.startswith("sqlite") else "configured",
        "task_backend": settings.task_backend,
        "runner": settings.runner,
        "demo_mode": settings.demo_mode,
    }
    _emit(ctx, checks, title="ProofStack doctor")
    if not python_ok:
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
