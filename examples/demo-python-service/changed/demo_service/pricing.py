"""Pricing functions shared by HTTP, order, and reporting paths."""

from decimal import ROUND_HALF_UP, Decimal


def calculate_total(
    subtotal: Decimal,
    currency: str,
    discount: Decimal = Decimal("0"),
) -> Decimal:
    """Return a currency-aware non-negative total after applying a discount."""
    if currency not in {"USD", "EUR"}:
        raise ValueError(f"Unsupported currency: {currency}")
    total = max(Decimal("0"), subtotal - discount)
    return total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
