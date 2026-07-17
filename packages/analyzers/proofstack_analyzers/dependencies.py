"""Dependency manifest parsing and deterministic change classification."""

from __future__ import annotations

import hashlib
import json
import re
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from proofstack_core import Finding, FindingCategory, Severity


@dataclass(slots=True, frozen=True)
class Dependency:
    name: str
    specification: str
    ecosystem: str
    source_path: str
    locked: bool
    direct_url: bool = False


@dataclass(slots=True, frozen=True)
class DependencyChange:
    name: str
    ecosystem: str
    change_type: str
    previous: str | None
    current: str | None


@dataclass(slots=True)
class DependencyAnalysisResult:
    dependencies: list[Dependency] = field(default_factory=list)
    changes: list[DependencyChange] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)


class DependencyAnalyzer:
    def parse(self, path: str, source: str) -> list[Dependency]:
        name = PurePosixPath(path).name.lower()
        if name.startswith("requirements") and name.endswith(".txt"):
            return _parse_requirements(path, source)
        if name == "pyproject.toml":
            return _parse_pyproject(path, source)
        if name == "package.json":
            return _parse_package_json(path, source)
        if name == "dockerfile" or name.endswith(".dockerfile"):
            return _parse_dockerfile(path, source)
        return []

    def analyze(
        self,
        current_files: Mapping[str, str],
        *,
        previous_files: Mapping[str, str] | None = None,
    ) -> DependencyAnalysisResult:
        result = DependencyAnalysisResult()
        current = [
            item for path, source in current_files.items() for item in self.parse(path, source)
        ]
        previous = [
            item
            for path, source in (previous_files or {}).items()
            for item in self.parse(path, source)
        ]
        result.dependencies = current
        current_map = {(item.ecosystem, item.name.lower()): item for item in current}
        previous_map = {(item.ecosystem, item.name.lower()): item for item in previous}
        for key in sorted(current_map.keys() | previous_map.keys()):
            before = previous_map.get(key)
            after = current_map.get(key)
            if before is None and after is not None:
                result.changes.append(
                    DependencyChange(
                        after.name, after.ecosystem, "added", None, after.specification
                    )
                )
            elif after is None and before is not None:
                result.changes.append(
                    DependencyChange(
                        before.name, before.ecosystem, "removed", before.specification, None
                    )
                )
            elif before and after and before.specification != after.specification:
                result.changes.append(
                    DependencyChange(
                        after.name,
                        after.ecosystem,
                        _version_direction(before.specification, after.specification),
                        before.specification,
                        after.specification,
                    )
                )
        for dependency in current:
            if dependency.direct_url:
                result.findings.append(
                    _finding(
                        "dependency.direct-url",
                        Severity.HIGH,
                        "Dependency uses a direct URL",
                        f"{dependency.name} is installed from {dependency.specification}.",
                        dependency.source_path,
                        (
                            "Use an immutable registry release or pin the URL to a verified "
                            "commit and hash."
                        ),
                    )
                )
            elif _is_unpinned(dependency.specification):
                result.findings.append(
                    _finding(
                        "dependency.unpinned",
                        Severity.MEDIUM,
                        "Dependency is not pinned",
                        (
                            f"{dependency.name} uses the broad specification "
                            f"{dependency.specification or '<any>'}."
                        ),
                        dependency.source_path,
                        "Use a bounded version and commit the ecosystem lockfile.",
                    )
                )
        manifest_names = {PurePosixPath(path).name.lower() for path in current_files}
        if "package.json" in manifest_names and not manifest_names.intersection(
            {"package-lock.json", "pnpm-lock.yaml", "yarn.lock"}
        ):
            result.findings.append(
                _finding(
                    "dependency.javascript-lockfile-missing",
                    Severity.MEDIUM,
                    "JavaScript lockfile is missing",
                    "package.json is present without a recognized JavaScript lockfile.",
                    "package.json",
                    "Generate and commit one lockfile using the selected package manager.",
                )
            )
        if "pyproject.toml" in manifest_names and not manifest_names.intersection(
            {"poetry.lock", "uv.lock", "pdm.lock"}
        ):
            result.findings.append(
                _finding(
                    "dependency.python-lockfile-missing",
                    Severity.LOW,
                    "Python lockfile is missing",
                    "pyproject.toml is present without a recognized Python lockfile.",
                    "pyproject.toml",
                    "Generate a reproducible lockfile for the selected package manager.",
                )
            )
        return result


