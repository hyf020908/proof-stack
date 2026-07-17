from __future__ import annotations

from pathlib import Path

import pytest
from proofstack_policies import (
    PolicyEngine,
    PolicyOutcome,
    PolicyValidationError,
    load_policy,
    parse_policy,
)

POLICY_TEXT = """
name: acceptance
version: 1
rules:
  - id: critical
    description: Critical findings are forbidden
    metric: findings.critical
    operator: eq
    value: 0
    outcome: fail
    evidence: [findings.json]
  - id: coverage
    description: Requirement coverage should be high
    metric: requirements.coverage
    operator: gte
    value: 0.7
    outcome: warn
  - id: validation
    description: A validation must pass
    metric: validation.passed
    operator: gt
    value: 0
    outcome: fail
"""


def test_policy_engine_produces_explainable_strongest_verdict() -> None:
    policy = parse_policy(POLICY_TEXT)
    evaluation = PolicyEngine().evaluate(
        policy,
        {
            "findings": {"critical": 0},
            "requirements": {"coverage": 0.4},
            "validation": {"passed": 0},
        },
        evidence_by_metric={"requirements.coverage": ["requirements.json#REQ-1"]},
    )

    assert evaluation.verdict is PolicyOutcome.FAIL
    assert evaluation.counts == {"pass": 1, "warn": 1, "fail": 1}
    coverage = next(item for item in evaluation.decisions if item.rule_id == "coverage")
    assert coverage.observed_value == 0.4
    assert coverage.expected_value == 0.7
    assert coverage.evidence_references == ("requirements.json#REQ-1",)
    assert "violated" in coverage.explanation
    critical = next(item for item in evaluation.decisions if item.rule_id == "critical")
    assert critical.evidence_references == ("findings.json",)


@pytest.mark.parametrize(
    ("operator", "observed", "expected", "matched"),
    [
        ("eq", "safe", "safe", True),
        ("neq", "safe", "unsafe", True),
        ("gt", 5, 4, True),
        ("gte", 5, 5, True),
        ("lt", 4, 5, True),
        ("lte", 5, 5, True),
        ("in", "high", ["high", "critical"], True),
        ("not_in", "low", ["high", "critical"], True),
        ("exists", "anything", True, True),
    ],
)
def test_every_supported_operator(
    operator: str, observed: object, expected: object, matched: bool
) -> None:
    policy = parse_policy(
        {
            "name": "operators",
            "version": 1,
            "rules": [
                {
                    "id": operator,
                    "description": "Operator contract",
                    "metric": "value",
                    "operator": operator,
                    "value": expected,
                    "outcome": "fail",
                }
            ],
        }
    )
    decision = PolicyEngine().evaluate(policy, {"value": observed}).decisions[0]
    assert decision.matched is matched
    assert decision.outcome is PolicyOutcome.PASS


def test_exists_can_require_a_metric_to_be_absent() -> None:
    policy = parse_policy(
        """
name: absence
version: 1
rules:
  - id: removed
    metric: deprecated.value
    operator: exists
    value: false
    outcome: fail
"""
    )

    decision = PolicyEngine().evaluate(policy, {}).decisions[0]
    assert decision.matched
    assert decision.observed_value is None
    assert "<missing>" in decision.explanation


def test_parser_rejects_duplicate_rules_and_unsafe_yaml() -> None:
    duplicate = """
name: duplicate
version: 1
rules:
  - {id: same, metric: value, operator: eq, value: 1}
  - {id: same, metric: other, operator: eq, value: 2}
"""
    with pytest.raises(PolicyValidationError, match="duplicate rule"):
        parse_policy(duplicate)
    with pytest.raises(PolicyValidationError, match="invalid YAML"):
        parse_policy("!!python/object/apply:os.system ['echo unsafe']")


def test_load_policy_enforces_size_limit(tmp_path: Path) -> None:
    path = tmp_path / "policy.yml"
    path.write_text(POLICY_TEXT, encoding="utf-8")
    assert load_policy(path).name == "acceptance"
    with pytest.raises(PolicyValidationError, match="exceeds"):
        load_policy(path, max_bytes=8)
