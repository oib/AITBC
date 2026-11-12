"""MARKET-SETTLE-HARDEN-1 (#1835): dispute freeze + release/refund CAS +
dispute gating, from the #1828 adversarial audit.

* F1: an open dispute freezes release AND refund on the direct API paths,
  not just the sweeper.
* F2: release/refund terminal writes are CAS — a competing commit during
  the RPC window wins; the stale ORM write must not clobber it.
* F7: dispute_market_job requires a live escrowed payment and caps re-arms.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from market_service.domain.market import MarketJob, MarketJobPayment
from market_service.services.market_service import MarketService
from market_service.storage import get_session_context

pytestmark = pytest.mark.asyncio


class RecordingRPC:
    def __init__(self, during=None):
        self.calls: list[str] = []
        self._during = during

    async def release_escrow(self, job_id: str, body: dict | None = None):
        self.calls.append(("release", job_id))
        if self._during:
            await self._during()
        return {"success": True, "tx_hash": f"0xrel_{job_id}"}

    async def refund_escrow(self, job_id: str, body: dict | None = None):
        self.calls.append(("refund", job_id))
        if self._during:
            await self._during()
        return {"success": True, "tx_hash": f"0xref_{job_id}"}


async def _seed(
    *,
    state: str = "RUNNING",
    payment_status: str = "escrowed",
    with_payment: bool = True,
    disputed: bool = False,
) -> str:
    async with get_session_context() as session:
        job_id = f"job_1835_{uuid4().hex[:12]}"
        payment_id = None
        if with_payment:
            payment = MarketJobPayment(id=f"pay_{job_id}", job_id=job_id, amount=Decimal("1.0"), status=payment_status)
            session.add(payment)
            payment_id = payment.id
        now = datetime.now(UTC).replace(tzinfo=None)
        session.add(
            MarketJob(
                id=job_id,
                buyer_address="0x" + "11" * 20,
                provider_address="0x" + "22" * 20,
                service_type="ipfs",
                state=state,
                payload={"provider_confirmed": True},
                payment_id=payment_id,
                payment_status=payment_status if with_payment else None,
                disputed_at=now if disputed else None,
                dispute_cleared_at=None,
            )
        )
        await session.commit()
        return job_id


async def _fields(job_id: str):
    async with get_session_context() as session:
        job = await session.get(MarketJob, job_id)
        payment = await session.get(MarketJobPayment, job.payment_id) if job and job.payment_id else None
        return job, payment


async def _competing_cancel(job_id: str) -> None:
    """A second session commits cancel_market_job's writes mid-RPC-window."""
    async with get_session_context() as session:
        job = await session.get(MarketJob, job_id)
        payment = await session.get(MarketJobPayment, job.payment_id)
        now = datetime.now(UTC).replace(tzinfo=None)
        payment.status = "refund_pending"
        payment.updated_at = now
        job.state = "CANCELED"
        job.payment_status = "refund_pending"
        job.updated_at = now
        session.add_all([job, payment])
        await session.commit()


async def _competing_dispute(job_id: str) -> None:
    async with get_session_context() as session:
        job = await session.get(MarketJob, job_id)
        job.disputed_at = datetime.now(UTC).replace(tzinfo=None)
        job.dispute_reason = "mid-flight dispute"
        job.dispute_cleared_at = None
        job.updated_at = job.disputed_at
        session.add(job)
        await session.commit()


# --- F1: open dispute freezes direct release/refund -------------------------


async def test_open_dispute_blocks_release() -> None:
    job_id = await _seed(state="RUNNING", disputed=True)
    async with get_session_context() as session:
        service = MarketService(session)
        rpc = RecordingRPC()
        service._rpc_client = rpc  # type: ignore[assignment]
        with pytest.raises(ValueError, match="dispute"):
            await service.release_market_job_payment(job_id)
    assert rpc.calls == []
    job, payment = await _fields(job_id)
    assert job.state == "RUNNING"
    assert payment.status == "escrowed"


