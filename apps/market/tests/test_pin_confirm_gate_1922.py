"""#1922 MARKET-PIN-CONFIRM-GATE-1: unsigned pin-confirm is informational.

Before the fix ``confirm_market_job_pin`` set ``payload.pinned`` and CASed
QUEUED -> RUNNING for *any* caller holding the user-distributed
``MARKET_API_KEY`` — and RUNNING is the release gate's delivery proof, so a
key holder could pin-confirm, then release, and get paid without the
provider ever attesting a pin (pay-without-delivery for IPFS rentals).

Pinned here:

* unsigned ``size``/``pin_tx_hash`` reports record payload fields and may
  flip a pending payment to ``escrowed`` on verified on-chain proof, but
  never set ``pinned``/``provider_confirmed`` and never move the job to
  RUNNING;
* ``provider_confirmed=True`` (the route only passes it after the provider
  wallet signature + cid/size binding check) is the sole path that mints
  RUNNING and release works from it;
* release refuses a RUNNING job whose payload lacks ``provider_confirmed``
  — the fail-closed treatment for rows that reached RUNNING via the
  unsigned path before this gate existed.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from market_service.domain.market import MarketJob, MarketJobPayment, SoftwareService
from market_service.services.market_service import MarketService
from market_service.storage import get_session_context

pytestmark = pytest.mark.asyncio


class _EscrowStub:
    """Locked on-chain escrow proof for the pending->escrowed gate."""

    async def verify_escrow(self, job_id: str):
        return {
            "job_id": job_id,
            "state": "funded",
            "amount": "1.0",
            "buyer": "0x" + "11" * 20,
            "provider": "0x" + "22" * 20,
        }


class _ReleaseStub:
    def __init__(self) -> None:
        self.released: list[str] = []

    async def release_escrow(self, job_id: str, body: dict | None = None):
        self.released.append(job_id)
        return {"success": True, "tx_hash": f"0xrelease_{job_id}"}


async def _seed(*, payment_status: str = "pending") -> tuple[str, MarketService]:
    async with get_session_context() as session:
        svc = MarketService(session)
        svc.session.add(SoftwareService(service_type="ipfs", offer_id="offer-1922"))
        svc._rpc_client = _EscrowStub()  # type: ignore[assignment]
        created = await svc.create_market_job(
            {
                "service_type": "ipfs",
                "buyer_address": "0x" + "11" * 20,
                "provider_address": "0x" + "22" * 20,
                "offer_id": "offer-1922",
                "payload": {"cid": "QmPinGate", "size": 10},
                "payment": {"amount": "1.0", "status": payment_status},
            }
        )
        job_id = created["job_id"]
        if payment_status == "escrowed":
            # create_market_job ignores caller payment.status (#815) — drive
            # the escrowed lifecycle the way settlement would.
            job = await svc.session.get(MarketJob, job_id)
            assert job is not None
            job.state = "QUEUED"
            job.payment_status = "escrowed"
            payment = await svc.session.get(MarketJobPayment, job.payment_id)
            assert payment is not None
            payment.status = "escrowed"
            payment.escrowed_at = datetime.now(UTC).replace(tzinfo=None)
            payment.updated_at = datetime.now(UTC).replace(tzinfo=None)
            svc.session.add_all([job, payment])
            await svc.session.commit()
    return job_id, svc


async def _fetch(job_id: str) -> dict:
    async with get_session_context() as session:
        return await MarketService(session).get_market_job(job_id)


async def test_unsigned_pin_confirm_is_informational_only() -> None:
    """The buyer host-flow report records size but mints no delivery proof."""
    job_id, _ = await _seed()
    async with get_session_context() as session:
        svc = MarketService(session)
        svc._rpc_client = _EscrowStub()  # type: ignore[assignment]
        out = await svc.confirm_market_job_pin(job_id, size=777, pin_tx_hash="0xpin")

    assert out["state"] == "QUEUED"
    fetched = await _fetch(job_id)
    assert fetched["state"] == "QUEUED"
    assert fetched["payment"]["status"] == "escrowed"  # on-chain proof flip still runs
    assert fetched["payload"]["size"] == 777
    assert fetched["payload"]["pin_tx_hash"] == "0xpin"
    assert fetched["payload"].get("pinned") is not True
    assert fetched["payload"].get("provider_confirmed") is not True

    # And the unsigned report cannot authorize release: QUEUED is refused.
    async with get_session_context() as session:
        svc = MarketService(session)
        svc._rpc_client = _ReleaseStub()  # type: ignore[assignment]
        with pytest.raises(ValueError, match="only RUNNING/COMPLETED"):
            await svc.release_market_job_payment(job_id)
        assert svc._rpc_client.released == []


async def test_signed_provider_confirm_still_reaches_running_and_releases() -> None:
    """provider_confirmed (route-gated by the provider signature + binding)
    remains the delivery proof: RUNNING, pinned flags, release pays out."""
    job_id, _ = await _seed(payment_status="escrowed")
    async with get_session_context() as session:
        svc = MarketService(session)
        out = await svc.confirm_market_job_pin(job_id, size=777, provider_confirmed=True)
    assert out["state"] == "RUNNING"
    fetched = await _fetch(job_id)
    assert fetched["payload"]["pinned"] is True
    assert fetched["payload"]["provider_confirmed"] is True

    async with get_session_context() as session:
        svc = MarketService(session)
        svc._rpc_client = _ReleaseStub()  # type: ignore[assignment]
        released = await svc.release_market_job_payment(job_id)
        assert released["state"] == "RELEASED"
        assert svc._rpc_client.released == [job_id]


async def test_release_refuses_running_without_provider_attestation() -> None:
    """Fail closed on pre-fix rows: RUNNING minted by the unsigned path carries
    no ``provider_confirmed`` and must not release."""
    job_id, _ = await _seed(payment_status="escrowed")
    async with get_session_context() as session:
        svc = MarketService(session)
        # Simulate the legacy write: RUNNING + pinned flag but no attestation.
        job = await svc.session.get(MarketJob, job_id)
        assert job is not None
        job.state = "RUNNING"
        job.payload = {**(job.payload or {}), "pinned": True, "size": 5}
        svc.session.add(job)
        await svc.session.commit()

        svc._rpc_client = _ReleaseStub()  # type: ignore[assignment]
        with pytest.raises(ValueError, match="pin attestation"):
            await svc.release_market_job_payment(job_id)
        assert svc._rpc_client.released == []


async def test_unsigned_report_does_not_clear_existing_attestation() -> None:
    """A later buyer size report on an attested RUNNING job updates the
    reported size but leaves the delivery evidence intact."""
    job_id, _ = await _seed(payment_status="escrowed")
    async with get_session_context() as session:
        svc = MarketService(session)
        await svc.confirm_market_job_pin(job_id, size=100, provider_confirmed=True)
    async with get_session_context() as session:
        svc = MarketService(session)
        out = await svc.confirm_market_job_pin(job_id, size=200)
    assert out["state"] == "RUNNING"
    fetched = await _fetch(job_id)
    assert fetched["payload"]["size"] == 200
    assert fetched["payload"]["provider_confirmed"] is True
    assert fetched["payload"]["pinned"] is True
