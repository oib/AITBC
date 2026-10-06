"""Demote-only settlement sweeper + v2-era route guard (S-8 "lite").

Two halves:

* ``sweep_once`` reconciles settlement claims against the sealed
  ``transaction`` table. A marked leg whose hash stays unsealed past the
  detector's 900 s threshold AND is absent from the proposer's mempool is
  demoted (timestamps cleared, ``status='settlement_failed'``, dead hash
  kept); an *unmarked* leg that is sealed is re-marked. A marked leg whose
  settlement is sealed is merely verified — healthy rows are never
  rewritten. The detector uses the same sealed-table probe, so the two
  never disagree.
* ``_refuse_v2_lock`` keeps the demote from being an accidental remedy-2: a
  demoted row reaching the release/refund routes re-drives only when its lock
  sealed at or above ``state_transition_v3_height``. V2-era locks answer 409
  so the coordinator retry paths can never replay the v2 dead-set.
"""

import asyncio
import importlib
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlmodel import Session, create_engine

from aitbc_chain.base_models import Escrow, Transaction
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.rpc import escrow_settlement_sweeper as ess

CHAIN = "test-chain"
JOB = "sw_job_t56"
BUYER = "0xe8b0db006F34bf5b5d2B22553C017431E8e86e4F"
PROVIDER = "0xD4d85501E6cD447972Db19370307F1E3B1510016"

NOW = datetime(2026, 10, 4, 12, 0, 0, tzinfo=UTC)
SEALED_AT = NOW - timedelta(hours=1)
OLD_MARK = NOW - timedelta(seconds=1800)  # past the 900 s detector threshold
FRESH_MARK = NOW - timedelta(seconds=300)  # still inside the settlement window


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    chain_metadata.create_all(engine)
    with Session(engine) as open_session:
        yield open_session


def _tx(session, tx_type: str, tx_hash: str, at: datetime = SEALED_AT, job_id: str = JOB) -> Transaction:
    tx = Transaction(
        chain_id=CHAIN,
        tx_hash=tx_hash,
        sender="0x03DF9Ed3",
        recipient=PROVIDER,
        type=tx_type,
        value=100,
        created_at=at,
        payload={"action": "settle", "job_id": job_id},
    )
    session.add(tx)
    session.commit()
    return tx


def _row(session, **overrides) -> Escrow:
    fields = {
        "job_id": JOB,
        "chain_id": CHAIN,
        "buyer": BUYER,
        "provider": PROVIDER,
        "amount": 3_600_000,
        "status": "locked",
        "released_at": None,
        "refunded_at": None,
        "release_tx_hash": None,
        "refund_tx_hash": None,
        "released_amount": None,
        "refunded_amount": None,
    }
    fields.update(overrides)
    row = Escrow(**fields)
    session.add(row)
    session.commit()
    return row


def _refresh(session, row: Escrow) -> Escrow:
    session.expire_all()
    return session.get(Escrow, row.job_id)


def _naive(dt: datetime | None) -> datetime | None:
    # SQLite round-trips datetimes naive; compare after stripping tz.
    return dt.replace(tzinfo=None) if dt is not None else None


# ---------------------------------------------------------------- sweeper


def test_marked_leg_sealed_is_verified_untouched(session):
    """A healthy row is never rewritten: acceptance-time mark and stored hash
    both stand — the sweep only verifies."""
    _tx(session, "ESCROW_RELEASE", "0xsealed-release")
    _row(session, status="released", released_at=OLD_MARK, release_tx_hash="0xsealed-release")
    stats = ess.sweep_once(session, NOW, set())
    row = _refresh(session, session.get(Escrow, JOB))
    assert stats["verified"] == 1 and stats["demoted"] == 0 and stats["remarked"] == 0
    assert _naive(row.released_at) == _naive(OLD_MARK)  # acceptance time kept
    assert row.release_tx_hash == "0xsealed-release"
    assert row.status == "released"


def test_marked_leg_inside_window_is_untouched(session):
    _row(session, status="released", released_at=FRESH_MARK, release_tx_hash="0xunsealed")
    stats = ess.sweep_once(session, NOW, set())
    row = _refresh(session, session.get(Escrow, JOB))
    assert stats["demoted"] == 0
    assert _naive(row.released_at) == _naive(FRESH_MARK)
    assert row.status == "released"


