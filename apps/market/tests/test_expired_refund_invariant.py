"""Invariant tests for expired-job escrow settlement (#v11 item 6).

Proves the sweeper + lazy-expiry paths can never pay the same escrow twice,
and never pay the wrong party:

* an unfinished (QUEUED/RUNNING) job past ``expires_at`` refunds the buyer;
* a COMPLETED job past ``expires_at`` keeps its terminal state — the lazy
  access-token expiry must not regress it to EXPIRED and refund work that
  was finished (regression fixed in the v11 audit);
* across one ``sweep_once`` no escrow key is both released and refunded.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from market_service.domain.market import MarketJob, MarketJobPayment
from market_service.services.market_job_sweeper import MarketJobSweeper
from market_service.services.market_service import MarketService
from market_service.storage import get_session_context


class StubRPC:
    def __init__(self) -> None:
        self.released: list[str] = []
        self.refunded: list[str] = []

    async def release_escrow(self, job_id: str, body: dict | None = None):
        self.released.append(job_id)
        return {"success": True, "tx_hash": f"0xrelease_{job_id}"}

    async def refund_escrow(self, job_id: str, body: dict | None = None):
        self.refunded.append(job_id)
        return {"success": True, "tx_hash": f"0xrefund_{job_id}"}


async def _make_job(
    service: MarketService,
    *,
    tag: str,
    expires_at: datetime,
    access: bool = False,
) -> str:
    payload: dict = {"cid": f"Qm{tag}"}
    if access:
        payload["access_key"] = f"ak_{tag}"
        payload["access_secret"] = f"sec_{tag}"
    created = await service.create_market_job(
        {
            "service_type": "ipfs",
            "buyer_address": "0x" + "11" * 20,
            "provider_address": "0x" + "22" * 20,
            "expires_at": expires_at.isoformat(),
            "payload": payload,
            "payment": {"amount": "1.0", "status": "escrowed"},
        }
    )
    return created["job_id"]


async def _set_lifecycle(
    job_id: str,
    *,
    state: str,
    payment_status: str = "escrowed",
    updated_at: datetime | None = None,
    payload_update: dict | None = None,
) -> None:
    async with get_session_context() as session:
        job = await session.get(MarketJob, job_id)
        assert job is not None
        job.state = state
        job.payment_status = payment_status
        if payload_update:
            job.payload = {**(job.payload or {}), **payload_update}
        if updated_at is not None:
            job.updated_at = updated_at
        payment = await session.get(MarketJobPayment, job.payment_id)
        assert payment is not None
        payment.status = payment_status
        payment.escrowed_at = datetime.now(UTC).replace(tzinfo=None)
        payment.updated_at = datetime.now(UTC).replace(tzinfo=None)
        session.add_all([job, payment])
        await session.commit()


async def _job_and_payment(job_id: str) -> tuple[MarketJob, MarketJobPayment]:
    async with get_session_context() as session:
        job = await session.get(MarketJob, job_id)
        assert job is not None
        payment = await session.get(MarketJobPayment, job.payment_id)
        assert payment is not None
        return job, payment


@pytest.mark.asyncio
async def test_lazy_expiry_unfinished_job_refunds_buyer() -> None:
    """QUEUED job past expires_at: access denied, escrowed -> refund_pending,
    sweeper refunds (never releases) the buyer."""
    async with get_session_context() as session:
        service = MarketService(session)
        past = datetime.now(UTC) - timedelta(days=2)
        job_id = await _make_job(service, tag="lazyq", expires_at=past, access=True)
        # create_market_job ignores caller payment.status (#815) — escrow it.
        # updated_at stays old so the refund pass's min_age gate admits it.
        await _set_lifecycle(job_id, state="QUEUED", updated_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=1))

        assert await service.get_market_job_access_token("ak_lazyq", "sec_lazyq") is None

        job, payment = await _job_and_payment(job_id)
        assert job.state == "EXPIRED"
        assert payment.status == "refund_pending"

        rpc = StubRPC()
        sw = MarketJobSweeper(rpc_client=rpc, session_factory=lambda: get_session_context(), min_age_seconds=0)
        counts = await sw.sweep_once()
        assert job_id in rpc.refunded
        assert job_id not in rpc.released
        job, payment = await _job_and_payment(job_id)
        assert job.state == "REFUNDED"
        assert payment.status == "refunded"
        assert counts["released"] == 0


@pytest.mark.asyncio
async def test_lazy_expiry_does_not_regress_completed_job() -> None:
    """COMPLETED job past expires_at: access denied but state/payment
    untouched — the sweeper must release to the provider, not refund."""
    async with get_session_context() as session:
        service = MarketService(session)
        past = datetime.now(UTC) - timedelta(days=40)
        job_id = await _make_job(service, tag="lazyc", expires_at=past, access=True)
        await _set_lifecycle(job_id, state="COMPLETED")

        assert await service.get_market_job_access_token("ak_lazyc", "sec_lazyc") is None

        job, payment = await _job_and_payment(job_id)
        assert job.state == "COMPLETED", "lazy expiry must not regress a completed job"
        assert payment.status == "escrowed"

        rpc = StubRPC()
        sw = MarketJobSweeper(rpc_client=rpc, session_factory=lambda: get_session_context(), min_age_seconds=0)
        await sw.sweep_once()
        assert job_id in rpc.released
        assert job_id not in rpc.refunded
        job, payment = await _job_and_payment(job_id)
        assert job.state == "RELEASED"
        assert payment.status == "released"


@pytest.mark.asyncio
async def test_sweep_settles_each_escrow_exactly_once() -> None:
    """Mixed terminal states in one sweep: no escrow key is both released
    and refunded, and every escrowed payment reaches exactly one verdict."""
    async with get_session_context() as session:
        service = MarketService(session)
        past = datetime.now(UTC) - timedelta(days=2)
        old = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=1)

        ids = {
            "completed": await _make_job(service, tag="invrel", expires_at=past),
            "expired": await _make_job(service, tag="invexp", expires_at=past),
            "failed": await _make_job(service, tag="invfail", expires_at=past),
            "canceled": await _make_job(service, tag="invcxl", expires_at=past),
        }
        await _set_lifecycle(ids["completed"], state="COMPLETED", updated_at=old)
        await _set_lifecycle(ids["expired"], state="EXPIRED", updated_at=old)
        await _set_lifecycle(ids["failed"], state="FAILED", updated_at=old)
        await _set_lifecycle(ids["canceled"], state="CANCELED", updated_at=old)

        rpc = StubRPC()
        sw = MarketJobSweeper(rpc_client=rpc, session_factory=lambda: get_session_context(), min_age_seconds=0)
        counts = await sw.sweep_once()

        both = set(rpc.released) & set(rpc.refunded)
        assert not both, f"escrow settled twice: {both}"
        assert set(rpc.released) == {ids["completed"]}
        assert set(rpc.refunded) == {ids["expired"], ids["failed"], ids["canceled"]}
        assert counts["released"] == 1
        assert counts["refunded"] == 3

        for job_id in ids.values():
            job, payment = await _job_and_payment(job_id)
            assert payment.status in {"released", "refunded"}
            assert job.state == payment.status.upper()


@pytest.mark.asyncio
async def test_direct_release_rejects_unfinished_and_expired_states() -> None:
    """#v11 item 10: the release endpoint must not pay the provider for work
    that was never delivered. QUEUED and EXPIRED escrowed jobs are refused
    before any RPC; RUNNING (post pin-confirm) and COMPLETED still release.
    """
    async with get_session_context() as session:
        service = MarketService(session)
        past = datetime.now(UTC) - timedelta(days=2)

        queued = await _make_job(service, tag="relq", expires_at=past)
        expired = await _make_job(service, tag="rele", expires_at=past)
        running = await _make_job(service, tag="relr", expires_at=past)
        running_legacy = await _make_job(service, tag="rell", expires_at=past)
        completed = await _make_job(service, tag="relc", expires_at=past)
        await _set_lifecycle(queued, state="QUEUED")
        # EXPIRED with payment still escrowed is the release-vs-refund race
        # case: the state guard must fire before the payment-status one.
        await _set_lifecycle(expired, state="EXPIRED")
        # #1922: RUNNING is delivery evidence — post-fix it is only minted by
        # the signed provider pin-confirm, which records provider_confirmed
        # in the payload. running_legacy models a pre-fix row that reached
        # RUNNING via the unsigned path: it must NOT release.
        await _set_lifecycle(running, state="RUNNING", payload_update={"provider_confirmed": True})
        await _set_lifecycle(running_legacy, state="RUNNING")
        await _set_lifecycle(completed, state="COMPLETED")

        service._rpc_client = StubRPC()  # type: ignore[assignment]

        for job_id in (queued, expired, running_legacy):
            with pytest.raises(ValueError):
                await service.release_market_job_payment(job_id)
        assert service._rpc_client.released == []

        for job_id in (running, completed):
            result = await service.release_market_job_payment(job_id)
            assert result["state"] == "RELEASED"
        assert set(service._rpc_client.released) == {running, completed}
