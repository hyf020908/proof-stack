"""HTTP interface for the baseline demo service."""

from decimal import Decimal

from fastapi import FastAPI

from demo_service.config import SERVICE_NAME
from demo_service.orders import summarize_order
from demo_service.pricing import calculate_total

app = FastAPI(title=SERVICE_NAME)


@app.get("/health")
def health() -> dict[str, str]:
    """Report process health."""
    return {"status": "healthy"}


@app.get("/orders/preview")
def preview_order(subtotal: str, discount: str = "0") -> dict[str, str]:
    """Preview a calculated order without persistence."""
    return summarize_order(subtotal, discount)


@app.get("/pricing/example")
def pricing_example() -> dict[str, str]:
    """Expose a stable example used by an integration test."""
    return {"total": str(calculate_total(Decimal("10.00")))}
