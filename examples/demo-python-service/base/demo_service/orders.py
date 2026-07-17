"""Order calculations that depend on the public pricing function."""

from decimal import Decimal

from demo_service.pricing import calculate_total


def summarize_order(subtotal: str, discount: str = "0") -> dict[str, str]:
    """Build the total returned by the order API."""
    total = calculate_total(Decimal(subtotal), Decimal(discount))
    return {"subtotal": subtotal, "discount": discount, "total": str(total)}
