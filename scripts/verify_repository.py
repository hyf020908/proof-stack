#!/usr/bin/env python3
"""Validate ProofStack structure, documentation, and common security invariants."""

from __future__ import annotations

import argparse
import ast
import json
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_PATHS = (
    "README.md",
    "README.zh-CN.md",
    "LICENSE",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "CODE_OF_CONDUCT.md",
    "pyproject.toml",
    "package.json",
    "pnpm-workspace.yaml",
    "docker-compose.yml",
    "docker/API.Dockerfile",
    "docker/Worker.Dockerfile",
    "docker/Web.Dockerfile",
    "migrations/versions",
    "tests/unit",
    "tests/integration",
    "tests/security",
    "tests/contract",
    "apps/web/e2e",
    "examples/demo-python-service/base",
    "examples/demo-python-service/changed",
    "examples/demo-python-service/change.diff",
    "examples/demo-python-service/requirements.md",
    "examples/demo-python-service/policy.yml",
)
TEXT_SUFFIXES = {
    ".css",
    ".html",
    ".js",
    ".json",
    ".py",
    ".sh",
    ".toml",
    ".ts",
    ".tsx",
    ".yaml",
    ".yml",
}
SOURCE_ROOTS = (
    "apps",
    "packages",
    "migrations",
    "tests",
    "examples",
    "scripts",
    "docker",
    ".github",
)
SCAN_EXCLUSIONS = {
    "scripts/verify_repository.py",
    "examples/demo-python-service/changed/demo_service/exporter.py",
}
PLACEHOLDER_WORDS = {
    "change-before-production",
    "development-only",
    "example",
    "placeholder",
    "replace-with",
    "sample",
}


@dataclass
class CheckResult:
    name: str
    problems: list[str]


def relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def source_files() -> list[Path]:
    files: list[Path] = []
    for root_name in SOURCE_ROOTS:
        source_root = ROOT / root_name
        if not source_root.exists():
            continue
        for path in source_root.rglob("*"):
            if not path.is_file() or path.is_symlink():
                continue
            if any(part in {"node_modules", "__pycache__", "dist"} for part in path.parts):
                continue
            if path.suffix.lower() in TEXT_SUFFIXES or "Dockerfile" in path.name:
                files.append(path)
    return sorted(files)


def check_structure() -> CheckResult:
    problems = []
    for name in REQUIRED_PATHS:
        path = ROOT / name
        if not path.exists():
            problems.append(f"missing required path: {name}")
        elif path.is_file() and path.stat().st_size == 0:
            problems.append(f"required file is empty: {name}")
    migrations = list((ROOT / "migrations/versions").glob("*.py"))
    if not migrations:
        problems.append("no Alembic version migration was found")
    python_tests = list((ROOT / "tests").rglob("test_*.py"))
    web_tests = list((ROOT / "apps/web/src").rglob("*.test.*"))
    e2e_tests = list((ROOT / "apps/web/e2e").glob("*.spec.ts"))
    if not python_tests:
        problems.append("no Python tests were found")
    if not web_tests:
        problems.append("no frontend component tests were found")
    if len(e2e_tests) < 3:
        problems.append("fewer than three Playwright scenarios were found")
    return CheckResult("repository structure", problems)


def check_forbidden_markers() -> CheckResult:
    marker = re.compile(r"\b(?:TO" r"DO|FIX" r"ME)\b", re.IGNORECASE)
    problems: list[str] = []
    for path in source_files():
        if relative(path) in SCAN_EXCLUSIONS:
            continue
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if marker.search(line):
                problems.append(f"{relative(path)}:{line_number} contains a work marker")
    return CheckResult("unfinished work markers", problems)


def check_code_language() -> CheckResult:
    cjk = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
    problems: list[str] = []
    for path in source_files():
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if cjk.search(line):
                problems.append(
                    f"{relative(path)}:{line_number} contains Chinese text in a code file"
                )
    return CheckResult("English-only code files", problems)


