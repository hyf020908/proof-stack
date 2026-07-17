"""Typed models shared by the policy parser and evaluator."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class PolicyOperator(StrEnum):
    """Operators supported by the deterministic policy evaluator."""

    EQ = "eq"
    NEQ = "neq"
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"
    IN = "in"
    NOT_IN = "not_in"
    EXISTS = "exists"


class PolicyOutcome(StrEnum):
    """Possible outcomes for an individual rule and a complete policy."""

    PASS = "pass"  # noqa: S105
    WARN = "warn"
    FAIL = "fail"


@dataclass(frozen=True, slots=True)
class PolicyRule:
    """A single policy assertion over an analysis metric."""

    id: str
    description: str
    metric: str
    operator: PolicyOperator
    value: Any = None
    outcome: PolicyOutcome = PolicyOutcome.FAIL
    evidence: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible representation."""

        return {
            "id": self.id,
            "description": self.description,
            "metric": self.metric,
            "operator": self.operator.value,
            "value": self.value,
            "outcome": self.outcome.value,
            "evidence": list(self.evidence),
        }


@dataclass(frozen=True, slots=True)
class Policy:
    """A validated policy document."""

    name: str
    version: int
    rules: tuple[PolicyRule, ...]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible representation."""

        return {
            "name": self.name,
            "version": self.version,
            "rules": [rule.to_dict() for rule in self.rules],
        }


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    """Explainable result of evaluating one policy rule."""

    policy_name: str
    rule_id: str
    description: str
    metric: str
    operator: PolicyOperator
    observed_value: Any
    expected_value: Any
    matched: bool
    outcome: PolicyOutcome
    explanation: str
    evidence_references: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible representation."""

        return {
            "policy_name": self.policy_name,
            "rule_id": self.rule_id,
            "description": self.description,
            "metric": self.metric,
            "operator": self.operator.value,
            "observed_value": self.observed_value,
            "expected_value": self.expected_value,
            "matched": self.matched,
            "outcome": self.outcome.value,
            "explanation": self.explanation,
            "evidence_references": list(self.evidence_references),
        }


@dataclass(frozen=True, slots=True)
class PolicyEvaluation:
    """Aggregate policy verdict with all rule-level evidence."""

    policy_name: str
    policy_version: int
    verdict: PolicyOutcome
    decisions: tuple[PolicyDecision, ...]
    summary: str
    counts: dict[str, int] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        """Return whether no warning or failure was emitted."""

        return self.verdict is PolicyOutcome.PASS

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible representation."""

        return {
            "policy_name": self.policy_name,
            "policy_version": self.policy_version,
            "verdict": self.verdict.value,
            "summary": self.summary,
            "counts": dict(self.counts),
            "decisions": [decision.to_dict() for decision in self.decisions],
        }
