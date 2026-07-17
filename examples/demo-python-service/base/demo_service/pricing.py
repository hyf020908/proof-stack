"""Pricing functions shared by HTTP, order, and reporting paths."""

from decimal import ROUND_HALF_UP, Decimal


def calculate_total(subtotal: Decimal, discount: Decimal = Decimal("0")) -> Decimal:
    """Return a non-negative two-decimal total after applying a discount."""
    total = max(Decimal("0"), subtotal - discount)
    return total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
