"""#2858 AUDIT-MONEY-47: caller-supplied settle txs must cover the floor.

``_require_confirmed_settle_tx`` verified the tx was THIS job's settlement
but never compared its on-chain ``value`` to the locked ``payment.amount`` —
a partial settle flipped the job terminal while the remainder stayed locked
in escrow. Release floors at the attested billed amount when provider
billing priced the job, else the full lock; refund always floors at the
full lock.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from market_service.domain.market import MarketJob, MarketJobPayment
from market_service.services.market_service import MarketService
from market_service.storage import get_session_context

pytestmark = pytest.mark.asyncio

# aitbc.utils.units: 1 AIT = 36_000_000 compute units.
UNITS_PER_AIT = 36_000_000
LOCK_AIT = Decimal("10")


async def _seed(state: str, payment_status: str = "escrowed", tag: str = "") -> str:
    job_id = f"job-2858-{state.lower()}-{tag}-{payment_status}"
    async with get_session_context() as session:
        pay = MarketJobPayment(job_id=job_id, amount=LOCK_AIT, status=payment_status)
        job = MarketJob(
            id=job_id,
            state=state,
            payment_id=pay.id,
            payment_status=payment_status,
        )
        session.add_all([pay, job])
        await session.commit()
    return job_id


def _settle_tx(job_id: str, tx_type: str, ait: Decimal | int) -> dict:
    units = int(Decimal(str(ait)) * UNITS_PER_AIT)
    return {
        "status": "confirmed",
        "type": tx_type,
        "payload": {"job_id": job_id},
        "value": units,
    }


async def _fields(job_id: str):
    async with get_session_context() as session:
        job = await session.get(MarketJob, job_id)
        payment = await session.get(MarketJobPayment, job.payment_id) if job and job.payment_id else None
        return job, payment


async def test_partial_refund_tx_refused_and_payment_stays_escrowed() -> None:
    """5-of-10 AIT refund tx: refused — the job must not go terminal with
    half the escrow still locked."""
    job_id = await _seed("FAILED", tag="partial")
    async with get_session_context() as session:
        svc = MarketService(session)
        svc._rpc_client.get_transaction = AsyncMock(return_value=_settle_tx(job_id, "ESCROW_REFUND", 5))
        svc._rpc_client.refund_escrow = AsyncMock()
        with pytest.raises(ValueError, match="(?i)below the"):
            await svc.refund_market_job_payment(job_id, refund_data={"tx_hash": "0xpartial"})
    job, payment = await _fields(job_id)
    assert job.state == "FAILED"
    assert payment.status == "escrowed"


async def test_full_refund_tx_accepted() -> None:
    job_id = await _seed("FAILED", tag="full")
    async with get_session_context() as session:
        svc = MarketService(session)
        svc._rpc_client.get_transaction = AsyncMock(return_value=_settle_tx(job_id, "ESCROW_REFUND", LOCK_AIT))
        result = await svc.refund_market_job_payment(job_id, refund_data={"tx_hash": "0xfull"})
    assert result["state"] == "REFUNDED"
    _job, payment = await _fields(job_id)
    assert payment.status == "refunded"
    assert payment.refunded_amount == LOCK_AIT


async def test_partial_release_tx_refused_without_billing_attestation() -> None:
    """No attested billing -> the release floor is the full lock; a partial
    release tx strands the remainder."""
    job_id = await _seed("COMPLETED", tag="partial")
    async with get_session_context() as session:
        svc = MarketService(session)
        svc._rpc_client.get_transaction = AsyncMock(return_value=_settle_tx(job_id, "ESCROW_RELEASE", 5))
        svc._rpc_client.release_escrow = AsyncMock()
        with pytest.raises(ValueError, match="(?i)below the"):
            await svc.release_market_job_payment(job_id, release_data={"tx_hash": "0xpartial"})
    job, payment = await _fields(job_id)
    assert job.state == "COMPLETED"
    assert payment.status == "escrowed"


async def test_full_release_tx_accepted() -> None:
    job_id = await _seed("COMPLETED", tag="full")
    async with get_session_context() as session:
        svc = MarketService(session)
        svc._rpc_client.get_transaction = AsyncMock(return_value=_settle_tx(job_id, "ESCROW_RELEASE", LOCK_AIT))
        result = await svc.release_market_job_payment(job_id, release_data={"tx_hash": "0xfull"})
    assert result["state"] == "RELEASED"
    _job, payment = await _fields(job_id)
    assert payment.status == "released"
    assert payment.released_amount == LOCK_AIT
