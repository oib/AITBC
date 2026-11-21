"""#2325 MARKET-ESCROW-ALIAS-1: one locked escrow backs at most one live token.

#2322 bound the shop access token to a locked on-chain escrow, but every
field that check compares — ``payload["escrow_job_id"]``, buyer/provider
addresses, payment amount — is caller-supplied at ``POST /v1/market/jobs``
(user-tier key), and the on-chain escrow record carries no market-job
reference (its ``job_id`` IS the lookup key). A caller could therefore point
``escrow_job_id`` — or even choose a job id equal to a foreign escrow key —
at ANY locked escrow and mint unlimited shop tokens off it.

Pinned here:

* a second active job declaring the same ``escrow_job_id`` is denied while
  the earliest claimant's token still verifies (one escrow, one token);
* the earliest-created claimant wins, so registering an alias cannot strip
  the legitimate job's token;
* a job whose own id names a foreign escrow key loses to an earlier
  ``escrow_job_id`` claimant just the same;
* when the winner's job leaves the active states the key is released for
  the next claimant (bounded squatting, self-healing);
* ``payment.status == "escrowed"`` no longer shortcuts an ``escrow_job_id``
  alias record: that status only ever proved the escrow keyed by
  ``job.id``, so alias jobs always take the live verify.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from market_service.domain.market import MarketJob, MarketJobPayment
from market_service.services.market_service import MarketService
from market_service.storage import get_session_context
from sqlmodel import col, select

pytestmark = pytest.mark.asyncio

BUYER = "0x" + "11" * 20
PROVIDER = "0x" + "22" * 20


class _EscrowStub:
    """verify_escrow stub keyed by escrow/job id.

    ``bindings`` maps a lock tx hash to the market job id its payload
    ``market_job_id`` names (#2326) — alias claims verify only when the
    escrow's signed lock tx binds them.
    """

    def __init__(self, escrows: dict[str, dict] | None = None, bindings: dict[str, str] | None = None) -> None:
        self.escrows = escrows or {}
        self.bindings = bindings or {}
        self.calls: list[str] = []

    async def verify_escrow(self, job_id: str):
        self.calls.append(job_id)
        return self.escrows.get(job_id)

    async def get_transaction(self, tx_hash: str, chain_id: str | None = None):
        market_job_id = self.bindings.get(tx_hash)
        if market_job_id is None:
            return None
        return {"payload": {"market_job_id": market_job_id}}


def _locked_escrow(
    *,
    amount: str = "1.0",
    state: str = "locked",
    buyer: str = BUYER,
    provider: str = PROVIDER,
    lock_tx_hash: str | None = None,
) -> dict:
    escrow = {"state": state, "amount": amount, "buyer": buyer, "provider": provider}
    if lock_tx_hash:
        escrow["lock_tx_hash"] = lock_tx_hash
    return escrow


def _bound_rpc(escrow_key: str, market_job_id: str, **escrow_kwargs) -> _EscrowStub:
    """Escrow stub whose lock tx payload binds ``market_job_id`` (#2326)."""
    lock_hash = f"lock_{escrow_key}"
    return _EscrowStub(
        {escrow_key: _locked_escrow(lock_tx_hash=lock_hash, **escrow_kwargs)},
        bindings={lock_hash: market_job_id},
    )


async def _seed_access_job(
    *,
    tag: str,
    payment_status: str = "pending",
    amount: str = "1.0",
    escrow_job_id: str | None = None,
    job_id: str | None = None,
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
            "buyer_address": BUYER,
            "provider_address": PROVIDER,
            "expires_at": (datetime.now(UTC) + timedelta(days=7)).isoformat(),
            "payload": payload,
            "payment": {"amount": amount},
        }
        if job_id:
            data["id"] = job_id
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


async def test_second_alias_for_same_escrow_is_denied() -> None:
    """The reported hole: two active jobs claiming one locked escrow —
    only the earliest claimant's token verifies."""
    t0 = (datetime.now(UTC) - timedelta(hours=1)).replace(tzinfo=None)
    first_id, ak1, sec1 = await _seed_access_job(tag="alias_first", escrow_job_id="coord_shared_1", created_at=t0)
    second_id, ak2, sec2 = await _seed_access_job(
        tag="alias_second", escrow_job_id="coord_shared_1", created_at=t0 + timedelta(seconds=1)
    )
    assert first_id != second_id
    rpc = _bound_rpc("coord_shared_1", first_id)

    tok1 = await _verify(ak1, sec1, rpc)
    assert tok1 is not None and tok1["job_id"] == first_id
    # The alias is denied BEFORE the escrow is even consulted — uniqueness
    # is checked first, so the denied job costs no RPC.
    calls_before = len(rpc.calls)
    assert await _verify(ak2, sec2, rpc) is None
    assert len(rpc.calls) == calls_before


async def test_alias_cannot_displace_legitimate_claimant() -> None:
    """Registering an alias after the legit job never strips its token."""
    t0 = (datetime.now(UTC) - timedelta(hours=1)).replace(tzinfo=None)
    legit_id, ak_legit, sec_legit = await _seed_access_job(tag="alias_legit", escrow_job_id="coord_shared_2", created_at=t0)
    _, ak_evil, sec_evil = await _seed_access_job(
        tag="alias_evil", escrow_job_id="coord_shared_2", created_at=t0 + timedelta(seconds=1)
    )
    rpc = _bound_rpc("coord_shared_2", legit_id)
    assert await _verify(ak_legit, sec_legit, rpc) is not None
    assert await _verify(ak_evil, sec_evil, rpc) is None
    # And the legit job still verifies afterwards — no state was mutated.
    assert (await _verify(ak_legit, sec_legit, rpc) or {}).get("job_id") == legit_id


async def test_earlier_alias_wins_until_it_expires() -> None:
    """Squatting is bounded twice over: the earlier claimant holds the key
    only while it stays active, AND #2326's lock-tx binding means the escrow
    authorizes only the market job its signed lock names — a later claimant
    is denied even after the squatter's job expires, because the escrow was
    never locked for it."""
    t0 = (datetime.now(UTC) - timedelta(hours=1)).replace(tzinfo=None)
    squat_id, ak_squat, sec_squat = await _seed_access_job(tag="alias_squat", escrow_job_id="coord_shared_3", created_at=t0)
    legit_id, ak_legit, sec_legit = await _seed_access_job(
        tag="alias_legit3", escrow_job_id="coord_shared_3", created_at=t0 + timedelta(seconds=1)
    )
    # The escrow's lock tx binds the squatter's market job — the only job
    # this escrow may ever authorize.
    rpc = _bound_rpc("coord_shared_3", squat_id)
    assert await _verify(ak_squat, sec_squat, rpc) is not None
    assert await _verify(ak_legit, sec_legit, rpc) is None

    # The squatter's job terminates — uniqueness releases the key, but the
    # on-chain binding still denies the legit job: this escrow was locked
    # for squat_id, not legit_id.
    async with get_session_context() as session:
        squat_job = (
            await session.execute(select(MarketJob).where(col(MarketJob.access_key) == "ak_alias_squat"))
        ).scalar_one()
        squat_job.state = "EXPIRED"
        session.add(squat_job)
        await session.commit()

    assert await _verify(ak_legit, sec_legit, rpc) is None
    assert legit_id != squat_id


async def test_job_id_named_escrow_loses_to_earlier_claim() -> None:
    """A caller-chosen job id equal to a foreign escrow key is just another
    claim on that key — ordering decides, not which field named it."""
    t0 = (datetime.now(UTC) - timedelta(hours=1)).replace(tzinfo=None)
    # First claimant: a market job whose caller-chosen id IS the escrow key
    # (no payload binding needed — the key defaults to job.id).
    byid_id, ak_byid, sec_byid = await _seed_access_job(
        tag="alias_byid",
        job_id="escrow_key_shared_4",
        created_at=t0,
    )
    # Second claimant: the ai-submit shape, payload.escrow_job_id binding.
    _, ak_payload, sec_payload = await _seed_access_job(
        tag="alias_payload",
        escrow_job_id="escrow_key_shared_4",
        created_at=t0 + timedelta(seconds=1),
    )
    rpc = _EscrowStub({"escrow_key_shared_4": _locked_escrow()})
    assert (await _verify(ak_byid, sec_byid, rpc) or {}).get("job_id") == byid_id
    assert await _verify(ak_payload, sec_payload, rpc) is None


async def test_escrowed_payment_does_not_skip_alias_verify() -> None:
    """payment.status == 'escrowed' proved only the escrow keyed by job.id —
    an escrow_job_id alias record must still verify the alias escrow live."""
    alias_id, ak, secret = await _seed_access_job(
        tag="alias_escrowed",
        payment_status="escrowed",
        escrow_job_id="coord_alias_paid",
    )
    # No escrow under the alias key: previously the escrowed fast-path
    # returned True with zero checks.
    rpc = _EscrowStub({})
    assert await _verify(ak, secret, rpc) is None
    assert rpc.calls == ["coord_alias_paid"]

    # With the alias escrow locked, matching AND bound to this market job
    # by its lock tx, the token verifies — via the live path.
    rpc2 = _bound_rpc("coord_alias_paid", alias_id)
    assert await _verify(ak, secret, rpc2) is not None
    assert rpc2.calls == ["coord_alias_paid"]


async def test_self_bound_escrowed_payment_still_skips_rpc() -> None:
    """Regression: the escrowed fast-path is unchanged for jobs whose escrow
    key IS the market job id (the #2322 pin-confirm proof)."""
    job_id, ak, secret = await _seed_access_job(tag="selfesc", payment_status="escrowed")
    rpc = _EscrowStub({})
    tok = await _verify(ak, secret, rpc)
    assert tok is not None and tok["job_id"] == job_id
    assert rpc.calls == []
