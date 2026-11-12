"""#1790: cancel/confirm_pin lifecycle writes are compare-and-swap.

Before the fix both methods read state, checked it, then wrote — two
concurrent calls could both pass the check and both commit, leaving e.g. a
CANCELED job with an escrowed payment. The conditional UPDATE ... WHERE
state-predicate makes exactly one transition win; the loser rolls back
(including its payment flip) and reports the state that actually landed.
"""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest
from market_service.domain.market import MarketJob, MarketJobPayment, SoftwareService
from market_service.services.market_service import MarketService
from market_service.storage import get_session_context

pytestmark = pytest.mark.asyncio


class _StubRPC:
    """Escrow proof for confirm_pin's pending->escrowed gate."""

    async def verify_escrow(self, job_id: str):
        return {"state": "locked", "amount": "1.0", "buyer": "0x" + "11" * 20, "provider": "0x" + "22" * 20}


async def _seed() -> str:
    """QUEUED job + pending payment + registered offer, escrow proof stubbed."""
    uid = uuid4().hex[:8]
    offer_id = f"offer_cas_{uid}"
    async with get_session_context() as session:
        svc = MarketService(session)
        svc.session.add(SoftwareService(service_type="ipfs", offer_id=offer_id))
        created = await svc.create_market_job(
            {
                "service_type": "ipfs",
                "buyer_address": "0x" + "11" * 20,
                "provider_address": "0x" + "22" * 20,
                "offer_id": offer_id,
                "payload": {"cid": "QmTest"},
                "payment": {"amount": "1.0", "status": "pending"},
            }
        )
        job_id = created["job_id"]
    return job_id


async def _state_and_payment(job_id: str) -> tuple[str, str | None]:
    async with get_session_context() as session:
        job = await session.get(MarketJob, job_id)
        payment = await session.get(MarketJobPayment, job.payment_id) if job and job.payment_id else None
        return job.state, (payment.status if payment else None)


async def test_cancel_then_confirm_pin_cannot_resurrect() -> None:
    """Sequential form of the race: once cancel wins, pin-confirm must not
    flip the job back to RUNNING or escrow the payment."""
    job_id = await _seed()
    async with get_session_context() as session:
        svc = MarketService(session)
        await svc.cancel_market_job(job_id, reason="buyer_requested")
    async with get_session_context() as session:
        svc = MarketService(session)
        svc._rpc_client = _StubRPC()  # type: ignore[assignment]
        # #1922: provider_confirmed is the only path that mints RUNNING.
        out = await svc.confirm_market_job_pin(job_id, size=5, provider_confirmed=True)
    assert out["state"] == "CANCELED"
    state, pay = await _state_and_payment(job_id)
    assert state == "CANCELED"
    assert pay != "escrowed"


async def test_concurrent_cancel_and_pin_exactly_one_wins() -> None:
    """The actual interleave: run both transitions against separate sessions.
    Exactly one may win; the loser must leave NO mixed state behind —
    never CANCELED-with-escrowed-payment or RUNNING-with-refund_pending."""
    for _ in range(10):
        job_id = await _seed()
        async with get_session_context() as s1, get_session_context() as s2:
            cancel_svc = MarketService(s1)
            pin_svc = MarketService(s2)
            pin_svc._rpc_client = _StubRPC()  # type: ignore[assignment]
            await asyncio.gather(
                cancel_svc.cancel_market_job(job_id, reason="race"),
                pin_svc.confirm_market_job_pin(job_id, size=5, provider_confirmed=True),
                return_exceptions=True,
            )
        state, pay = await _state_and_payment(job_id)
        assert state in {"CANCELED", "RUNNING"}, (state, pay)
        if state == "CANCELED":
            assert pay in {"pending", "refund_pending", "refunded"}, (state, pay)
        else:
            assert pay in {"pending", "escrowed"}, (state, pay)


async def test_cancel_on_terminal_job_is_idempotent() -> None:
    job_id = await _seed()
    async with get_session_context() as session:
        svc = MarketService(session)
        await svc.cancel_market_job(job_id)
        first = await svc.cancel_market_job(job_id)
        assert first["state"] == "CANCELED"
    state, pay = await _state_and_payment(job_id)
    assert state == "CANCELED"