def test_marked_leg_still_in_proposer_mempool_is_untouched(session):
    """900 s < 3600 s TTL: a legitimately pending tx must not be presumed dead."""
    _row(session, status="released", released_at=OLD_MARK, release_tx_hash="0xpending")
    stats = ess.sweep_once(session, NOW, {"0xpending"})
    row = _refresh(session, session.get(Escrow, JOB))
    assert stats["demoted"] == 0
    assert _naive(row.released_at) == _naive(OLD_MARK)
    assert row.status == "released"


def test_marked_leg_dead_is_demoted_with_hash_kept(session):
    _row(session, status="released", released_at=OLD_MARK, release_tx_hash="0xdead")
    stats = ess.sweep_once(session, NOW, set())
    row = _refresh(session, session.get(Escrow, JOB))
    assert stats["demoted"] == 1
    assert row.released_at is None
    assert row.status == "settlement_failed"
    assert row.release_tx_hash == "0xdead"  # kept: the detector still flags the leg


def test_mixed_row_demotes_only_the_dead_leg(session):
    _tx(session, "ESCROW_RELEASE", "0xsealed-release")
    _row(
        session,
        status="released",
        released_at=OLD_MARK,
        refunded_at=OLD_MARK,
        release_tx_hash="0xsealed-release",
        refund_tx_hash="0xdead-refund",
    )
    stats = ess.sweep_once(session, NOW, set())
    row = _refresh(session, session.get(Escrow, JOB))
    assert stats["demoted"] == 1 and stats["verified"] == 1
    assert _naive(row.released_at) == _naive(OLD_MARK)  # verified mark untouched
    assert row.refunded_at is None
    assert row.status == "released"  # the sealed leg keeps the row settled
    assert row.refund_tx_hash == "0xdead-refund"


def test_failed_row_whose_hash_later_seals_is_remarked(session):
    _tx(session, "ESCROW_RELEASE", "0xlate-seal")
    _row(session, status="settlement_failed", released_at=None, release_tx_hash="0xlate-seal")
    stats = ess.sweep_once(session, NOW, set())
    row = _refresh(session, session.get(Escrow, JOB))
    assert stats["remarked"] == 1 and stats["demoted"] == 0
    assert _naive(row.released_at) == _naive(SEALED_AT)
    assert row.status == "released"


def test_probe_failure_never_demotes(session):
    """proposer_pending=None fails the demote closed — no unverified absence."""
    _row(session, status="released", released_at=OLD_MARK, release_tx_hash="0xdead")
    stats = ess.sweep_once(session, NOW, None)
    row = _refresh(session, session.get(Escrow, JOB))
    assert stats["demoted"] == 0
    assert _naive(row.released_at) == _naive(OLD_MARK)
    assert row.status == "released"


@pytest.mark.asyncio
async def test_pending_probe_hashes_bodies_so_marked_leg_survives(session, monkeypatch):
    """End-to-end for the F1 probe fix: /mempool returns submitted bodies
    verbatim (no tx_hash key), so the probe recomputes compute_tx_hash over
    each one. A stale marked leg whose stored hash is still pending must
    survive demotion — before the fix the probe always returned an empty
    set and this row was demoted while still pending."""
    from aitbc_chain.mempool import InMemoryMempool, compute_tx_hash

    body_tx = {
        "from": "0x03DF9Ed3788E5BA3991e6788036f9D171f027716",
        "to": "0xD4d85501E6cD447972Db19370307F1E3B1510016",
        "amount": 10,
        "fee": 5,
        "nonce": 7,
        "type": "ESCROW_RELEASE",
        "signature": "0xsig",
        "chain_id": CHAIN,
    }
    mp = InMemoryMempool(chain_id=CHAIN)
    mp.add(dict(body_tx), CHAIN)
    pending_bodies = mp.get_pending_transactions(CHAIN)
    stored_hash = compute_tx_hash(pending_bodies[0])  # what the route stored

    _row(session, status="released", released_at=OLD_MARK, release_tx_hash=stored_hash)
    resp = SimpleNamespace(
        status_code=200,
        json=lambda: {"success": True, "transactions": pending_bodies, "count": len(pending_bodies)},
    )
    monkeypatch.setattr(ess.SharedHttpClient, "get", AsyncMock(return_value=resp))

    @contextmanager
    def _scope():
        yield session

    monkeypatch.setattr(ess, "session_scope", _scope)
    monkeypatch.setattr(ess, "_fee_sweep_pass_once", AsyncMock(return_value={}))
    stats = await ess._sweep_once()
    row = _refresh(session, session.get(Escrow, JOB))
    assert stats["demoted"] == 0
    assert row.release_tx_hash == stored_hash
    assert row.status == "released"


