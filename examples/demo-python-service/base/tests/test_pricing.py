"""Focused pricing regression tests for the baseline snapshot."""

from decimal import Decimal

from demo_service.pricing import calculate_total


def test_calculate_total_applies_discount() -> None:
    assert calculate_total(Decimal("12.50"), Decimal("2.25")) == Decimal("10.25")


def test_calculate_total_never_returns_negative_value() -> None:
    assert calculate_total(Decimal("2.00"), Decimal("4.00")) == Decimal("0.00")
