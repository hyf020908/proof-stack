"""Deterministic, explainable risk scoring for code-change analysis."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, ClassVar


def _non_negative(value: int | float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{name} must be numeric")
    if not math.isfinite(float(value)) or value < 0:
        raise ValueError(f"{name} must be a finite non-negative number")
    return float(value)


def _ratio(value: int | float, name: str) -> float:
    number = _non_negative(value, name)
    if number > 1:
        raise ValueError(f"{name} must be between 0 and 1")
    return number


@dataclass(frozen=True, slots=True)
class RiskFactors:
    """Normalized inputs consumed by the risk scorer."""

    changed_files: int = 0
    additions: int = 0
    deletions: int = 0
    high_complexity_symbols: int = 0
    high_fan_in_symbols: int = 0
    breaking_api_changes: int = 0
    database_migrations: int = 0
    dependency_changes: int = 0
    critical_findings: int = 0
    high_findings: int = 0
    medium_findings: int = 0
    low_findings: int = 0
    secrets_detected: int = 0
    test_evidence_score: float = 1.0
    requirement_coverage: float = 1.0
    failed_validations: int = 0
    config_drifts: int = 0
    ci_files_changed: int = 0

    def __post_init__(self) -> None:
        count_fields = (
            "changed_files",
            "additions",
            "deletions",
            "high_complexity_symbols",
            "high_fan_in_symbols",
            "breaking_api_changes",
            "database_migrations",
            "dependency_changes",
            "critical_findings",
            "high_findings",
            "medium_findings",
            "low_findings",
            "secrets_detected",
            "failed_validations",
            "config_drifts",
            "ci_files_changed",
        )
        for name in count_fields:
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        _ratio(self.test_evidence_score, "test_evidence_score")
        _ratio(self.requirement_coverage, "requirement_coverage")

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any]) -> RiskFactors:
        """Create factors from a flat mapping while rejecting unknown fields."""

        allowed = cls.__dataclass_fields__.keys()
        unknown = sorted(set(values) - set(allowed))
        if unknown:
            raise ValueError(f"unknown risk factors: {', '.join(unknown)}")
        return cls(**dict(values))


@dataclass(frozen=True, slots=True)
class RiskComponent:
    """One bounded and independently explainable risk contribution."""

    name: str
    score: float
    maximum: float
    explanation: str
    inputs: dict[str, int | float]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible representation."""

        return {
            "name": self.name,
            "score": round(self.score, 2),
            "maximum": round(self.maximum, 2),
            "explanation": self.explanation,
            "inputs": dict(self.inputs),
        }


