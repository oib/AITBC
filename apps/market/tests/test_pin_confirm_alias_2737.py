"""#2737 MARKET-HOST-DUAL-PAYMENT-1: pin-confirm honors payload.escrow_job_id.

``aitbc market host`` on the coordinator rail locks the on-chain escrow
under the *coordinator* job id, then registers a ``sw_job_*`` market job.
The market job claims that escrow via ``payload["escrow_job_id"]`` — the
same alias mechanism ``ai submit`` tokens use (#2322/#2325/#2326). Before
the fix ``_require_locked_escrow`` verified ``/rpc/escrow/{job.id}`` only,
so pin-confirm 404'd ("No on-chain escrow found") and the market payment
row stayed ``pending`` forever next to the real escrowed coordinator
payment.

Pinned here:

* an alias claim whose lock tx names this market job flips pending ->
  escrowed on the coordinator-keyed escrow;
* an alias claim whose lock tx names a *different* market job is refused
  and the payment stays pending;
* an alias key claimed by another live market job is refused.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from market_service.domain.market import MarketJob, MarketJobPayment, SoftwareService
from market_service.services.market_service import MarketService
from market_service.storage import get_session_context

pytestmark = pytest.mark.asyncio


_BUYER = "0x" + "11" * 20
_PROVIDER = "0x" + "22" * 20


class _AliasEscrowStub:
    """Locked escrow under the coordinator key + lock-tx lookup."""

    def __init__(self, escrow_key: str, market_job_id: str) -> None:
        self.escrow_key = escrow_key
        self.market_job_id = market_job_id
        self.verified: list[str] = []

    async def verify_escrow(self, job_id: str):
        self.verified.append(job_id)
        if job_id != self.escrow_key:
            return None
        return {
            "job_id": job_id,
            "state": "funded",
            "amount": "1.0",
            "buyer": _BUYER,
            "provider": _PROVIDER,
            "lock_tx_hash": "0xlock2737",
        }

    async def get_transaction(self, tx_hash: str, chain_id: str | None = None):
        return {"payload": {"market_job_id": self.market_job_id}}


async def _seed_alias(escrow_key: str) -> str:
    async with get_session_context() as session:
        svc = MarketService(session)
        svc.session.add(SoftwareService(service_type="ipfs", offer_id=f"offer-{escrow_key}"))
        created = await svc.create_market_job(
            {
                "service_type": "ipfs",
                "buyer_address": _BUYER,
                "provider_address": _PROVIDER,
                "offer_id": f"offer-{escrow_key}",
                "payload": {"cid": "QmAlias", "escrow_job_id": escrow_key},
                "payment": {"amount": "1.0"},
            }
        )
    return created["job_id"]


async def _payment_status(job_id: str) -> str | None:
    async with get_session_context() as session:
        job = await session.get(MarketJob, job_id)
        assert job is not None and job.payment_id
        payment = await session.get(MarketJobPayment, job.payment_id)
        return payment.status if payment else None


async def test_alias_pin_confirm_flips_pending_to_escrowed() -> None:
    escrow_key = "coord-escrow-2737-a"
    job_id = await _seed_alias(escrow_key)
    async with get_session_context() as session:
        svc = MarketService(session)
        stub = _AliasEscrowStub(escrow_key, market_job_id=job_id)
        svc._rpc_client = stub  # type: ignore[assignment]
        out = await svc.confirm_market_job_pin(job_id, size=42)

    assert out["state"] == "QUEUED"  # unsigned report: informational only
    assert stub.verified == [escrow_key]  # looked up the alias, not job.id
    assert await _payment_status(job_id) == "escrowed"


async def test_alias_lock_naming_other_job_is_refused() -> None:
    escrow_key = "coord-escrow-2737-b"
    job_id = await _seed_alias(escrow_key)
    async with get_session_context() as session:
        svc = MarketService(session)
        svc._rpc_client = _AliasEscrowStub(escrow_key, market_job_id="sw_job_other")  # type: ignore[assignment]
        with pytest.raises(ValueError, match="does not name market job"):
            await svc.confirm_market_job_pin(job_id, size=42)
    assert await _payment_status(job_id) == "pending"


async def test_alias_key_claimed_by_another_job_is_refused() -> None:
    escrow_key = "coord-escrow-2737-c"
    job_id = await _seed_alias(escrow_key)
    # An earlier-created live job already claims the same escrow key — the
    # uniqueness rule gives the key to the earliest claimant (#2325).
    now = datetime.now(UTC).replace(tzinfo=None)
    async with get_session_context() as session:
        session.add(
            MarketJob(
                id="sw_job_squatter",
                service_type="ipfs",
                buyer_address=_BUYER,
                provider_address=_PROVIDER,
                offer_id=f"offer-{escrow_key}",
                state="QUEUED",
                payload={"escrow_job_id": escrow_key},
                payment_amount="1.0",
                requested_at=now - timedelta(days=1),
                created_at=now - timedelta(days=1),
                updated_at=now - timedelta(days=1),
            )
        )
        await session.commit()

    async with get_session_context() as session:
        svc = MarketService(session)
        svc._rpc_client = _AliasEscrowStub(escrow_key, market_job_id=job_id)  # type: ignore[assignment]
        with pytest.raises(ValueError, match="claimed by another market job"):
            await svc.confirm_market_job_pin(job_id, size=42)
    assert await _payment_status(job_id) == "pending"
