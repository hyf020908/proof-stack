"""Explainable code and API impact detection."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from proofstack_core import Finding, FindingCategory, Severity

from .graph import BlastRadius, DependencyGraph
from .python_ast import PythonAnalysis, PythonSymbol
from .routes import FastAPIRoute, RouteChange, compare_routes


@dataclass(slots=True)
class ImpactResult:
    changed_symbols: list[str] = field(default_factory=list)
    signature_changes: list[tuple[str, str, str]] = field(default_factory=list)
    removed_exports: list[str] = field(default_factory=list)
    high_fan_in_symbols: list[tuple[str, int]] = field(default_factory=list)
    route_changes: list[RouteChange] = field(default_factory=list)
    blast_radius: BlastRadius | None = None
    findings: list[Finding] = field(default_factory=list)


class ImpactAnalyzer:
    def analyze(
        self,
        previous: list[PythonAnalysis],
        current: list[PythonAnalysis],
        graph: DependencyGraph,
        changed_symbols: list[str],
        *,
        previous_routes: list[FastAPIRoute] | None = None,
        current_routes: list[FastAPIRoute] | None = None,
        high_fan_in_threshold: int = 3,
    ) -> ImpactResult:
        result = ImpactResult(changed_symbols=sorted(changed_symbols))
        before = _symbols(previous)
        after = _symbols(current)
        for name in sorted(before.keys() & after.keys()):
            if before[name].signature != after[name].signature:
                result.signature_changes.append(
                    (name, before[name].signature, after[name].signature)
                )
                result.findings.append(
                    _finding(
                        "impact.python-signature-changed",
                        Severity.HIGH if before[name].exported else Severity.MEDIUM,
                        "Python callable signature changed",
                        f"{name} changed from {before[name].signature} to {after[name].signature}.",
                        after[name].path,
                        after[name].start_line,
                        (
                            "Review all callers and preserve compatibility or publish a "
                            "migration path."
                        ),
                    )
                )
            if (
                before[name].return_shapes != after[name].return_shapes
                or before[name].raises != after[name].raises
            ):
                result.findings.append(
                    _finding(
                        "impact.python-behavior-changed",
                        Severity.MEDIUM,
                        "Python return or exception behavior changed",
                        f"The observable return or exception structure of {name} changed.",
                        after[name].path,
                        after[name].start_line,
                        "Validate successful returns, boundary inputs, and documented exceptions.",
                    )
                )
        for name in sorted(before.keys() - after.keys()):
            if before[name].exported:
                result.removed_exports.append(name)
                result.findings.append(
                    _finding(
                        "impact.public-export-removed",
                        Severity.HIGH,
                        "Public Python symbol removed",
                        f"The exported symbol {name} no longer exists.",
                        before[name].path,
                        before[name].start_line,
                        "Restore the symbol or document a versioned migration path.",
                    )
                )
        result.blast_radius = graph.blast_radius(
            [name if name.startswith("symbol:") else f"symbol:{name}" for name in changed_symbols]
        )
        for name in sorted(changed_symbols):
            node_id = name if name.startswith("symbol:") else f"symbol:{name}"
            fan_in = graph.fan_in(node_id, edge_types={"calls", "inherits"})
            if fan_in >= high_fan_in_threshold:
                result.high_fan_in_symbols.append((name, fan_in))
                symbol = after.get(name.removeprefix("symbol:"))
                result.findings.append(
                    _finding(
                        "impact.high-fan-in-change",
                        Severity.HIGH,
                        "High fan-in symbol changed",
                        f"{name} has {fan_in} incoming dependencies.",
                        symbol.path if symbol else None,
                        symbol.start_line if symbol else None,
                        "Run validation for every direct and transitive dependent.",
                    )
                )
        result.route_changes = compare_routes(previous_routes or [], current_routes or [])
        for change in result.route_changes:
            if not change.breaking:
                continue
            result.findings.append(
                _finding(
                    "impact.fastapi-breaking-change",
                    Severity.HIGH,
                    "Potentially breaking API change",
                    f"{change.route.method} {change.route.path}: {change.explanation}",
                    None,
                    change.route.line,
                    "Version the route or update and validate every known API consumer.",
                )
            )
        return result


def _symbols(analyses: list[PythonAnalysis]) -> dict[str, PythonSymbol]:
    return {symbol.qualified_name: symbol for analysis in analyses for symbol in analysis.symbols}


def _finding(
    rule_id: str,
    severity: Severity,
    title: str,
    description: str,
    path: str | None,
    line: int | None,
    remediation: str,
) -> Finding:
    digest = hashlib.sha256(f"{rule_id}:{path}:{line}:{description}".encode()).hexdigest()
    return Finding(
        category=FindingCategory.IMPACT,
        severity=severity,
        title=title,
        description=description,
        rule_id=rule_id,
        remediation=remediation,
        fingerprint=digest,
        file_path=path,
        start_line=line,
        end_line=line,
    )