@dataclass(frozen=True, slots=True)
class RiskAssessment:
    """Final score and the complete reasoning used to derive it."""

    score: int
    level: str
    raw_score: float
    components: tuple[RiskComponent, ...]
    floors_applied: tuple[str, ...]
    explanation: str

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible representation."""

        return {
            "score": self.score,
            "level": self.level,
            "raw_score": round(self.raw_score, 2),
            "components": [component.to_dict() for component in self.components],
            "floors_applied": list(self.floors_applied),
            "explanation": self.explanation,
        }


class RiskScorer:
    """Calculate risk with weights that sum to exactly 100 points."""

    WEIGHTS: ClassVar[Mapping[str, float]] = MappingProxyType(
        {
            "change_surface": 10.0,
            "complexity_and_fan_in": 8.0,
            "api_compatibility": 10.0,
            "database": 7.0,
            "dependencies": 6.0,
            "security_findings": 20.0,
            "secrets": 12.0,
            "test_gap": 8.0,
            "requirement_gap": 6.0,
            "validation": 8.0,
            "configuration": 3.0,
            "ci_changes": 2.0,
        }
    )

    @staticmethod
    def _component(
        name: str,
        score: float,
        explanation: str,
        inputs: dict[str, int | float],
    ) -> RiskComponent:
        maximum = RiskScorer.WEIGHTS[name]
        return RiskComponent(
            name=name,
            score=max(0.0, min(maximum, score)),
            maximum=maximum,
            explanation=explanation,
            inputs=inputs,
        )

    def score(self, factors: RiskFactors | Mapping[str, Any]) -> RiskAssessment:
        """Score normalized factors on a conservative 0 through 100 scale."""

        if not isinstance(factors, RiskFactors):
            factors = RiskFactors.from_mapping(factors)
        lines = factors.additions + factors.deletions
        components = (
            self._component(
                "change_surface",
                min(5.0, factors.changed_files * 0.5) + min(5.0, lines / 200.0),
                "Changed file count and total line churn increase review surface.",
                {"changed_files": factors.changed_files, "changed_lines": lines},
            ),
            self._component(
                "complexity_and_fan_in",
                min(4.0, factors.high_complexity_symbols * 1.0)
                + min(4.0, factors.high_fan_in_symbols * 1.0),
                "Complex or heavily reused changed symbols have a wider failure radius.",
                {
                    "high_complexity_symbols": factors.high_complexity_symbols,
                    "high_fan_in_symbols": factors.high_fan_in_symbols,
                },
            ),
            self._component(
                "api_compatibility",
                factors.breaking_api_changes * 5.0,
                "Potentially breaking public API changes require migration evidence.",
                {"breaking_api_changes": factors.breaking_api_changes},
            ),
            self._component(
                "database",
                factors.database_migrations * 3.5,
                "Database migrations can affect availability and data compatibility.",
                {"database_migrations": factors.database_migrations},
            ),
            self._component(
                "dependencies",
                factors.dependency_changes * 1.5,
                "Dependency changes alter the build and software supply chain.",
                {"dependency_changes": factors.dependency_changes},
            ),
            self._component(
                "security_findings",
                factors.critical_findings * 20.0
                + factors.high_findings * 7.0
                + factors.medium_findings * 2.5
                + factors.low_findings * 0.5,
                "Security findings are weighted by severity.",
                {
                    "critical": factors.critical_findings,
                    "high": factors.high_findings,
                    "medium": factors.medium_findings,
                    "low": factors.low_findings,
                },
            ),
            self._component(
                "secrets",
                factors.secrets_detected * 12.0,
                "A detected secret creates immediate credential exposure risk.",
                {"secrets_detected": factors.secrets_detected},
            ),
            self._component(
                "test_gap",
                (1.0 - factors.test_evidence_score) * 8.0,
                "Lower test evidence raises the chance of an undetected regression.",
                {"test_evidence_score": factors.test_evidence_score},
            ),
            self._component(
                "requirement_gap",
                (1.0 - factors.requirement_coverage) * 6.0,
                "Unsupported requirements weaken acceptance confidence.",
                {"requirement_coverage": factors.requirement_coverage},
            ),
            self._component(
                "validation",
                factors.failed_validations * 4.0,
                "Failed validation commands provide direct negative execution evidence.",
                {"failed_validations": factors.failed_validations},
            ),
            self._component(
                "configuration",
                factors.config_drifts * 1.5,
                "Configuration drift can make deployments differ from tested behavior.",
                {"config_drifts": factors.config_drifts},
            ),
            self._component(
                "ci_changes",
                factors.ci_files_changed * 2.0,
                "CI changes can alter the controls used to accept future changes.",
                {"ci_files_changed": factors.ci_files_changed},
            ),
        )
        raw_score = min(100.0, sum(component.score for component in components))
        score = math.ceil(raw_score)
        floors: list[str] = []
        if factors.critical_findings and score < 90:
            score = 90
            floors.append("Critical security finding floor raised the score to 90.")
        if factors.secrets_detected and score < 75:
            score = 75
            floors.append("Detected secret floor raised the score to 75.")
        if factors.high_findings >= 3 and score < 70:
            score = 70
            floors.append("Multiple high-severity findings floor raised the score to 70.")
        score = min(100, score)
        level = self._level(score)
        explanation = (
            f"Weighted components totaled {raw_score:.2f}/100; the final score is "
            f"{score}/100 ({level})."
        )
        if floors:
            explanation += " " + " ".join(floors)
        return RiskAssessment(
            score=score,
            level=level,
            raw_score=raw_score,
            components=components,
            floors_applied=tuple(floors),
            explanation=explanation,
        )

    @staticmethod
    def _level(score: int) -> str:
        if score >= 80:
            return "critical"
        if score >= 60:
            return "high"
        if score >= 35:
            return "medium"
        if score >= 15:
            return "low"
        return "minimal"


def score_risk(factors: RiskFactors | Mapping[str, Any]) -> RiskAssessment:
    """Convenience wrapper around the default deterministic scorer."""

    return RiskScorer().score(factors)