def test_status_only_claim_demotes_when_dead(session):
    """A row claiming settled through status alone is swept the same way."""
    _row(session, status="released", released_at=None, release_tx_hash="0xdead")
    stats = ess.sweep_once(session, NOW, set())
    row = _refresh(session, session.get(Escrow, JOB))
    assert stats["demoted"] == 1  # the status-only claim is itself demoted
    assert row.status == "settlement_failed"  # and the claim re-derived away
    assert row.release_tx_hash == "0xdead"  # hash kept so the detector still flags it


def test_status_only_claim_with_sealed_hash_is_remarked(session):
    """A status-claimed leg that turns out sealed gets the mark written —
    the one case besides demote where a write is allowed."""
    _tx(session, "ESCROW_RELEASE", "0xsealed-release")
    _row(session, status="released", released_at=None, release_tx_hash="0xsealed-release")
    stats = ess.sweep_once(session, NOW, set())
    row = _refresh(session, session.get(Escrow, JOB))
    assert stats["remarked"] == 1
    assert _naive(row.released_at) == _naive(SEALED_AT)
    assert row.status == "released"


def test_sealed_stored_hash_is_never_overwritten(session):
    """Double-settle anomaly (job 46025c0e sealed twice): the stored sealed
    hash stays even though a second sealed tx exists for the job."""
    _tx(session, "ESCROW_RELEASE", "0xfirst-seal")
    _tx(session, "ESCROW_RELEASE", "0xsecond-seal")
    _row(session, status="released", released_at=OLD_MARK, release_tx_hash="0xfirst-seal")
    ess.sweep_once(session, NOW, set())
    row = _refresh(session, session.get(Escrow, JOB))
    assert row.release_tx_hash == "0xfirst-seal"
    assert _naive(row.released_at) == _naive(OLD_MARK)


def test_marked_leg_with_missing_hash_stays_flagged(session):
    """A marked leg whose stored hash is absent is verified via the job's
    sealed tx — it is *not* demoted — but the row is not rewritten either,
    so the detector's claim-by-mark still flags the missing audit trail."""
    _tx(session, "ESCROW_RELEASE", "0xsealed-release")
    _row(session, status="released", released_at=OLD_MARK, release_tx_hash=None)
    stats = ess.sweep_once(session, NOW, set())
    row = _refresh(session, session.get(Escrow, JOB))
    assert stats["verified"] == 1 and stats["demoted"] == 0
    assert _naive(row.released_at) == _naive(OLD_MARK)
    assert row.release_tx_hash is None  # no silent rewrite; flag stays honest


def test_dead_stored_hash_on_marked_leg_does_not_demote_when_job_sealed(session):
    """Mark is true (the job sealed under another hash): no demote, and no
    rewrite either — the dead stored hash keeps flagging for the operator."""
    _tx(session, "ESCROW_RELEASE", "0xreal-seal")
    _row(session, status="released", released_at=OLD_MARK, release_tx_hash="0xdead-hash")
    stats = ess.sweep_once(session, NOW, set())
    row = _refresh(session, session.get(Escrow, JOB))
    assert stats["verified"] == 1 and stats["demoted"] == 0
    assert _naive(row.released_at) == _naive(OLD_MARK)
    assert row.release_tx_hash == "0xdead-hash"


def test_unmarked_refund_leg_with_sealed_hash_is_remarked(session):
    """The metered-row heal: refunded_at NULL + sealed refund hash → re-mark."""
    _tx(session, "ESCROW_RELEASE", "0xsealed-release")
    _tx(session, "ESCROW_REFUND", "0xsealed-refund")
    _row(
        session,
        status="released",
        released_at=OLD_MARK,
        refunded_at=None,
        release_tx_hash="0xsealed-release",
        refund_tx_hash="0xsealed-refund",
    )
    stats = ess.sweep_once(session, NOW, set())
    row = _refresh(session, session.get(Escrow, JOB))
    assert stats["remarked"] == 1
    assert _naive(row.refunded_at) == _naive(SEALED_AT)
    assert _naive(row.released_at) == _naive(OLD_MARK)  # the marked leg untouched
    assert row.refunded_amount == 100  # sealed leg value, filled with the mark
    assert row.status == "released"


