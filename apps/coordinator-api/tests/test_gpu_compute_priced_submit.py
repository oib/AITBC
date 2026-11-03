"""A gpu_compute job submitted without a usable price is refused (#805)."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from coordinator_api.contexts.infrastructure.routers import client as client_router
from coordinator_api.schemas import JobCreate


def _job(payload_type: str = "gpu_compute", amount: Decimal | None = None) -> JobCreate:
    return JobCreate(payload={"type": payload_type, "duration_hours": 1}, payment_amount=amount)


@pytest.mark.parametrize("amount", [None, Decimal("0"), Decimal("-1"), Decimal("-0.000001")])
def test_an_unpriced_gpu_compute_job_is_refused(amount: Decimal | None) -> None:
    with pytest.raises(HTTPException) as exc:
        client_router._require_priced_gpu_compute(_job(amount=amount))
    assert exc.value.status_code == 422
    assert "payment_amount" in exc.value.detail


@pytest.mark.parametrize("amount", [Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity")])
def test_a_non_finite_price_never_reaches_the_check(amount: Decimal) -> None:
    # JobCreate refuses these itself; pin that so the check can rely on it.
    with pytest.raises(ValidationError):
        _job(amount=amount)


def test_a_priced_gpu_compute_job_passes() -> None:
    client_router._require_priced_gpu_compute(_job(amount=Decimal("0.5")))


def test_other_job_types_are_not_affected() -> None:
    client_router._require_priced_gpu_compute(_job(payload_type="inference"))
    client_router._require_priced_gpu_compute(JobCreate(payload={}))


@pytest.mark.asyncio
async def test_submit_refuses_before_touching_the_database() -> None:
    # session=None: the refusal must come before JobService is built.
    with pytest.raises(HTTPException) as exc:
        await client_router._submit_job_impl(_job(), None, {"sub": "client-1"})  # type: ignore[arg-type]
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_an_offer_bought_gpu_compute_job_is_priced_by_the_quote(monkeypatch) -> None:
    """offer_id + no payment_amount: the quote fills the price before the check (#805 edge)."""
    quote = SimpleNamespace(
        offer_id="gpu-offer-1",
        provider_address="0xProvider",
        total=Decimal("2.5"),
        describe=lambda: "2.5 AIT x 1",
    )

    async def fake_resolve(offer_id, quantity):
        return quote

    monkeypatch.setattr(client_router, "resolve_offer", fake_resolve)
    req = JobCreate(payload={"type": "gpu_compute", "duration_hours": 1}, offer_id="gpu-offer-1")

    priced, _ = await client_router._apply_offer_quote(req)

    assert priced.payment_amount == Decimal("2.5")
    client_router._require_priced_gpu_compute(priced)