def _parse_requirements(path: str, source: str) -> list[Dependency]:
    result: list[Dependency] = []
    for line in source.splitlines():
        value = line.strip()
        if not value or value.startswith(("#", "-r", "--")):
            continue
        value = value.split(" #", 1)[0]
        direct_url = " @ " in value or value.startswith(("git+", "http://", "https://"))
        match = re.match(r"([A-Za-z0-9_.-]+)(.*)", value)
        if match:
            result.append(
                Dependency(
                    match.group(1),
                    match.group(2).strip(),
                    "python",
                    path,
                    "==" in value,
                    direct_url,
                )
            )
    return result


def _parse_pyproject(path: str, source: str) -> list[Dependency]:
    try:
        data = tomllib.loads(source)
    except tomllib.TOMLDecodeError:
        return []
    values: list[str] = list(data.get("project", {}).get("dependencies", []))
    for group in data.get("project", {}).get("optional-dependencies", {}).values():
        values.extend(group)
    poetry = data.get("tool", {}).get("poetry", {}).get("dependencies", {})
    result = _parse_requirements(path, "\n".join(values))
    for name, spec in poetry.items():
        if name.lower() == "python":
            continue
        rendered = spec if isinstance(spec, str) else json.dumps(spec, sort_keys=True)
        result.append(
            Dependency(
                name,
                rendered,
                "python",
                path,
                "==" in rendered,
                "git" in rendered or "url" in rendered,
            )
        )
    return result


def _parse_package_json(path: str, source: str) -> list[Dependency]:
    try:
        data = json.loads(source)
    except json.JSONDecodeError:
        return []
    result: list[Dependency] = []
    for section in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
        for name, spec in data.get(section, {}).items():
            rendered = str(spec)
            result.append(
                Dependency(
                    name,
                    rendered,
                    "npm",
                    path,
                    not rendered.startswith(("^", "~", ">", "<", "*", "latest")),
                    rendered.startswith(("git", "http", "github:")),
                )
            )
    return result


def _parse_dockerfile(path: str, source: str) -> list[Dependency]:
    result = []
    for match in re.finditer(r"^\s*FROM\s+([^\s]+)", source, re.I | re.M):
        image = match.group(1)
        name, separator, spec = image.rpartition(":")
        if not separator or "/" in spec:
            name, spec = image, "latest"
        result.append(Dependency(name, spec, "container", path, spec not in {"latest", ""}, False))
    return result


def _is_unpinned(specification: str) -> bool:
    value = specification.strip().lower()
    return (
        not value
        or value in {"*", "latest"}
        or value.startswith(("^", "~", ">", "<"))
        or "," in value
    )


def _version_direction(previous: str, current: str) -> str:
    old = tuple(int(item) for item in re.findall(r"\d+", previous)[:3])
    new = tuple(int(item) for item in re.findall(r"\d+", current)[:3])
    if old and new:
        return "upgraded" if new > old else "downgraded" if new < old else "modified"
    return "modified"


def _finding(
    rule_id: str,
    severity: Severity,
    title: str,
    description: str,
    path: str,
    remediation: str,
) -> Finding:
    fingerprint = hashlib.sha256(f"{rule_id}:{path}:{description}".encode()).hexdigest()
    return Finding(
        category=FindingCategory.DEPENDENCY,
        severity=severity,
        title=title,
        description=description,
        rule_id=rule_id,
        remediation=remediation,
        fingerprint=fingerprint,
        file_path=path,
    )