async def test_open_dispute_blocks_refund() -> None:
    job_id = await _seed(state="FAILED", disputed=True)
    async with get_session_context() as session:
        service = MarketService(session)
        rpc = RecordingRPC()
        service._rpc_client = rpc  # type: ignore[assignment]
        with pytest.raises(ValueError, match="dispute"):
            await service.refund_market_job_payment(job_id)
    assert rpc.calls == []
    job, payment = await _fields(job_id)
    assert job.state == "FAILED"
    assert payment.status == "escrowed"


async def test_cleared_dispute_does_not_block() -> None:
    """A resolved dispute (dispute_cleared_at set) must not freeze forever."""
    job_id = await _seed(state="FAILED")
    async with get_session_context() as session:
        job = await session.get(MarketJob, job_id)
        now = datetime.now(UTC).replace(tzinfo=None)
        job.disputed_at = now
        job.dispute_cleared_at = now
        session.add(job)
        await session.commit()

    async with get_session_context() as session:
        service = MarketService(session)
        service._rpc_client = RecordingRPC()  # type: ignore[assignment]
        result = await service.refund_market_job_payment(job_id)
    assert result["state"] == "REFUNDED"


# --- F2: terminal writes are CAS --------------------------------------------


async def test_release_loses_to_concurrent_cancel() -> None:
    """cancel commits during release's RPC window: the CAS must lose and the
    buyer's cancel must not be clobbered to RELEASED/released."""
    job_id = await _seed(state="RUNNING")
    async with get_session_context() as session:
        service = MarketService(session)
        service._rpc_client = RecordingRPC(during=lambda: _competing_cancel(job_id))  # type: ignore[assignment]
        result = await service.release_market_job_payment(job_id)
    assert result["state"] == "CANCELED"
    job, payment = await _fields(job_id)
    assert job.state == "CANCELED"
    assert payment.status == "refund_pending"


async def test_refund_loses_to_concurrent_dispute() -> None:
    """A dispute landing during refund's RPC window must win the CAS — the
    payment flip rolls back and the escrow stays frozen, not refunded."""
    job_id = await _seed(state="FAILED")
    async with get_session_context() as session:
        service = MarketService(session)
        service._rpc_client = RecordingRPC(during=lambda: _competing_dispute(job_id))  # type: ignore[assignment]
        result = await service.refund_market_job_payment(job_id)
    assert result["state"] == "FAILED"
    job, payment = await _fields(job_id)
    assert job.state == "FAILED"
    assert job.disputed_at is not None
    assert payment.status == "escrowed"


async def test_release_still_succeeds_unchallenged() -> None:
    job_id = await _seed(state="COMPLETED")
    async with get_session_context() as session:
        service = MarketService(session)
        service._rpc_client = RecordingRPC()  # type: ignore[assignment]
        result = await service.release_market_job_payment(job_id)
    assert result["state"] == "RELEASED"
    job, payment = await _fields(job_id)
    assert job.state == "RELEASED"
    assert payment.status == "released"


# --- F7: dispute gating -----------------------------------------------------


async def test_dispute_requires_escrowed_payment() -> None:
    job_id = await _seed(state="RUNNING", with_payment=False)
    async with get_session_context() as session:
        service = MarketService(session)
        with pytest.raises(ValueError, match="no escrowed payment"):
            await service.dispute_market_job(job_id)


async def test_dispute_rejects_settled_payment() -> None:
    job_id = await _seed(state="RELEASED", payment_status="released")
    async with get_session_context() as session:
        service = MarketService(session)
        with pytest.raises(ValueError, match="no escrowed payment"):
            await service.dispute_market_job(job_id)


async def test_dispute_rearm_is_capped() -> None:
    """dispute -> resolve cycles are bounded: the 4th open exceeds the cap."""
    job_id = await _seed(state="RUNNING")
    async with get_session_context() as session:
        service = MarketService(session)
        for _ in range(3):
            await service.dispute_market_job(job_id, reason="cycle")
            await service.resolve_market_job_dispute(job_id)
        with pytest.raises(ValueError, match="dispute limit"):
            await service.dispute_market_job(job_id, reason="one too many")
    job, _ = await _fields(job_id)
    assert job.dispute_cleared_at is not None