def check_secrets() -> CheckResult:
    patterns = (
        re.compile(r"AKIA[0-9A-Z]{16}"),
        re.compile(r"gh[pousr]_[A-Za-z0-9]{30,255}"),
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
        re.compile(r"(?i)(?:api[_-]?key|password|secret|token)\s*[:=]\s*['\"]([^'\"\s]{16,})['\"]"),
    )
    problems: list[str] = []
    for path in source_files():
        if relative(path) in SCAN_EXCLUSIONS or "tests" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        for line_number, line in enumerate(text.splitlines(), 1):
            lowered = line.lower()
            if any(word in lowered for word in PLACEHOLDER_WORDS):
                continue
            if any(pattern.search(line) for pattern in patterns):
                problems.append(f"{relative(path)}:{line_number} may contain a credential")
    env_path = ROOT / ".env.example"
    if env_path.exists():
        for line_number, line in enumerate(env_path.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            if (
                re.search(r"(?:SECRET|TOKEN|PASSWORD|API_KEY)", key)
                and not key.endswith("_TTL")
                and value
            ):
                lowered = value.lower()
                if not any(word in lowered for word in PLACEHOLDER_WORDS):
                    problems.append(f".env.example:{line_number} has a non-placeholder {key}")
    return CheckResult("credential hygiene", problems)


def check_empty_python_implementations() -> CheckResult:
    problems: list[str] = []
    for path in source_files():
        if path.suffix != ".py" or "migrations" in path.parts or "tests" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError as exc:
            problems.append(f"{relative(path)}:{exc.lineno or 1} has invalid Python syntax")
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            decorators = {
                decorator.id for decorator in node.decorator_list if isinstance(decorator, ast.Name)
            }
            body = [item for item in node.body if not _is_docstring(item)]
            if body and all(isinstance(item, (ast.Pass, ast.Expr)) for item in body):
                expressions = [item for item in body if isinstance(item, ast.Expr)]
                ellipsis_only = expressions and all(
                    isinstance(item.value, ast.Constant) and item.value.value is Ellipsis
                    for item in expressions
                )
                if "abstractmethod" not in decorators and (not expressions or ellipsis_only):
                    problems.append(
                        f"{relative(path)}:{node.lineno} has an empty function: {node.name}"
                    )
    return CheckResult("Python implementations", problems)


def _is_docstring(node: ast.stmt) -> bool:
    return (
        isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    )


def check_json_files() -> CheckResult:
    problems: list[str] = []
    for path in ROOT.rglob("*.json"):
        if any(part in {"node_modules", ".git"} for part in path.parts):
            continue
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            problems.append(f"{relative(path)} is not valid JSON: {exc}")
    return CheckResult("JSON files", problems)


def check_markdown_links() -> CheckResult:
    problems: list[str] = []
    link_pattern = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
    for path in ROOT.rglob("*.md"):
        if any(part in {"node_modules", ".git"} for part in path.parts) or path.name == "AGENTS.md":
            continue
        text = path.read_text(encoding="utf-8")
        for match in link_pattern.finditer(text):
            raw_target = match.group(1).strip().split(maxsplit=1)[0].strip("<>")
            target = unquote(raw_target.split("#", 1)[0])
            if not target or re.match(r"^[a-z][a-z0-9+.-]*:", target, re.IGNORECASE):
                continue
            candidate = (
                (ROOT / target.lstrip("/")) if target.startswith("/") else path.parent / target
            )
            if not candidate.resolve().exists():
                line = text.count("\n", 0, match.start()) + 1
                problems.append(f"{relative(path)}:{line} links to missing path {target}")
    return CheckResult("internal Markdown links", problems)


def check_readme_make_commands() -> CheckResult:
    makefile = ROOT / "Makefile"
    if not makefile.exists():
        return CheckResult("README Make targets", ["Makefile is missing"])
    targets = set(
        re.findall(
            r"^([A-Za-z0-9][A-Za-z0-9_-]*):(?:\s|$)",
            makefile.read_text(encoding="utf-8"),
            re.MULTILINE,
        )
    )
    documented: set[str] = set()
    for name in ("README.md", "README.zh-CN.md"):
        path = ROOT / name
        if path.exists():
            documented.update(
                re.findall(r"\bmake\s+([A-Za-z0-9][A-Za-z0-9_-]*)", path.read_text("utf-8"))
            )
    missing = sorted(documented - targets)
    return CheckResult(
        "README Make targets",
        [f"README documents unknown Make target: {name}" for name in missing],
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--structure-only",
        action="store_true",
        help="Only validate required repository paths and test presence.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    checks = [check_structure()]
    if not args.structure_only:
        checks.extend(
            (
                check_forbidden_markers(),
                check_code_language(),
                check_secrets(),
                check_empty_python_implementations(),
                check_json_files(),
                check_markdown_links(),
                check_readme_make_commands(),
            )
        )
    failures = 0
    for check in checks:
        if check.problems:
            failures += len(check.problems)
            print(f"[FAIL] {check.name}")
            for problem in check.problems:
                print(f"  - {problem}")
        else:
            print(f"[PASS] {check.name}")
    if failures:
        print(f"Repository verification failed with {failures} problem(s).")
        return 1
    print("Repository verification passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