def test_verified_refund_mark_fills_null_refunded_amount(session):
    """A row whose refunded_at+hash were already stamped by an earlier heal
    but whose refunded_amount stayed NULL gets the amount filled on the
    verified path — the sealed leg proves it. NULL would leave the row in
    the change pass's refunded_amount-IS-NULL scan forever."""
    _tx(session, "ESCROW_RELEASE", "0xsealed-release")
    _tx(session, "ESCROW_REFUND", "0xsealed-refund")
    _row(
        session,
        status="released",
        released_at=OLD_MARK,
        refunded_at=OLD_MARK,
        release_tx_hash="0xsealed-release",
        refund_tx_hash="0xsealed-refund",
        refunded_amount=None,
    )
    stats = ess.sweep_once(session, NOW, set())
    row = _refresh(session, session.get(Escrow, JOB))
    assert stats["verified"] == 2 and stats["remarked"] == 0
    assert row.refunded_amount == 100
    assert row.status == "released"


# ---------------------------------------------------------- mempool probe


@pytest.mark.asyncio
async def test_truncated_mempool_answer_is_probe_failure(monkeypatch):
    """count >= limit means the tail could hide the pending hash — fail closed."""
    monkeypatch.setenv("HUB_BLOCKCHAIN_RPC_URL", "http://proposer:8202/rpc")
    resp = SimpleNamespace(
        status_code=200,
        json=lambda: {"transactions": [{"tx_hash": "0xa"}], "count": ess._MEMPOOL_PROBE_LIMIT},
    )
    monkeypatch.setattr(ess.SharedHttpClient, "get", AsyncMock(return_value=resp))
    assert await ess._proposer_pending_hashes() is None


@pytest.mark.asyncio
async def test_non_200_probe_is_failure(monkeypatch):
    monkeypatch.setenv("HUB_BLOCKCHAIN_RPC_URL", "http://proposer:8202/rpc")
    resp = SimpleNamespace(status_code=503, json=lambda: {})
    monkeypatch.setattr(ess.SharedHttpClient, "get", AsyncMock(return_value=resp))
    assert await ess._proposer_pending_hashes() is None


@pytest.mark.asyncio
async def test_probe_reads_proposer_env_url_first(monkeypatch):
    """HUB_BLOCKCHAIN_RPC_URL points at the actual proposer on every host;
    the local BLOCKCHAIN_RPC_URL (which on followers is the node's own
    mempool) is only the fallback."""
    monkeypatch.setenv("HUB_BLOCKCHAIN_RPC_URL", "http://proposer:8202/rpc")
    seen = {}
    resp = SimpleNamespace(
        status_code=200,
        json=lambda: {"transactions": [], "count": 0},
    )

    async def _get(url, **kw):
        seen["url"] = url
        return resp

    monkeypatch.setattr(ess.SharedHttpClient, "get", AsyncMock(side_effect=_get))
    assert await ess._proposer_pending_hashes() == set()
    assert seen["url"].startswith("http://proposer:8202/rpc/mempool")


@pytest.mark.asyncio
async def test_probe_falls_back_to_route_hub_url(monkeypatch):
    monkeypatch.delenv("HUB_BLOCKCHAIN_RPC_URL", raising=False)
    seen = {}
    resp = SimpleNamespace(status_code=200, json=lambda: {"transactions": [], "count": 0})

    async def _get(url, **kw):
        seen["url"] = url
        return resp

    monkeypatch.setattr(ess.SharedHttpClient, "get", AsyncMock(side_effect=_get))
    assert await ess._proposer_pending_hashes() == set()
    assert seen["url"].startswith(f"{ess._HUB_RPC_URL}/mempool")


# ------------------------------------------------------------- v2-era guard


def _reload_routes():
    from aitbc_chain.rpc import escrow_routes

    importlib.reload(escrow_routes)
    return escrow_routes


