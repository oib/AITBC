"""SWEEPER-PAYFLIP-ORPHAN-1 (#1825): _expire_stale_jobs must not persist the
payment flip when the job CAS loses.

The payment CAS (escrowed -> refund_pending) and the job CAS
(QUEUED/RUNNING -> EXPIRED) share one savepoint. Before the fix, a lost job
CAS exited the savepoint normally — committing the payment flip while the
job stayed live, after which the refund pass's ``refund_pending`` OR-branch
could refund a running job's escrow.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from market_service.domain.market import MarketJob, MarketJobPayment
from market_service.services.market_job_sweeper import MarketJobSweeper
from market_service.services.market_service import MarketService
from market_service.storage import get_session_context


class StubRPC:
    async def release_escrow(self, job_id: str, body: dict | None = None):
        return {"success": True, "tx_hash": f"0xrelease_{job_id}"}

    async def refund_escrow(self, job_id: str, body: dict | None = None):
        return {"success": True, "tx_hash": f"0xrefund_{job_id}"}


async def _make_expired_queued_job(service: MarketService, tag: str) -> str:
    past = datetime.now(UTC) - timedelta(days=2)
    created = await service.create_market_job(
        {
            "service_type": "ipfs",
            "buyer_address": "0x" + "11" * 20,
            "provider_address": "0x" + "22" * 20,
            "expires_at": past.isoformat(),
            "payload": {"cid": f"Qm{tag}"},
            "payment": {"amount": "1.0", "status": "escrowed"},
        }
    )
    job_id = created["job_id"]
    # create_market_job ignores caller payment.status (#815) — escrow it and
    # keep updated_at old so lifecycle timestamps stay consistent.
    async with get_session_context() as session:
        job = await session.get(MarketJob, job_id)
        assert job is not None
        job.state = "QUEUED"
        payment = await session.get(MarketJobPayment, job.payment_id)
        assert payment is not None
        payment.status = "escrowed"
        payment.escrowed_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=1)
        payment.updated_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=1)
        job.updated_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=1)
        session.add_all([job, payment])
        await session.commit()
    return job_id


async def _job_and_payment(job_id: str) -> tuple[MarketJob, MarketJobPayment]:
    async with get_session_context() as session:
        job = await session.get(MarketJob, job_id)
        assert job is not None
        payment = await session.get(MarketJobPayment, job.payment_id)
        assert payment is not None
        return job, payment


def _sweeper() -> MarketJobSweeper:
    return MarketJobSweeper(
        rpc_client=StubRPC(),
        session_factory=lambda: get_session_context(),
        min_age_seconds=0,
    )


@pytest.mark.asyncio
async def test_lost_job_cas_rolls_back_payment_flip() -> None:
    """Job CAS loses (concurrent transition won): the escrowed ->
    refund_pending flip must roll back with the savepoint — the job stays
    QUEUED and its payment stays escrowed."""
    async with get_session_context() as session:
        service = MarketService(session)
        job_id = await _make_expired_queued_job(service, "payflip")

        sweeper = _sweeper()

        async def lose_job_cas(session_, job_id_, from_states, values):
            return False

        sweeper._cas_job_state = lose_job_cas  # type: ignore[method-assign]
        await sweeper._expire_stale_jobs(session, datetime.now(UTC).replace(tzinfo=None))
        await session.commit()

    job, payment = await _job_and_payment(job_id)
    assert job.state == "QUEUED"
    assert payment.status == "escrowed", "payment flip must not outlive a lost job CAS"


@pytest.mark.asyncio
async def test_won_job_cas_still_flips_payment() -> None:
    """Control: when the job CAS wins, the payment flip persists exactly as
    before — EXPIRED job + refund_pending payment."""
    async with get_session_context() as session:
        service = MarketService(session)
        job_id = await _make_expired_queued_job(service, "paywin")

        sweeper = _sweeper()
        await sweeper._expire_stale_jobs(session, datetime.now(UTC).replace(tzinfo=None))
        await session.commit()

    job, payment = await _job_and_payment(job_id)
    assert job.state == "EXPIRED"
    assert payment.status == "refund_pending"
    assert job.payment_status == "refund_pending"
