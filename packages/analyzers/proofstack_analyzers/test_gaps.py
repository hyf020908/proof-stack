"""Test discovery, source mapping, evidence scoring, and gap suggestions."""

from __future__ import annotations

import ast
import hashlib
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from proofstack_core import Finding, FindingCategory, Severity

from .requirements import RequirementMappingResult


@dataclass(slots=True)
class TestCaseEvidence:
    path: str
    framework: str
    tests: list[str] = field(default_factory=list)
    fixtures: list[str] = field(default_factory=list)
    imported_modules: list[str] = field(default_factory=list)
    integration: bool = False


@dataclass(slots=True, frozen=True)
class SuggestedTest:
    name: str
    target: str
    preconditions: tuple[str, ...]
    inputs: tuple[str, ...]
    assertions: tuple[str, ...]
    edge_cases: tuple[str, ...]
    recommended_path: str


@dataclass(slots=True)
class TestGapResult:
    discovered_tests: list[TestCaseEvidence]
    source_to_tests: dict[str, list[str]]
    uncovered_sources: list[str]
    evidence_score: float
    suggestions: list[SuggestedTest]
    findings: list[Finding]


class TestGapAnalyzer:
    def discover(self, files: Mapping[str, str]) -> list[TestCaseEvidence]:
        discovered: list[TestCaseEvidence] = []
        for path, source in sorted(files.items()):
            framework = _test_framework(path, source)
            if framework is None:
                continue
            evidence = TestCaseEvidence(
                path=path,
                framework=framework,
                integration=any(
                    token in path.lower() for token in ("integration", "e2e", "contract")
                ),
            )
            if path.endswith(".py"):
                _extract_python_test_details(source, evidence)
            else:
                evidence.tests.extend(re.findall(r"\b(?:it|test)\s*\(\s*['\"]([^'\"]+)", source))
                evidence.imported_modules.extend(
                    match.group(1) for match in re.finditer(r"from\s+['\"]([^'\"]+)['\"]", source)
                )
            discovered.append(evidence)
        return discovered

    def analyze(
        self,
        files: Mapping[str, str],
        changed_sources: Sequence[str],
        *,
        changed_symbols: Sequence[str] = (),
        high_risk_sources: Sequence[str] = (),
        public_api_sources: Sequence[str] = (),
        changed_tests: Sequence[str] = (),
        requirement_mapping: RequirementMappingResult | None = None,
    ) -> TestGapResult:
        tests = self.discover(files)
        mapping: dict[str, list[str]] = {}
        findings: list[Finding] = []
        suggestions: list[SuggestedTest] = []
        changed_test_set = set(changed_tests)
        for source_path in sorted(set(changed_sources)):
            related = [
                test.path
                for test in tests
                if _test_matches_source(test, source_path, changed_symbols)
            ]
            mapping[source_path] = sorted(set(related))
            if not related:
                severity = Severity.MEDIUM if changed_test_set else Severity.HIGH
                findings.append(
                    _finding(
                        "test.changed-source-without-evidence",
                        severity,
                        "Changed source has no related test evidence",
                        f"No discovered test maps to {source_path}.",
                        source_path,
                        (
                            "Add focused regression tests that import and exercise the "
                            "changed behavior."
                        ),
                    )
                )
                suggestions.append(_suggestion(source_path, changed_symbols))
            if source_path in public_api_sources and not any(
                test.integration for test in tests if test.path in related
            ):
                findings.append(
                    _finding(
                        "test.public-api-without-integration-test",
                        Severity.HIGH,
                        "Public API change lacks integration evidence",
                        f"{source_path} changes a public API without a mapped integration test.",
                        source_path,
                        (
                            "Add an integration test covering request, response, error, "
                            "and compatibility behavior."
                        ),
                    )
                )
            if (
                source_path in high_risk_sources
                and related
                and not any(test.integration for test in tests if test.path in related)
            ):
                findings.append(
                    _finding(
                        "test.high-risk-only-unit-tested",
                        Severity.MEDIUM,
                        "High-risk change has only unit-test evidence",
                        f"Mapped tests for {source_path} do not include an integration test.",
                        source_path,
                        "Add an integration scenario across the affected dependency boundary.",
                    )
                )
        if requirement_mapping is not None:
            for requirement in requirement_mapping.mappings:
                if not requirement.tests:
                    findings.append(
                        _finding(
                            "test.requirement-without-test-evidence",
                            Severity.MEDIUM if requirement.supported else Severity.HIGH,
                            "Requirement lacks test evidence",
                            (
                                f"Requirement {requirement.requirement_id} has change evidence "
                                "but no linked test."
                            ),
                            None,
                            "Link or add a test that directly proves the acceptance criterion.",
                        )
                    )
        covered = sum(bool(mapping[path]) for path in mapping)
        source_score = covered / len(mapping) if mapping else 1.0
        changed_test_bonus = min(0.15, len(changed_test_set) * 0.03)
        requirement_score = (
            requirement_mapping.coverage_score if requirement_mapping else source_score
        )
        score = min(1.0, source_score * 0.75 + requirement_score * 0.25 + changed_test_bonus)
        return TestGapResult(
            discovered_tests=tests,
            source_to_tests=mapping,
            uncovered_sources=sorted(path for path, related in mapping.items() if not related),
            evidence_score=round(score, 4),
            suggestions=suggestions,
            findings=findings,
        )