def _env(monkeypatch):
    monkeypatch.setenv("ESCROW_RELEASE_PRIVATE_KEY", "0x2222222222222222222222222222222222222222222222222222222222222222")
    monkeypatch.setenv("GENESIS_WALLET_PRIVATE_KEY", "0x1111111111111111111111111111111111111111111111111111111111111111")
    monkeypatch.setenv("HUB_RPC_URL", "http://localhost:8202")
    monkeypatch.setenv("CHAIN_ID", "test-chain")


def _record(**overrides):
    fields = {
        "amount": 72_000_000,
        "status": "locked",
        "protected": False,
        "released_at": None,
        "refunded_at": None,
        "released_amount": None,
        "refunded_amount": None,
        "release_tx_hash": None,
        "refund_tx_hash": None,
        "job_tx_hash": None,
        "contract_id": "c1",
        "energy_settlement_asset": None,
        "energy_settlement_unit_scale": None,
        "energy_fee_basis_points": None,
        "energy_provider_credit_units": None,
        "energy_net_floor_units": None,
    }
    fields.update(overrides)
    return SimpleNamespace(**fields)


class _FakeSession:
    def __init__(self, record):
        self.record = record
        self.committed = False

    def get(self, model, key):
        return self.record

    def add(self, obj):
        pass

    def commit(self):
        self.committed = True


def _session_scope(record):
    session = _FakeSession(record)

    @contextmanager
    def _scope():
        yield session

    return _scope, session


def _mgr(er, contract=None):
    mgr = MagicMock()
    mgr.escrow_contracts = {"c1": contract} if contract else {}
    mgr.release_lock = MagicMock(side_effect=lambda cid: asyncio.Lock())
    mgr.snapshot_release_state = MagicMock(return_value={})
    mgr.snapshot_refund_state = MagicMock(return_value={})
    mgr.release_payment = AsyncMock(return_value=(True, "released"))
    mgr.refund_contract = AsyncMock(return_value=(True, "refunded"))
    mgr.restore_after_failed_settlement = MagicMock()
    mgr.restore_after_failed_refund = MagicMock()
    return mgr


def _funded_contract(er):
    contract = MagicMock()
    contract.state = er.EscrowState.FUNDED
    contract.released_amount = Decimal("1.0")
    contract.refunded_amount = Decimal("1.0")
    contract.client_address = "0x4444444444444444444444444444444444444444"
    contract.agent_address = "0x3333333333333333333333333333333333333333"
    contract.milestones = [{"amount": "1.0", "completed": False, "verified": False}]
    contract.fee_rate = Decimal("0")
    return contract


def _route_patches(er, *, mgr, scope, lock_tx):
    """The outside world for a settlement attempt: lock sealed (gate passes),
    era probe answering ``lock_tx``, submissions mocked."""
    return (
        patch.object(er, "get_escrow_manager", return_value=mgr),
        patch.object(er, "session_scope", scope),
        patch.object(er, "backfill_settlement_legs"),
        patch.object(er, "_find_contract_id", new_callable=AsyncMock, return_value="c1"),
        patch.object(er, "_find_existing_lock", new_callable=AsyncMock, return_value=(lock_tx or {}).get("tx_hash")),
        patch.object(er, "_find_existing_lock_tx", new_callable=AsyncMock, return_value=lock_tx),
        patch.object(er, "_find_existing_release", new_callable=AsyncMock, return_value=None),
        patch.object(er, "_find_existing_refund", new_callable=AsyncMock, return_value=None),
        patch.object(er, "_submit_payment_tx", new_callable=AsyncMock, return_value="0xnewrelease"),
        patch.object(er, "_submit_refund_tx", new_callable=AsyncMock, return_value="0xnewrefund"),
    )


V3_HEIGHT = 5470
V2_LOCK = {"tx_hash": "0xv2lock", "block_height": 5469, "payload": {"job_id": "j1"}}
V3_LOCK = {"tx_hash": "0xv3lock", "block_height": 6000, "payload": {"job_id": "j1"}}


def _with_settings(er, monkeypatch):
    monkeypatch.setattr(er.settings, "state_transition_v3_height", V3_HEIGHT)


