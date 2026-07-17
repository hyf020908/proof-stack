"""Reporting helpers with another dependency on pricing."""

from decimal import Decimal

from demo_service.pricing import calculate_total


def projected_revenue(subtotals: list[str]) -> str:
    """Aggregate order totals into a display value."""
    total = sum((calculate_total(Decimal(value)) for value in subtotals), Decimal("0"))
    return str(total)