def _test_framework(path: str, source: str) -> str | None:
    lowered = path.lower()
    if path.endswith(".py") and (
        re.search(r"(^|/)(test_.+|.+_test)\.py$", lowered)
        or "import pytest" in source
        or "unittest.TestCase" in source
    ):
        return "pytest" if "pytest" in source or "unittest" not in source else "unittest"
    if re.search(r"\.(?:test|spec)\.[jt]sx?$", lowered):
        return (
            "playwright"
            if "@playwright/test" in source
            else "vitest"
            if "vitest" in source
            else "jest"
        )
    if "playwright" in lowered and re.search(r"\btest\s*\(", source):
        return "playwright"
    return None


def _extract_python_test_details(source: str, evidence: TestCaseEvidence) -> None:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            if node.name.startswith("test_"):
                evidence.tests.append(node.name)
                evidence.fixtures.extend(
                    argument.arg
                    for argument in node.args.args
                    if argument.arg not in {"self", "cls"}
                )
        elif isinstance(node, ast.Import):
            evidence.imported_modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            evidence.imported_modules.append(node.module)


def _test_matches_source(
    test: TestCaseEvidence,
    source_path: str,
    changed_symbols: Sequence[str],
) -> bool:
    source = PurePosixPath(source_path)
    module_candidates = _module_candidates(source)
    basename = source.stem.removeprefix("test_")
    test_name = PurePosixPath(test.path).stem.removeprefix("test_").removesuffix("_test")
    if basename == test_name or any(
        any(
            imported == candidate or imported.startswith(candidate + ".")
            for candidate in module_candidates
        )
        for imported in test.imported_modules
    ):
        return True
    short_symbols = {
        item.rsplit(".", 1)[-1]
        for item in changed_symbols
        if any(
            item == candidate or item.startswith(candidate + ".") for candidate in module_candidates
        )
    }
    searchable = " ".join([*test.tests, *test.fixtures]).lower()
    return any(len(symbol) > 3 and symbol.lower() in searchable for symbol in short_symbols)


def _module_candidates(source: PurePosixPath) -> list[str]:
    parts = list(source.with_suffix("").parts)
    values = [".".join(parts)]
    if parts and parts[0] in {"src", "lib", "python"}:
        values.append(".".join(parts[1:]))
    return [value for value in values if value]


def _suggestion(path: str, changed_symbols: Sequence[str]) -> SuggestedTest:
    stem = PurePosixPath(path).stem
    target = next((item for item in changed_symbols if stem in item), path)
    return SuggestedTest(
        name=f"test_{stem}_changed_behavior",
        target=target,
        preconditions=("Construct the smallest valid dependency set.",),
        inputs=("A representative valid input.", "An invalid boundary input."),
        assertions=("Assert the documented output.", "Assert the expected error behavior."),
        edge_cases=("Empty input.", "Boundary-sized input.", "Dependency failure."),
        recommended_path=f"tests/test_{stem}.py",
    )


def _finding(
    rule_id: str,
    severity: Severity,
    title: str,
    description: str,
    path: str | None,
    remediation: str,
) -> Finding:
    fingerprint = hashlib.sha256(f"{rule_id}:{path}:{description}".encode()).hexdigest()
    return Finding(
        category=FindingCategory.TEST,
        severity=severity,
        title=title,
        description=description,
        rule_id=rule_id,
        remediation=remediation,
        fingerprint=fingerprint,
        file_path=path,
    )
