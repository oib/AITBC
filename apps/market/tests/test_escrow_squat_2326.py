"""#2326 MARKET-ESCROW-SQUAT-1: cheap mitigations against escrow-key squatting.

#2325 made escrow-key claims unique (earliest active claimant wins) but the
claim itself stayed attacker-steerable: ``sw_job_*`` ids were deterministic
(CLI side, pinned in ``tests/cli``), ``expires_at`` was unbounded, expired-
but-unswept jobs still claimed, ``payment.amount == 0`` jobs claimed, and an
``escrow_job_id`` alias with an omitted ``buyer_address`` skipped the party
check entirely.

Pinned here (market-service side):

* an expired-but-unswept claimant (``expires_at < now``, still QUEUED/RUNNING)
  does not hold the key — the next claimant is released;
* a zero-amount job cannot claim an escrow key at all;
* an alias claim must name the escrow's buyer — omitting ``buyer_address``
  denies the token even when every other term matches;
* ``create_market_job`` rejects an ``expires_at`` beyond the ttl ceiling.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from market_service.domain.market import MarketJob, MarketJobPayment
from market_service.services.market_service import MarketService
from market_service.services.market_service.shared import MAX_JOB_TTL_SECONDS
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
    buyer_address: str | None = BUYER,
    expires_at: datetime | None = None,
    created_at: datetime | None = None,
) -> tuple[str, str, str]:
    """Market job + access creds + payment; returns (job_id, key, secret)."""
    async with get_session_context() as session:
        svc = MarketService(session)
        payload: dict = {"cid": "QmTest", "access_key": f"ak_{tag}", "access_secret": f"sec_{tag}"}
        if escrow_job_id:
            payload["escrow_job_id"] = escrow_job_id
        data: dict = {
            "service_type": "whisper",
            "provider_address": PROVIDER,
            "expires_at": (expires_at or (datetime.now(UTC) + timedelta(days=7))).isoformat(),
            "payload": payload,
            "payment": {"amount": amount},
        }
        if buyer_address is not None:
            data["buyer_address"] = buyer_address
        created = await svc.create_market_job(data)
        new_job_id = created["job_id"]
        job = await session.get(MarketJob, new_job_id)
        assert job is not None
        if created_at is not None:
            job.created_at = created_at.replace(tzinfo=None)
        if payment_status != "pending":
            payment = await session.get(MarketJobPayment, job.payment_id)
            assert payment is not None
            payment.status = payment_status
            payment.updated_at = datetime.now(UTC).replace(tzinfo=None)
            session.add(payment)
        session.add(job)
        await session.commit()
    return new_job_id, f"ak_{tag}", f"sec_{tag}"


async def _verify(ak: str, secret: str, rpc: _EscrowStub) -> dict | None:
    async with get_session_context() as session:
        svc = MarketService(session)
        svc._rpc_client = rpc  # type: ignore[assignment]
        return await svc.get_market_job_access_token(ak, secret)


async def test_expired_unswept_claimant_releases_key() -> None:
    """A job past expires_at but still QUEUED (sweeper hasn't flipped it)
    must not squat the escrow key — the next claimant wins."""
    t0 = (datetime.now(UTC) - timedelta(hours=2)).replace(tzinfo=None)
    past = datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=5)
    _, ak_squat, sec_squat = await _seed_access_job(
        tag="squat_expired",
        escrow_job_id="coord_exp_1",
        expires_at=past,
        created_at=t0,
    )
    legit_id, ak_legit, sec_legit = await _seed_access_job(
        tag="legit_exp_1",
        escrow_job_id="coord_exp_1",
        created_at=t0 + timedelta(seconds=1),
    )
    rpc = _EscrowStub({"coord_exp_1": _locked_escrow()})

    # Verify the legit job FIRST: without the claim-query expiry filter the
    # still-QUEUED squatter (its own lazy TTL flip only runs on ITS access)
    # is the earliest active claimant and the legit token is denied.
    tok = await _verify(ak_legit, sec_legit, rpc)
    assert tok is not None and tok["job_id"] == legit_id
    # And the expired squatter's own token is denied by the TTL gate anyway.
    assert await _verify(ak_squat, sec_squat, rpc) is None


async def test_zero_amount_job_cannot_claim_escrow_key() -> None:
    """payment.amount == 0 has no escrow stake — it must not claim a key
    ahead of a paying claimant."""
    t0 = (datetime.now(UTC) - timedelta(hours=1)).replace(tzinfo=None)
    await _seed_access_job(
        tag="squat_free",
        escrow_job_id="coord_free_1",
        amount="0",
        created_at=t0,
    )
    legit_id, ak_legit, sec_legit = await _seed_access_job(
        tag="legit_free_1",
        escrow_job_id="coord_free_1",
        created_at=t0 + timedelta(seconds=1),
    )
    rpc = _EscrowStub({"coord_free_1": _locked_escrow()})
    tok = await _verify(ak_legit, sec_legit, rpc)
    assert tok is not None and tok["job_id"] == legit_id


async def test_alias_claim_requires_buyer_address() -> None:
    """An escrow_job_id alias with no buyer_address skips the party match —
    it must be denied even when amount/state/escrow all line up."""
    _, ak, sec = await _seed_access_job(
        tag="alias_nobuyer",
        escrow_job_id="coord_nobuyer_1",
        buyer_address=None,
    )
    rpc = _EscrowStub({"coord_nobuyer_1": _locked_escrow()})
    assert await _verify(ak, sec, rpc) is None


async def test_alias_claim_with_matching_buyer_verifies() -> None:
    """Regression: a well-formed alias (buyer_address = escrow buyer) still
    verifies — the requirement binds, it does not break the ai-submit shape."""
    job_id, ak, sec = await _seed_access_job(
        tag="alias_buyer",
        escrow_job_id="coord_buyer_1",
    )
    rpc = _EscrowStub({"coord_buyer_1": _locked_escrow()})
    tok = await _verify(ak, sec, rpc)
    assert tok is not None and tok["job_id"] == job_id


async def test_alias_claim_with_wrong_buyer_denied() -> None:
    """A declared buyer that does not match the escrow buyer is denied."""
    _, ak, sec = await _seed_access_job(
        tag="alias_wrongbuyer",
        escrow_job_id="coord_wrongbuyer_1",
        buyer_address="0x" + "33" * 20,
    )
    rpc = _EscrowStub({"coord_wrongbuyer_1": _locked_escrow()})
    assert await _verify(ak, sec, rpc) is None


async def test_create_rejects_unbounded_expires_at() -> None:
    """expires_at beyond requested_at + MAX_JOB_TTL_SECONDS is refused at
    creation — the year-2100 squat shape."""
    async with get_session_context() as session:
        svc = MarketService(session)
        far = (datetime.now(UTC) + timedelta(seconds=MAX_JOB_TTL_SECONDS + 3600)).isoformat()
        with pytest.raises(ValueError, match="expires_at"):
            await svc.create_market_job(
                {
                    "service_type": "whisper",
                    "buyer_address": BUYER,
                    "provider_address": PROVIDER,
                    "expires_at": far,
                    "payload": {"access_key": "ak_x", "access_secret": "sec_x"},
                    "payment": {"amount": "1.0"},
                }
            )
        # Within the ceiling still creates.
        ok = (datetime.now(UTC) + timedelta(seconds=MAX_JOB_TTL_SECONDS - 60)).isoformat()
        created = await svc.create_market_job(
            {
                "service_type": "whisper",
                "buyer_address": BUYER,
                "provider_address": PROVIDER,
                "expires_at": ok,
                "payload": {"access_key": "ak_y", "access_secret": "sec_y"},
                "payment": {"amount": "1.0"},
            }
        )
        assert created["job_id"]
