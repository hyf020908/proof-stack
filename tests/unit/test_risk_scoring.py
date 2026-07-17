from __future__ import annotations

import pytest
from proofstack_policies import RiskFactors, RiskScorer, score_risk


def test_risk_weights_sum_to_one_hundred() -> None:
    assert sum(RiskScorer.WEIGHTS.values()) == 100


def test_zero_change_has_zero_risk_and_all_components() -> None:
    result = score_risk(RiskFactors())

    assert result.score == 0
    assert result.level == "minimal"
    assert len(result.components) == len(RiskScorer.WEIGHTS)
    assert sum(component.score for component in result.components) == 0
    assert result.floors_applied == ()


def test_risk_score_is_deterministic_and_explainable() -> None:
    factors = RiskFactors(
        changed_files=4,
        additions=300,
        deletions=100,
        high_complexity_symbols=2,
        high_fan_in_symbols=1,
        breaking_api_changes=1,
        dependency_changes=2,
        test_evidence_score=0.5,
        requirement_coverage=0.75,
        failed_validations=1,
        config_drifts=1,
        ci_files_changed=1,
    )

    first = RiskScorer().score(factors)
    second = RiskScorer().score(factors)
    assert first == second
    assert 0 < first.score < 100
    assert first.raw_score == pytest.approx(sum(item.score for item in first.components))
    assert all(item.explanation and item.inputs for item in first.components)
    assert "Weighted components" in first.explanation


def test_severe_security_floors_override_low_weighted_score() -> None:
    critical = score_risk(RiskFactors(critical_findings=1))
    secret = score_risk(RiskFactors(secrets_detected=1))
    multiple_high = score_risk(RiskFactors(high_findings=3))

    assert critical.score == 90
    assert secret.score == 75
    assert multiple_high.score == 70
    assert critical.raw_score == 20
    assert critical.floors_applied


def test_risk_inputs_are_validated() -> None:
    with pytest.raises(ValueError, match="between 0 and 1"):
        RiskFactors(test_evidence_score=1.1)
    with pytest.raises(ValueError, match="non-negative integer"):
        RiskFactors(changed_files=-1)
    with pytest.raises(ValueError, match="unknown risk factors"):
        score_risk({"surprise": 1})
