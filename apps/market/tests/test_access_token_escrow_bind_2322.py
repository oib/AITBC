"""#2322 MARKET-TOKEN-ESCROW-BIND-1: shop access tokens require locked escrow.

Before the fix ``get_market_job_access_token`` authorized on
access_key + secret + QUEUED/RUNNING + TTL only — ``payment.status ==
"pending"`` still passed, and ``POST /v1/market/jobs`` is user-tier, so any
market-key holder could mint shop tokens (whisper/ffmpeg/ollama gated
calls) with no on-chain escrow at all.

Pinned here:

* ``pending`` payment + no/absent/non-locked/mismatched escrow -> denied;
* ``pending`` payment + locked on-chain escrow matching amount and parties
  -> allowed (the ``aitbc market run`` / ``ai submit`` flows, whose DB row
  stays ``pending`` because nothing flips it — the escrow is verified
  live);
* ``payment.status == "escrowed"`` (only ever written after the
  pin-confirm on-chain proof) -> allowed without another RPC;
* ``released``/``refunded``-class terminal payments -> denied;
* ``payload["escrow_job_id"]`` binds the escrow lookup when it differs
  from the market job id (the ai-submit transcribe token record).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from market_service.domain.market import MarketJob, MarketJobPayment
from market_service.services.market_service import MarketService
from market_service.storage import get_session_context

pytestmark = pytest.mark.asyncio

BUYER = "0x" + "11" * 20
PROVIDER = "0x" + "22" * 20


class _EscrowStub:
    """verify_escrow stub keyed by escrow/job id."""

    def __init__(self, escrows: dict[str, dict] | None = None) -> None:
        self.escrows = escrows or {}
        self.calls: list[str] = []

    async def verify_escrow(self, job_id: str):
        self.calls.append(job_id)
        return self.escrows.get(job_id)


def _locked_escrow(*, amount: str = "1.0", state: str = "locked", buyer: str = BUYER, provider: str = PROVIDER) -> dict:
    return {"state": state, "amount": amount, "buyer": buyer, "provider": provider}


async def _seed_access_job(
    *,
    tag: str,
    payment_status: str = "pending",
    amount: str = "1.0",
    escrow_job_id: str | None = None,
    expires_at: datetime | None = None,
) -> tuple[str, str, str]:
    """QUEUED market job + access creds + payment in ``payment_status``."""
    async with get_session_context() as session:
        svc = MarketService(session)
        payload: dict = {"cid": "QmTest", "access_key": f"ak_{tag}", "access_secret": f"sec_{tag}"}
        if escrow_job_id:
            payload["escrow_job_id"] = escrow_job_id
        created = await svc.create_market_job(
            {
                "service_type": "whisper",
                "buyer_address": BUYER,
                "provider_address": PROVIDER,
                "expires_at": (expires_at or (datetime.now(UTC) + timedelta(days=7))).isoformat(),
                "payload": payload,
                "payment": {"amount": amount},
            }
        )
        job_id = created["job_id"]
        if payment_status != "pending":
            # create_market_job always writes pending (#815) — drive the
            # lifecycle the way settlement would.
            job = await session.get(MarketJob, job_id)
            assert job is not None
            payment = await session.get(MarketJobPayment, job.payment_id)
            assert payment is not None
            payment.status = payment_status
            payment.updated_at = datetime.now(UTC).replace(tzinfo=None)
            session.add(payment)
            await session.commit()
    return job_id, f"ak_{tag}", f"sec_{tag}"


async def _verify(ak: str, secret: str, rpc: _EscrowStub) -> dict | None:
    async with get_session_context() as session:
        svc = MarketService(session)
        svc._rpc_client = rpc  # type: ignore[assignment]
        return await svc.get_market_job_access_token(ak, secret)


async def test_pending_payment_without_escrow_is_denied() -> None:
    """The defect: a registered job whose escrow was never locked."""
    job_id, ak, secret = await _seed_access_job(tag="noesc")
    rpc = _EscrowStub({})
    assert await _verify(ak, secret, rpc) is None
    # The lookup is keyed by the market job id when no binding is given.
    assert rpc.calls == [job_id]


async def test_pending_payment_with_locked_escrow_is_allowed() -> None:
    """aitbc market run shape: payment stays pending, escrow locked on-chain."""
    job_id, ak, secret = await _seed_access_job(tag="locked")
    rpc = _EscrowStub({job_id: _locked_escrow()})
    tok = await _verify(ak, secret, rpc)
    assert tok is not None
    assert tok["job_id"] == job_id


async def test_escrowed_payment_passes_without_rpc() -> None:
    """DB 'escrowed' was only ever written after the on-chain proof."""
    _, ak, secret = await _seed_access_job(tag="dbesc", payment_status="escrowed")
    rpc = _EscrowStub({})
    tok = await _verify(ak, secret, rpc)
    assert tok is not None
    assert rpc.calls == []


async def test_released_payment_with_released_escrow_is_denied() -> None:
    """A settled escrow must not keep minting shop work."""
    job_id, ak, secret = await _seed_access_job(tag="rel", payment_status="released")
    rpc = _EscrowStub({job_id: _locked_escrow(state="released")})
    assert await _verify(ak, secret, rpc) is None


async def test_refunded_payment_is_denied() -> None:
    job_id, ak, secret = await _seed_access_job(tag="ref", payment_status="refunded")
    rpc = _EscrowStub({job_id: _locked_escrow(state="refunded")})
    assert await _verify(ak, secret, rpc) is None


async def test_unfunded_escrow_state_is_denied() -> None:
    """'created' means the lock tx never funded — not escrowed."""
    job_id, ak, secret = await _seed_access_job(tag="unf")
    rpc = _EscrowStub({job_id: _locked_escrow(state="created")})
    assert await _verify(ak, secret, rpc) is None


async def test_locked_escrow_amount_mismatch_is_denied() -> None:
    job_id, ak, secret = await _seed_access_job(tag="amt")
    rpc = _EscrowStub({job_id: _locked_escrow(amount="2.0")})
    assert await _verify(ak, secret, rpc) is None


async def test_locked_escrow_party_mismatch_is_denied() -> None:
    job_id, ak, secret = await _seed_access_job(tag="party")
    rpc = _EscrowStub({job_id: _locked_escrow(provider="0x" + "33" * 20)})
    assert await _verify(ak, secret, rpc) is None


async def test_escrow_job_id_payload_binding_is_used() -> None:
    """ai-submit shape: escrow keyed by the coordinator job id, not the
    market job id — the token record binds it via payload.escrow_job_id."""
    market_job_id, ak, secret = await _seed_access_job(tag="aibind", escrow_job_id="coord_job_1")
    rpc = _EscrowStub({"coord_job_1": _locked_escrow()})
    tok = await _verify(ak, secret, rpc)
    assert tok is not None
    assert tok["job_id"] == market_job_id
    assert rpc.calls == ["coord_job_1"]


async def test_escrow_job_id_binding_still_requires_locked_escrow() -> None:
    """The binding field is caller-supplied — it must not bypass the proof."""
    _, ak, secret = await _seed_access_job(tag="aibad", escrow_job_id="coord_job_gone")
    rpc = _EscrowStub({})
    assert await _verify(ak, secret, rpc) is None


async def test_rpc_failure_denies_token() -> None:
    """Fail closed: an unreadable escrow is not a verified escrow."""
    _, ak, secret = await _seed_access_job(tag="rpcerr")

    class _Boom:
        async def verify_escrow(self, job_id: str):
            raise RuntimeError("chain rpc down")

    assert await _verify(ak, secret, _Boom()) is None  # type: ignore[arg-type]


async def test_job_without_payment_row_is_denied() -> None:
    """Legacy/manual rows with no MarketJobPayment have no escrow to verify."""
    async with get_session_context() as session:
        MarketService(session)
        job = MarketJob(
            service_type="whisper",
            buyer_address=BUYER,
            provider_address=PROVIDER,
            state="RUNNING",
            access_key="ak_nopay",
            payload={"cid": "QmX", "access_key": "ak_nopay", "access_secret": "sec_nopay"},
        )
        session.add(job)
        await session.commit()
        job_id = job.id

    rpc = _EscrowStub({job_id: _locked_escrow()})
    assert await _verify("ak_nopay", "sec_nopay", rpc) is None
