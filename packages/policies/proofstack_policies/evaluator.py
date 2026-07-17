"""Deterministic and explainable policy evaluation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import fields, is_dataclass
from typing import Any

from .models import (
    Policy,
    PolicyDecision,
    PolicyEvaluation,
    PolicyOperator,
    PolicyOutcome,
    PolicyRule,
)
from .parser import PolicyValidationError, load_policy, parse_policy


class _MissingMetric:
    """Private sentinel used to distinguish missing values from explicit nulls."""


MISSING = _MissingMetric()


def _resolve_metric(metrics: Any, path: str) -> tuple[bool, Any]:
    current = metrics
    for segment in path.split("."):
        if isinstance(current, Mapping):
            if segment not in current:
                return False, None
            current = current[segment]
            continue
        if is_dataclass(current) and not isinstance(current, type):
            if segment not in {item.name for item in fields(current)}:
                return False, None
            current = getattr(current, segment)
            continue
        if hasattr(current, "__dict__"):
            attributes = vars(current)
            if segment not in attributes:
                return False, None
            current = attributes[segment]
            continue
        return False, None
    return True, current


def _ordered(value: Any) -> bool:
    return isinstance(value, int | float | str) and not isinstance(value, bool)


def _compare(operator: PolicyOperator, observed: Any, expected: Any, *, exists: bool) -> bool:
    if operator is PolicyOperator.EXISTS:
        return exists is expected
    if not exists:
        return False
    if operator is PolicyOperator.EQ:
        return bool(observed == expected)
    if operator is PolicyOperator.NEQ:
        return bool(observed != expected)
    if operator in {PolicyOperator.GT, PolicyOperator.GTE, PolicyOperator.LT, PolicyOperator.LTE}:
        if not _ordered(observed) or not _ordered(expected):
            return False
        try:
            if operator is PolicyOperator.GT:
                return bool(observed > expected)
            if operator is PolicyOperator.GTE:
                return bool(observed >= expected)
            if operator is PolicyOperator.LT:
                return bool(observed < expected)
            return bool(observed <= expected)
        except TypeError:
            return False
    if operator is PolicyOperator.IN:
        try:
            return bool(observed in expected)
        except TypeError:
            return False
    if operator is PolicyOperator.NOT_IN:
        try:
            return bool(observed not in expected)
        except TypeError:
            return False
    return False


def _display(value: Any, *, exists: bool = True) -> str:
    if not exists:
        return "<missing>"
    if isinstance(value, str):
        return repr(value)
    return repr(value)


def _explain(rule: PolicyRule, observed: Any, *, exists: bool, matched: bool) -> str:
    status = "satisfied" if matched else "violated"
    observed_text = _display(observed, exists=exists)
    expected_text = _display(rule.value)
    return (
        f"Rule '{rule.id}' {status}: metric '{rule.metric}' was {observed_text}; "
        f"expected operator '{rule.operator.value}' with {expected_text}."
    )


class PolicyEngine:
    """Evaluate validated policies against nested analysis metrics."""

    def evaluate(
        self,
        policy: Policy,
        metrics: Mapping[str, Any] | Any,
        *,
        evidence_by_metric: Mapping[str, Sequence[str]] | None = None,
    ) -> PolicyEvaluation:
        """Evaluate every rule and derive the strongest resulting verdict."""

        decisions: list[PolicyDecision] = []
        evidence_map = evidence_by_metric or {}
        for rule in policy.rules:
            exists, observed = _resolve_metric(metrics, rule.metric)
            matched = _compare(rule.operator, observed, rule.value, exists=exists)
            outcome = PolicyOutcome.PASS if matched else rule.outcome
            dynamic_evidence = tuple(str(item) for item in evidence_map.get(rule.metric, ()))
            references = tuple(dict.fromkeys((*rule.evidence, *dynamic_evidence)))
            decisions.append(
                PolicyDecision(
                    policy_name=policy.name,
                    rule_id=rule.id,
                    description=rule.description,
                    metric=rule.metric,
                    operator=rule.operator,
                    observed_value=observed if exists else None,
                    expected_value=rule.value,
                    matched=matched,
                    outcome=outcome,
                    explanation=_explain(rule, observed, exists=exists, matched=matched),
                    evidence_references=references,
                )
            )

        counts = {outcome.value: 0 for outcome in PolicyOutcome}
        for decision in decisions:
            counts[decision.outcome.value] += 1
        if counts[PolicyOutcome.FAIL.value]:
            verdict = PolicyOutcome.FAIL
        elif counts[PolicyOutcome.WARN.value]:
            verdict = PolicyOutcome.WARN
        else:
            verdict = PolicyOutcome.PASS
        summary = (
            f"Policy '{policy.name}' produced {counts['fail']} failure(s), "
            f"{counts['warn']} warning(s), and {counts['pass']} passing rule(s); "
            f"final verdict: {verdict.value}."
        )
        return PolicyEvaluation(
            policy_name=policy.name,
            policy_version=policy.version,
            verdict=verdict,
            decisions=tuple(decisions),
            summary=summary,
            counts=counts,
        )

    def evaluate_document(
        self,
        document: str | bytes | Mapping[str, Any],
        metrics: Mapping[str, Any] | Any,
        *,
        evidence_by_metric: Mapping[str, Sequence[str]] | None = None,
    ) -> PolicyEvaluation:
        """Parse and evaluate a YAML policy document."""

        return self.evaluate(parse_policy(document), metrics, evidence_by_metric=evidence_by_metric)


def evaluate_policy(
    policy: Policy,
    metrics: Mapping[str, Any] | Any,
    *,
    evidence_by_metric: Mapping[str, Sequence[str]] | None = None,
) -> PolicyEvaluation:
    """Convenience wrapper around the default policy engine."""

    return PolicyEngine().evaluate(policy, metrics, evidence_by_metric=evidence_by_metric)


__all__ = [
    "PolicyEngine",
    "PolicyValidationError",
    "evaluate_policy",
    "load_policy",
    "parse_policy",
]
