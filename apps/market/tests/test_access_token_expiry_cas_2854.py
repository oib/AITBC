"""#2854 AUDIT-MONEY-43: access-token lazy expiry must not regress a settle.

``get_market_job_access_token`` used to expire an overdue QUEUED/RUNNING job
with a plain ORM write + commit. A settle committing between the SELECT and
the flush was overwritten: RELEASED -> EXPIRED and payment released ->
refund_pending (provider paid AND buyer refunded). The expiry transition is
now a state-predicated CAS like every other lifecycle write.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from market_service.domain.market import MarketJob, MarketJobPayment
from market_service.services.market_service import MarketService
from market_service.storage import get_session_context

pytestmark = pytest.mark.asyncio

_BUYER = "0x" + "11" * 20
_PROVIDER = "0x" + "22" * 20


async def _seed_expired_job() -> tuple[str, str, str]:
    """Expired QUEUED job + escrowed payment + access credentials."""
    access_key = f"ak-2854-{datetime.now(UTC).timestamp()}"
    async with get_session_context() as session:
        svc = MarketService(session)
        created = await svc.create_market_job(
            {
                "service_type": "ipfs",
                "buyer_address": _BUYER,
                "provider_address": _PROVIDER,
                "expires_at": (datetime.now(UTC) - timedelta(hours=1)).isoformat(),
                "payload": {"cid": "QmExp", "access_key": access_key, "access_secret": "sec-2854"},
                "payment": {"amount": "1.0"},
            }
        )
        job_id = created["job_id"]
        job = await session.get(MarketJob, job_id)
        assert job is not None and job.payment_id
        payment = await session.get(MarketJobPayment, job.payment_id)
        assert payment is not None
        payment.status = "escrowed"
        payment.escrowed_at = datetime.now(UTC).replace(tzinfo=None)
        session.add(payment)
        await session.commit()
    return job_id, access_key, "sec-2854"


async def _job_and_payment(job_id: str) -> tuple[MarketJob, MarketJobPayment]:
    async with get_session_context() as session:
        job = await session.get(MarketJob, job_id)
        assert job is not None and job.payment_id
        payment = await session.get(MarketJobPayment, job.payment_id)
        assert payment is not None
        return job, payment


async def test_expired_token_fetch_expires_job_and_refunds_payment() -> None:
    """Guard: the intended expiry path still works — EXPIRED + refund_pending."""
    job_id, access_key, secret = await _seed_expired_job()
    async with get_session_context() as session:
        out = await MarketService(session).get_market_job_access_token(access_key, secret)
    assert out is None
    job, payment = await _job_and_payment(job_id)
    assert job.state == "EXPIRED"
    assert payment.status == "refund_pending"
    assert job.payment_status == "refund_pending"


async def test_expired_token_fetch_does_not_regress_concurrent_settle() -> None:
    """#2854: a settle (RELEASED + payment released) committing between the
    access-token SELECT and the expiry write must win — the lazy expiry is a
    CAS, so the loser is a no-op instead of a regression."""
    job_id, access_key, secret = await _seed_expired_job()

    async with get_session_context() as session:
        svc = MarketService(session)
        original_execute = session.execute
        injected = False

        async def execute_with_concurrent_settle(*args, **kwargs):  # type: ignore[no-untyped-def]
            nonlocal injected
            result = await original_execute(*args, **kwargs)
            if not injected:
                injected = True
                # The "other" transaction: settle commits RELEASED + released
                # right after this session's job SELECT materialized QUEUED.
                async with get_session_context() as other:
                    other_job = await other.get(MarketJob, job_id)
                    assert other_job is not None and other_job.payment_id
                    other_job.state = "RELEASED"
                    other_job.payment_status = "released"
                    other_payment = await other.get(MarketJobPayment, other_job.payment_id)
                    assert other_payment is not None
                    other_payment.status = "released"
                    other.add_all([other_job, other_payment])
                    await other.commit()
            return result

        session.execute = execute_with_concurrent_settle  # type: ignore[method-assign]
        out = await svc.get_market_job_access_token(access_key, secret)

    assert out is None  # expired access is denied either way
    job, payment = await _job_and_payment(job_id)
    assert job.state == "RELEASED"
    assert payment.status == "released"
    assert job.payment_status == "released"
