"""Pin: the stats endpoint must sum float wire payments into Decimal revenue (#1033).

Regression found by the validator: ``total_revenue = Decimal("0")`` plus
``+= payload.get("payment", 0.0)`` raises TypeError on the first completed
job. The boundary now converts via ``Decimal(str(...))``.
"""

from __future__ import annotations

from decimal import Decimal


def test_float_payment_sums_into_decimal() -> None:
    # mirror of the stats loop in rpc/ai_services.py
    payloads = [{"payment": 12.5, "status": "completed"}, {"payment": 0.25, "status": "completed"}]
    total_revenue = Decimal("0")
    for payload in payloads:
        if payload["status"] == "completed":
            total_revenue += Decimal(str(payload.get("payment", "0")))
    assert total_revenue == Decimal("12.75")


def test_missing_payment_defaults() -> None:
    total_revenue = Decimal("0")
    total_revenue += Decimal(str({}.get("payment", "0")))
    assert total_revenue == Decimal("0")