@pytest.mark.asyncio
async def test_v2_failed_row_release_409(monkeypatch):
    """A demoted v2 row is not resubmitted by the route — the coordinator's
    retry path gets 409, so the sweeper can never replay the v2 dead-set."""
    _env(monkeypatch)
    er = _reload_routes()
    _with_settings(er, monkeypatch)
    record = _record(status="settlement_failed", release_tx_hash="0xdead")
    scope, session = _session_scope(record)
    contract = _funded_contract(er)
    mgr = _mgr(er, contract)
    p = _route_patches(er, mgr=mgr, scope=scope, lock_tx=V2_LOCK)
    with p[0], p[1], p[2], p[3], p[4], p[5], p[6], p[7], p[8] as submit_release, p[9]:
        with pytest.raises(HTTPException) as exc:
            await er.release_escrow("j1", {})
        assert exc.value.status_code == 409
        submit_release.assert_not_called()  # never resubmits a v2-era lock
    assert not session.committed


@pytest.mark.asyncio
async def test_v2_failed_row_refund_409(monkeypatch):
    """The refund route — the other coordinator retry path — refuses the same
    v2-era lock, so neither retry lane can repay a v2 row."""
    _env(monkeypatch)
    er = _reload_routes()
    _with_settings(er, monkeypatch)
    record = _record(status="settlement_failed", refund_tx_hash="0xdead")
    scope, session = _session_scope(record)
    contract = _funded_contract(er)
    mgr = _mgr(er, contract)
    p = _route_patches(er, mgr=mgr, scope=scope, lock_tx=V2_LOCK)
    with p[0], p[1], p[2], p[3], p[4], p[5], p[6], p[7], p[8], p[9]:
        with pytest.raises(HTTPException) as exc:
            await er.refund_escrow("j1", {"reason": "test"})
        assert exc.value.status_code == 409
    assert not session.committed


@pytest.mark.asyncio
async def test_v3_failed_row_redrives_and_replaces_dead_hash(monkeypatch):
    """A demoted v3 row re-drives once through the normal route: the new
    settlement hash replaces the dead one the sweeper kept."""
    _env(monkeypatch)
    er = _reload_routes()
    _with_settings(er, monkeypatch)
    record = _record(status="settlement_failed", release_tx_hash="0xdead", refund_tx_hash="0xdeadref")
    scope, session = _session_scope(record)
    contract = _funded_contract(er)
    mgr = _mgr(er, contract)
    p = _route_patches(er, mgr=mgr, scope=scope, lock_tx=V3_LOCK)
    with p[0], p[1], p[2], p[3], p[4], p[5], p[6], p[7], p[8], p[9]:
        result = await er.release_escrow("j1", {})
    assert result.get("tx_hash") == "0xnewrelease"
    assert record.release_tx_hash == "0xnewrelease"  # dead hash replaced
    assert record.status == "released"
    assert record.released_at is not None


@pytest.mark.asyncio
async def test_v2_failed_row_without_lock_defers_425(monkeypatch):
    """No sealed lock (the 5f6ebf5f shape): the sealed-lock gate answers 425
    before the era guard can run."""
    _env(monkeypatch)
    er = _reload_routes()
    _with_settings(er, monkeypatch)
    record = _record(status="settlement_failed", release_tx_hash="0xdead")
    scope, session = _session_scope(record)
    mgr = _mgr(er, _funded_contract(er))
    p = _route_patches(er, mgr=mgr, scope=scope, lock_tx=None)
    with p[0], p[1], p[2], p[3], p[4], p[5], p[6], p[7], p[8], p[9]:
        with pytest.raises(HTTPException) as exc:
            await er.release_escrow("j1", {})
        assert exc.value.status_code == 425
    assert not session.committed


@pytest.mark.asyncio
async def test_unverifiable_lock_era_refuses(monkeypatch):
    """A lock returned without a readable block_height is refused, not trusted."""
    _env(monkeypatch)
    er = _reload_routes()
    _with_settings(er, monkeypatch)
    record = _record(status="settlement_failed", release_tx_hash="0xdead")
    scope, session = _session_scope(record)
    mgr = _mgr(er, _funded_contract(er))
    lock_no_height = {"tx_hash": "0xlock", "payload": {"job_id": "j1"}}
    p = _route_patches(er, mgr=mgr, scope=scope, lock_tx=lock_no_height)
    with p[0], p[1], p[2], p[3], p[4], p[5], p[6], p[7], p[8], p[9]:
        with pytest.raises(HTTPException) as exc:
            await er.release_escrow("j1", {})
        assert exc.value.status_code == 409
    assert not session.committed
