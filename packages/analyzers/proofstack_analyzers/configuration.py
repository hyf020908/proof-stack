"""Configuration and environment contract analysis."""

from __future__ import annotations

import ast
import hashlib
import json
import re
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any

from proofstack_core import Finding, FindingCategory, Severity


@dataclass(slots=True, frozen=True)
class EnvironmentReference:
    name: str
    path: str
    line: int
    required: bool
    default: str | None


@dataclass(slots=True)
class ConfigurationResult:
    environment_references: list[EnvironmentReference] = field(default_factory=list)
    undocumented_variables: list[str] = field(default_factory=list)
    removed_keys: list[str] = field(default_factory=list)
    compose_drift: list[str] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)


class ConfigurationAnalyzer:
    def extract_environment(self, source: str, path: str) -> list[EnvironmentReference]:
        if not path.endswith(".py"):
            return self._extract_text_environment(source, path)
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return []
        references: list[EnvironmentReference] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _call_name(node.func) in {
                "os.getenv",
                "os.environ.get",
            }:
                name = _constant_string(node.args[0]) if node.args else None
                if not name:
                    continue
                default_node = (
                    node.args[1]
                    if len(node.args) > 1
                    else next((item.value for item in node.keywords if item.arg == "default"), None)
                )
                default = _render_default(default_node)
                references.append(
                    EnvironmentReference(name, path, node.lineno, default_node is None, default)
                )
            elif (
                isinstance(node, ast.Subscript)
                and _call_name(node.value) == "os.environ"
                and (name := _constant_string(node.slice))
            ):
                references.append(EnvironmentReference(name, path, node.lineno, True, None))
        return _deduplicate_references(references)

    def analyze(
        self,
        current_files: Mapping[str, str],
        *,
        previous_files: Mapping[str, str] | None = None,
    ) -> ConfigurationResult:
        previous_files = previous_files or {}
        result = ConfigurationResult()
        for path, source in current_files.items():
            result.environment_references.extend(self.extract_environment(source, path))
        documented = set()
        for path, source in current_files.items():
            if PurePosixPath(path).name.lower() in {".env.example", ".env.sample", "readme.md"}:
                documented.update(_env_keys(source))
        current_names = {item.name for item in result.environment_references}
        previous_names = {
            item.name
            for path, source in previous_files.items()
            for item in self.extract_environment(source, path)
        }
        new_names = current_names - previous_names if previous_files else current_names
        result.undocumented_variables = sorted(new_names - documented)
        for name in result.undocumented_variables:
            reference = next(item for item in result.environment_references if item.name == name)
            severity = Severity.HIGH if reference.required else Severity.MEDIUM
            result.findings.append(
                _finding(
                    "config.undocumented-environment-variable",
                    severity,
                    "Environment variable is not documented",
                    (
                        f"{name} is read by the application but is absent from "
                        ".env.example and README."
                    ),
                    reference.path,
                    reference.line,
                    "Document the variable, whether it is required, and a safe example value.",
                )
            )
        previous_config = _collect_config(previous_files)
        current_config = _collect_config(current_files)
        result.removed_keys = sorted(previous_config.keys() - current_config.keys())
        for key in result.removed_keys:
            result.findings.append(
                _finding(
                    "config.key-removed",
                    Severity.MEDIUM,
                    "Configuration key removed",
                    f"The configuration key {key} existed before this change and is now absent.",
                    None,
                    None,
                    "Confirm consumers have a migration path before removing the key.",
                )
            )
        compose_sources = [
            source
            for path, source in current_files.items()
            if PurePosixPath(path).name.lower()
            in {"compose.yml", "compose.yaml", "docker-compose.yml", "docker-compose.yaml"}
        ]
        compose_environment = {
            key for source in compose_sources for key in _compose_env_keys(source)
        }
        if compose_sources:
            result.compose_drift = sorted(current_names - compose_environment)
            for name in result.compose_drift:
                reference = next(
                    item for item in result.environment_references if item.name == name
                )
                result.findings.append(
                    _finding(
                        "config.compose-environment-drift",
                        Severity.MEDIUM,
                        "Compose environment differs from application configuration",
                        f"{name} is read by the application but is not declared in Compose.",
                        reference.path,
                        reference.line,
                        "Declare the variable in Compose or document its external source.",
                    )
                )
        return result

    @staticmethod
    def _extract_text_environment(source: str, path: str) -> list[EnvironmentReference]:
        references: list[EnvironmentReference] = []
        for line_number, line in enumerate(source.splitlines(), 1):
            for match in re.finditer(r"(?:process\.env\.|\$\{)([A-Z][A-Z0-9_]{2,})", line):
                references.append(
                    EnvironmentReference(match.group(1), path, line_number, True, None)
                )
        return references


def _collect_config(files: Mapping[str, str]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for path, source in files.items():
        suffix = PurePosixPath(path).suffix.lower()
        try:
            if suffix == ".json":
                parsed = json.loads(source)
            elif suffix == ".toml":
                parsed = tomllib.loads(source)
            elif suffix in {".yaml", ".yml"}:
                try:
                    import yaml
                except ImportError:
                    continue
                parsed = yaml.safe_load(source)
            else:
                continue
        except (ValueError, tomllib.TOMLDecodeError):
            continue
        _flatten(parsed, prefix=path, target=result)
    return result


def _flatten(value: Any, *, prefix: str, target: dict[str, Any]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            _flatten(child, prefix=f"{prefix}:{key}", target=target)
    else:
        target[prefix] = value


def _env_keys(source: str) -> set[str]:
    return {
        match.group(1)
        for line in source.splitlines()
        if (match := re.match(r"\s*(?:export\s+)?([A-Z][A-Z0-9_]{1,})\s*=", line))
    } | set(re.findall(r"\bPROOFSTACK_[A-Z0-9_]+\b", source))


def _compose_env_keys(source: str) -> set[str]:
    return set(re.findall(r"(?:^|[-{, ]\s*)([A-Z][A-Z0-9_]{2,})\s*(?:=|:)", source, re.M))


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        owner = _call_name(node.value)
        return f"{owner}.{node.attr}" if owner else node.attr
    return ""


def _constant_string(node: ast.AST) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _render_default(node: ast.AST | None) -> str | None:
    if node is None:
        return None
    try:
        value = ast.literal_eval(node)
    except (ValueError, TypeError):
        return "<expression>"
    return str(value)


def _deduplicate_references(values: list[EnvironmentReference]) -> list[EnvironmentReference]:
    unique = {(item.name, item.path, item.line): item for item in values}
    return sorted(unique.values(), key=lambda item: (item.path, item.line, item.name))


def _finding(
    rule_id: str,
    severity: Severity,
    title: str,
    description: str,
    path: str | None,
    line: int | None,
    remediation: str,
) -> Finding:
    fingerprint = hashlib.sha256(f"{rule_id}:{path}:{line}:{description}".encode()).hexdigest()
    return Finding(
        category=FindingCategory.CONFIGURATION,
        severity=severity,
        title=title,
        description=description,
        rule_id=rule_id,
        remediation=remediation,
        fingerprint=fingerprint,
        file_path=path,
        start_line=line,
        end_line=line,
    )
