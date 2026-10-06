"""Owed-change pass (Task A6/F1b) — deferred buyer-change settlement.

The release route never signs the change leg in-request: it would collide
on the release's own (sender, nonce) mempool slot, and an in-request
seal-wait would out-live every caller timeout on this block interval
(60 s configured, 66–72 s observed). This pass pays owed change instead —
derived only from sealed chain legs, gated on an empty authority mempool,
marked only from a sealed refund leg.

Owed = lock_units − Σbilled − Σrefund, with billed proven per sealed
release leg by ``recompute_release_proofs`` (A7): the route records the
billed gross per submission and the sealed leg must equal the recomputed
route fee rule exactly. Legacy rows without recorded billed, unpaired
legs, or recompute mismatches defer unproven rather than guessing.
"""

from decimal import Decimal
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from sqlmodel import Session, create_engine

from aitbc_chain.base_models import Escrow, Transaction
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.rpc import escrow_settlement_sweeper as ess

CHAIN = "test-chain"
JOB = "a6_job"
BUYER = "0xe8b0db006F34bf5b5d2B22553C017431E8e86e4F"
PROVIDER = "0xD4d85501E6cD447972Db19370307F1E3B1510016"
AUTHORITY = "0x03DF9Ed3788E5BA3991e6788036f9D171f027716"

NOW = datetime(2026, 10, 5, 18, 0, 0, tzinfo=UTC)
OLD = NOW - timedelta(hours=2)
V11 = 35400

# Metered settle: lock 36000, billed gross 18000 → release leg pays
# 17550 = billed·(1−250bps), fee bound 450 — the buyer is owed 18000 change
# (= lock − billed gross), while custody still holds 18450 = owed + fee.
# A7: the row records billed gross per release leg ({tx_hash, billed}); the
# pass proves the sealed leg by recomputing the route's own fee rule.
LOCK, RELEASE, FEE, OWED = 36000, 17550, 450, 18000
BILLED = 18000


def _billed_legs(job_id: str, billed: int = BILLED, tx_hash: str | None = None) -> list[dict]:
    return [{"tx_hash": tx_hash or f"0xrel-{job_id}", "billed": billed}]


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    chain_metadata.create_all(engine)
    with Session(engine) as open_session:
        yield open_session


def _tx(
    session,
    tx_type: str,
    tx_hash: str,
    value: int,
    *,
    job_id: str = JOB,
    height: int = V11 + 5,
    at: datetime = OLD,
    sender: str = AUTHORITY,
    recipient: str = PROVIDER,
    action: str | None = None,
) -> Transaction:
    action = (
        action
        or {
            "ESCROW_LOCK": "escrow_lock",
            "ESCROW_RELEASE": "escrow_release",
            "ESCROW_REFUND": "escrow_refund",
            "ESCROW_FEE_SWEEP": "escrow_fee_sweep",
        }[tx_type]
    )
    tx = Transaction(
        chain_id=CHAIN,
        tx_hash=tx_hash,
        sender=sender,
        recipient=recipient,
        type=tx_type,
        value=value,
        block_height=height,
        created_at=at,
        payload={"action": action, "job_id": job_id},
    )
    session.add(tx)
    session.commit()
    return tx


def _row(session, job_id: str = JOB, **overrides) -> Escrow:
    fields = {
        "job_id": job_id,
        "chain_id": CHAIN,
        "buyer": BUYER,
        "provider": PROVIDER,
        "amount": LOCK,
        "status": "released",
        "protected": False,
        "energy_fee_basis_points": None,
        "released_at": OLD,
        "released_amount": RELEASE,
        "refunded_amount": None,
        "refund_tx_hash": None,
        "billed_legs": _billed_legs(job_id),
    }
    fields.update(overrides)
    row = Escrow(**fields)
    session.add(row)
    session.commit()
    return row


def _candidates(session, **kwargs):
    kwargs.setdefault("max_jobs", 50)
    kwargs.setdefault("min_height", V11)
    candidates, stats, _watermark = ess.change_owed_candidates(session, NOW, **kwargs)
    return candidates, stats


def _metered_chain(session, job_id: str = JOB):
    _tx(session, "ESCROW_LOCK", f"0xlock-{job_id}", LOCK, job_id=job_id)
    _tx(session, "ESCROW_RELEASE", f"0xrel-{job_id}", RELEASE, job_id=job_id)


# ------------------------------------------------------------ selection


def test_owed_change_derived_exactly(session):
    """lock 36000 − billed 18000 = owed 18000; the sealed release leg is
    proven by recomputing the route's fee rule from the recorded billed
    (17550 = 18000·0.975); custody the legs imply is the lock minus what
    already left."""
    _metered_chain(session)
    _row(session)
    candidates, stats = _candidates(session)
    assert len(candidates) == 1
    assert candidates[0].owed_units == OWED
    assert candidates[0].custody_units == LOCK - RELEASE
    assert candidates[0].buyer_address == BUYER


def test_no_sealed_release_leg_is_no_legs(session):
    """C19: a released-marked row whose release leg never sealed has no owed
    change — the provider was never paid. A foreign/mistyped settlement leg
    feeding min_settlement_height must not turn that into a ≈lock refund."""
    _tx(session, "ESCROW_LOCK", "0xlock", LOCK)
    _tx(session, "ESCROW_RELEASE", "0xodd", RELEASE, action="something_else")
    _row(session)
    candidates, stats = _candidates(session)
    assert candidates == []
    assert stats["no_legs"] == 1


def test_sweep_leg_alone_is_no_legs(session):
    """C19 companion: an ESCROW_FEE_SWEEP leg feeds min_settlement_height but
    is not a provider release — no release leg, no candidate."""
    _tx(session, "ESCROW_LOCK", "0xlock", LOCK)
    _tx(session, "ESCROW_FEE_SWEEP", "0xsweep", FEE)
    _row(session)
    candidates, stats = _candidates(session)
    assert candidates == []
    assert stats["no_legs"] == 1


def test_full_release_has_no_owed(session):
    """Full-price settle (release = lock − fee): nothing owed to the buyer."""
    _tx(session, "ESCROW_LOCK", "0xlock", LOCK)
    _tx(session, "ESCROW_RELEASE", "0xrel", 35100)  # billed == lock: 36000·0.975
    _row(session, billed_legs=_billed_legs(JOB, billed=36000, tx_hash="0xrel"))
    candidates, stats = _candidates(session)
    assert candidates == []
    assert stats["no_owed"] == 1


@pytest.mark.asyncio
async def test_sealed_refund_leg_heals_row_mark(session, monkeypatch):
    """Restart-survivability + persistence (A6b): a released+unmarked row
    whose refund leg sealed is marked from chain truth — and the mark must
    survive the session closing. A fresh-session re-read proves it landed in
    the database; a second tick finds the row already marked and reports
    nothing (no repeat marks, no inflated counter)."""
    _metered_chain(session)
    _tx(session, "ESCROW_REFUND", "0xref", OWED, job_id=JOB)
    _row(session)
    _patch_pass_session(monkeypatch, session)
    _patch_route(monkeypatch, {JOB: FEE})
    monkeypatch.setattr(ess, "_proposer_pending_txs", AsyncMock(return_value=[]))
    stats = await ess._change_pass_once(NOW)
    assert stats["marked"] == 1

    # Fresh session, same engine: the mark must be database state, not the
    # in-memory object the earlier version of this test only ever checked.
    engine = session.get_bind()
    with Session(engine) as fresh:
        persisted = fresh.get(Escrow, JOB)
        assert persisted is not None
        assert persisted.refunded_amount == OWED
        assert persisted.refund_tx_hash == "0xref"

    stats = await ess._change_pass_once(NOW + timedelta(minutes=2))
    assert stats["marked"] == 0
    assert stats["submitted"] == 0


def test_hash_marked_row_fills_null_refunded_amount(session):
    """w1 live shape: the mark sweeper stamped refund_tx_hash (and
    refunded_at) when the leg sealed but never wrote refunded_amount.
    Without the amount the row re-enters this scan every cycle forever —
    the heal must fill it from the sealed leg sum and drop the row out."""
    _metered_chain(session)
    _tx(session, "ESCROW_REFUND", "0xref", OWED, job_id=JOB)
    row = _row(session, refund_tx_hash="0xref")
    candidates, stats = _candidates(session)
    assert candidates == []
    assert stats["marked"] == 1
    assert row.refunded_amount == OWED
    assert row.refund_tx_hash == "0xref"
    # Fully marked now: the row leaves discovery entirely.
    candidates, stats = _candidates(session)
    assert candidates == []
    assert not any(stats.values())


def test_partial_refund_marks_sealed_truth(session):
    """A sealed under-paid refund on an unmarked row: the heal records the
    sealed sum — the row marks what the chain proves, never what was asked.
    The remainder stays in custody and out of auto-redrive (marked rows exit
    discovery); the fee pass's unproven-residue defer flags it for ops."""
    _metered_chain(session)
    _tx(session, "ESCROW_REFUND", "0xref", 10000, job_id=JOB)
    row = _row(session)
    candidates, stats = _candidates(session)
    assert candidates == []
    assert stats["marked"] == 1
    assert row.refunded_amount == 10000


def test_unreleased_row_not_discovered(session):
    """Discovery is released_at-gated: a locked-but-unreleased row is not the
    change pass's job (a dropped release means the mark sweeper owns it)."""
    _tx(session, "ESCROW_LOCK", "0xlock", LOCK)
    _row(session, released_at=None, released_amount=None, status="locked")
    candidates, stats = _candidates(session)
    assert candidates == []
    assert not any(stats.values())


def test_marked_row_not_discovered(session):
    _metered_chain(session)
    _tx(session, "ESCROW_REFUND", "0xref", OWED, job_id=JOB)
    _row(session, refunded_amount=OWED, refund_tx_hash="0xref")
    candidates, stats = _candidates(session)
    assert candidates == []
    assert not any(stats.values())


def test_protected_bump_release_proves_exactly(session):
    """A7 census shape (f0d0604b): protected release bumped to the signed
    credit — 274154 locked, billed 274154, sealed 267301 = max(net 267300,
    credit). Inversion could never prove this; recompute proves it exactly
    and the job has no owed change."""
    _tx(session, "ESCROW_LOCK", "0xlock", 274154)
    _tx(session, "ESCROW_RELEASE", "0xrel", 267301)
    _row(
        session,
        amount=274154,
        released_amount=267301,
        protected=True,
        energy_fee_basis_points=250,
        energy_provider_credit_units=267301,
        energy_net_floor_units=267300,
        billed_legs=_billed_legs(JOB, billed=274154, tx_hash="0xrel"),
    )
    candidates, stats = _candidates(session)
    assert candidates == []  # billed == lock → nothing owed
    assert stats["no_owed"] == 1


def test_zero_fee_rate_proves(session):
    """A7c: bps=0 is a legal signed quote — net equals billed, withheld is
    zero, the recompute must not refuse it (owed = lock − billed stands)."""
    _tx(session, "ESCROW_LOCK", "0xlock", LOCK)
    _tx(session, "ESCROW_RELEASE", "0xrel", 18000)  # bps=0 → provider gets billed whole
    _row(
        session,
        energy_fee_basis_points=0,
        billed_legs=_billed_legs(JOB, billed=18000, tx_hash="0xrel"),
    )
    candidates, stats = _candidates(session)
    assert len(candidates) == 1
    assert candidates[0].owed_units == 18000  # 36000 − 18000


def test_protected_billed_below_credit_refuses(session):
    """A7b: a protected billed below the signed credit is impossible — the
    route refuses that release outright (billable < target → 422), so the
    entry is corrupt. Without this guard the bump would mask it: sealed
    267301 = max(net(200000) 195000, credit) 'proves' and owed inflates to
    lock − billed = 74154 against custody of only 6853."""
    _tx(session, "ESCROW_LOCK", "0xlock", 274154)
    _tx(session, "ESCROW_RELEASE", "0xrel", 267301)
    _row(
        session,
        amount=274154,
        released_amount=267301,
        protected=True,
        energy_fee_basis_points=250,
        energy_provider_credit_units=267301,
        energy_net_floor_units=267300,
        billed_legs=_billed_legs(JOB, billed=200000, tx_hash="0xrel"),
    )
    candidates, stats = _candidates(session)
    assert candidates == []
    assert stats["deferred_unproven"] == 1


def test_protected_billed_below_net_floor_refuses(session):
    """A7b companion: the route also refuses billable < energy_net_floor —
    here the sealed value matches plain net(B) so only the floor
    precondition refuses it."""
    _tx(session, "ESCROW_LOCK", "0xlock", 274154)
    _tx(session, "ESCROW_RELEASE", "0xrel", 195000)  # = net(200000) at 250bps
    _row(
        session,
        amount=274154,
        released_amount=195000,
        protected=True,
        energy_fee_basis_points=250,
        energy_provider_credit_units=150000,  # bump does not apply: 195000 > 150000
        energy_net_floor_units=267300,
        billed_legs=_billed_legs(JOB, billed=200000, tx_hash="0xrel"),
    )
    candidates, stats = _candidates(session)
    assert candidates == []
    assert stats["deferred_unproven"] == 1


def test_owed_above_custody_refuses(session):
    """A7b: owed > custody means a leg is missing or treasury over-swept —
    the chain would refuse the refund regardless; defer as unproven instead
    of signing into an apply-failure + backoff loop."""
    _tx(session, "ESCROW_LOCK", "0xlock", LOCK)
    _tx(session, "ESCROW_RELEASE", "0xrel", RELEASE)
    _tx(session, "ESCROW_FEE_SWEEP", "0xsweep", 500)  # swept 500 > withheld 450
    _row(session, billed_legs=_billed_legs(JOB, tx_hash="0xrel"))
    candidates, stats = _candidates(session)
    # custody = 36000−17550−500 = 17950 < owed 18000 → refuse
    assert candidates == []
    assert stats["deferred_unproven"] == 1


def test_protected_recompute_mismatch_defers(session):
    """Protected + credit recorded: a sealed value equal to NEITHER the net
    nor the credit bump fails the recompute — defer."""
    _metered_chain(session)
    _row(
        session,
        protected=True,
        energy_fee_basis_points=250,
        energy_provider_credit_units=20000,  # bump would have applied: expected 20000 ≠ 17550
    )
    candidates, stats = _candidates(session)
    assert candidates == []
    assert stats["deferred_unproven"] == 1


def test_legacy_row_without_billed_stays_unproven(session):
    """A7: rows released before billed was recorded carry billed_legs=NULL —
    they remain unproven forever, no inversion fallback."""
    _metered_chain(session)
    _row(session, billed_legs=None)
    candidates, stats = _candidates(session)
    assert candidates == []
    assert stats["deferred_unproven"] == 1


def test_sealed_release_without_billed_entry_refuses(session):
    """A sealed release leg whose hash matches no recorded billed entry is
    not provable — the pass cannot know what it billed."""
    _tx(session, "ESCROW_LOCK", "0xlock", LOCK)
    _tx(session, "ESCROW_RELEASE", "0xother-hash", RELEASE)
    _row(session)  # billed entry keys 0xrel-<job>, leg hashes 0xother-hash
    candidates, stats = _candidates(session)
    assert candidates == []
    assert stats["deferred_unproven"] == 1


def test_orphaned_billed_entry_tolerated(session):
    """A dropped re-drive leaves a billed entry whose hash never sealed —
    it pairs with nothing and is skipped, not fatal."""
    _metered_chain(session)
    _row(
        session,
        billed_legs=_billed_legs(JOB) + [{"tx_hash": "0xdropped", "billed": BILLED}],
    )
    candidates, stats = _candidates(session)
    assert len(candidates) == 1
    assert candidates[0].owed_units == OWED


def test_tampered_billed_refuses(session):
    """A recorded billed that recomputes to a different sealed value is
    proof of nothing — defer, never pay on it."""
    _metered_chain(session)
    _row(session, billed_legs=_billed_legs(JOB, billed=12000))  # net 11700 ≠ 17550
    candidates, stats = _candidates(session)
    assert candidates == []
    assert stats["deferred_unproven"] == 1


def test_multiple_release_legs_unproven(session):
    """Two sealed release legs mean a reused id / second contract — which
    contract's protected fields applied is unknowable from the row."""
    _metered_chain(session)
    _tx(session, "ESCROW_RELEASE", "0xrel2", RELEASE)
    _row(
        session,
        billed_legs=_billed_legs(JOB) + [{"tx_hash": "0xrel2", "billed": BILLED}],
    )
    candidates, stats = _candidates(session)
    assert candidates == []
    assert stats["deferred_unproven"] == 1


def test_non_integral_release_defers_unproven(session):
    """A release value the recompute cannot match (recorded billed 18000 →
    expected 17550, sealed 10000) yields no provable owed — defer."""
    _tx(session, "ESCROW_LOCK", "0xlock", LOCK)
    _tx(session, "ESCROW_RELEASE", "0xrel", 10000)
    # billed pairs (hash matches) but recomputes to 17550 ≠ sealed 10000
    _row(session, billed_legs=_billed_legs(JOB, tx_hash="0xrel"))
    candidates, stats = _candidates(session)
    assert candidates == []
    assert stats["deferred_unproven"] == 1


def test_floor_straddler_skipped(session):
    """A reused id's pre-floor settlement leg (any non-lock leg below the
    floor) poisons the lock/refund sums — same floor rule as the fee pass:
    the whole job stays off-limits even with a post-floor release."""
    _tx(session, "ESCROW_LOCK", "0xlock", LOCK, height=V11 - 100)
    _tx(session, "ESCROW_REFUND", "0xold-ref", 500, height=V11 - 50)
    _tx(session, "ESCROW_RELEASE", "0xrel", RELEASE, height=V11 + 5)
    _row(session)
    candidates, stats = _candidates(session)
    assert candidates == []
    assert stats["skipped_floor"] == 1


def test_ring_rotates_through_rows(session):
    """More released-unmarked rows than the cap — the watermark ring inspects
    each once per cycle instead of starving the tail."""
    for i in range(3):
        _metered_chain(session, job_id=f"job{i}")
        _row(session, job_id=f"job{i}")
    seen = []
    watermark = ""
    for _ in range(4):
        candidates, _stats, watermark = ess.change_owed_candidates(
            session, NOW, max_jobs=1, min_height=V11, after_job_id=watermark
        )
        seen.extend(c.job_id for c in candidates)
    assert seen == ["job0", "job1", "job2", "job0"]


# ------------------------------------------------------------ async driver


def _patch_route(monkeypatch, custody: dict | None, submit_returns="0xrefhash"):
    monkeypatch.setenv("ESCROW_CHANGE_PASS_ENABLED", "1")
    monkeypatch.setattr("aitbc_chain.rpc.escrow_routes._get_settlement_key", lambda: "k")
    monkeypatch.setattr("aitbc_chain.rpc.escrow_routes._get_settlement_address", lambda: AUTHORITY)
    custody_mock = AsyncMock(side_effect=lambda job_id: (custody or {}).get(job_id))
    monkeypatch.setattr("aitbc_chain.rpc.escrow_routes._escrow_custody_balance", custody_mock)
    monkeypatch.setattr("aitbc_chain.rpc.escrow_routes._find_contract_id", AsyncMock(return_value="c1"))
    monkeypatch.setattr(ess, "get_escrow_manager", lambda: object())
    submit = AsyncMock(return_value=submit_returns)
    monkeypatch.setattr("aitbc_chain.rpc.escrow_routes._submit_refund_tx", submit)
    return submit


def _patch_pass_session(monkeypatch, session):
    from contextlib import contextmanager

    @contextmanager
    def _scope():
        yield session

    monkeypatch.setattr(ess, "session_scope", _scope)


def _route_tx(sender: str, tx_type: str, nonce: int = 7) -> dict:
    return {
        "from": sender,
        "to": PROVIDER,
        "amount": 10,
        "fee": 5,
        "nonce": nonce,
        "type": tx_type,
        "signature": "0xsig",
        "chain_id": CHAIN,
    }


def _mempool_pending(*txs: dict) -> list[dict]:
    from aitbc_chain.mempool import InMemoryMempool

    mp = InMemoryMempool(chain_id=CHAIN)
    for tx in txs:
        mp.add(dict(tx), CHAIN)
    return mp.get_pending_transactions(CHAIN)


@pytest.mark.asyncio
async def test_enabled_but_keyless_still_ticks(session, monkeypatch):
    """A7c: an enabled pass without a settlement key must still emit its
    tick heartbeat — otherwise it is invisible to the Stale alerts while
    being unable to ever submit."""
    from aitbc_chain.metrics import escrow_change_pass_total

    monkeypatch.setenv("ESCROW_CHANGE_PASS_ENABLED", "1")
    monkeypatch.setattr("aitbc_chain.rpc.escrow_routes._get_settlement_key", lambda: None)
    monkeypatch.setattr("aitbc_chain.rpc.escrow_routes._get_settlement_address", lambda: None)
    before = escrow_change_pass_total.labels(result="tick")._value.get()
    stats = await ess._change_pass_once(NOW)
    assert not any(stats.values())
    assert escrow_change_pass_total.labels(result="tick")._value.get() == before + 1


@pytest.mark.asyncio
async def test_owed_change_refund_submits(session, monkeypatch):
    _metered_chain(session)
    _row(session)
    _patch_pass_session(monkeypatch, session)
    submit = _patch_route(monkeypatch, {JOB: LOCK - RELEASE})
    monkeypatch.setattr(ess, "_proposer_pending_txs", AsyncMock(return_value=[]))
    stats = await ess._change_pass_once(NOW)
    assert stats["submitted"] == 1
    submit.assert_awaited_once_with(BUYER, PROVIDER, Decimal("0.0005"), JOB, "c1")


@pytest.mark.asyncio
async def test_pending_authority_tx_blocks_refund(session, monkeypatch):
    """No leg is signed while any authority transaction is pending — a refund
    built now would collide on the same (sender, nonce) slot."""
    _metered_chain(session)
    _row(session)
    _patch_pass_session(monkeypatch, session)
    submit = _patch_route(monkeypatch, {JOB: LOCK - RELEASE})
    pending = _mempool_pending(_route_tx(AUTHORITY, "ESCROW_RELEASE"))
    monkeypatch.setattr(ess, "_proposer_pending_txs", AsyncMock(return_value=pending))
    stats = await ess._change_pass_once(NOW)
    assert stats["deferred_pending"] == 1
    submit.assert_not_awaited()


@pytest.mark.asyncio
async def test_pending_probe_failure_fails_closed(session, monkeypatch):
    _metered_chain(session)
    _row(session)
    _patch_pass_session(monkeypatch, session)
    submit = _patch_route(monkeypatch, {JOB: LOCK - RELEASE})
    monkeypatch.setattr(ess, "_proposer_pending_txs", AsyncMock(return_value=None))
    stats = await ess._change_pass_once(NOW)
    assert stats["deferred_pending"] == 1
    submit.assert_not_awaited()


@pytest.mark.asyncio
async def test_malformed_mempool_body_fails_closed(session, monkeypatch):
    """C19: a 200 mempool answer whose 'transactions' key is missing/mistyped
    is an unread mempool, not an empty one — the probe returns None and the
    pass defers instead of signing on a mempool it cannot see."""
    _metered_chain(session)
    _row(session)
    _patch_pass_session(monkeypatch, session)
    submit = _patch_route(monkeypatch, {JOB: LOCK - RELEASE})
    from types import SimpleNamespace

    resp = SimpleNamespace(status_code=200, json=lambda: {"count": 3})
    monkeypatch.setattr(ess.SharedHttpClient, "get", AsyncMock(return_value=resp))
    stats = await ess._change_pass_once(NOW)
    assert stats["deferred_pending"] == 1
    submit.assert_not_awaited()


@pytest.mark.asyncio
async def test_second_probe_pending_defers_before_signing(session, monkeypatch):
    """A6c: the first probe is a stale snapshot by submission time — a leg
    landing between the two probes is caught by the re-probe right before
    signing. Deferred, never signed."""
    _metered_chain(session)
    _row(session)
    _patch_pass_session(monkeypatch, session)
    submit = _patch_route(monkeypatch, {JOB: LOCK - RELEASE})
    pending_now = _mempool_pending(_route_tx(AUTHORITY, "ESCROW_RELEASE"))
    probe = AsyncMock(side_effect=[[], pending_now])
    monkeypatch.setattr(ess, "_proposer_pending_txs", probe)
    stats = await ess._change_pass_once(NOW)
    assert probe.await_count == 2
    assert stats["deferred_pending"] == 1
    assert stats["submitted"] == 0
    submit.assert_not_awaited()


@pytest.mark.asyncio
async def test_second_probe_failure_fails_closed(session, monkeypatch):
    """A6c: a failing re-probe defers the same as a populated one — never
    sign on an unreadable mempool."""
    _metered_chain(session)
    _row(session)
    _patch_pass_session(monkeypatch, session)
    submit = _patch_route(monkeypatch, {JOB: LOCK - RELEASE})
    probe = AsyncMock(side_effect=[[], None])
    monkeypatch.setattr(ess, "_proposer_pending_txs", probe)
    stats = await ess._change_pass_once(NOW)
    assert stats["deferred_pending"] == 1
    assert stats["submitted"] == 0
    submit.assert_not_awaited()


@pytest.mark.asyncio
async def test_custody_mismatch_defers(session, monkeypatch):
    """Custody must equal exactly what the sealed legs imply — a touched or
    drained escrow account defers rather than pays on a guess."""
    _metered_chain(session)
    _row(session)
    _patch_pass_session(monkeypatch, session)
    submit = _patch_route(monkeypatch, {JOB: LOCK - RELEASE + 1})
    monkeypatch.setattr(ess, "_proposer_pending_txs", AsyncMock(return_value=[]))
    stats = await ess._change_pass_once(NOW)
    assert stats["deferred_custody"] == 1
    submit.assert_not_awaited()


@pytest.mark.asyncio
async def test_dry_run_counts_and_submits_nothing(session, monkeypatch):
    _metered_chain(session)
    _row(session)
    _patch_pass_session(monkeypatch, session)
    monkeypatch.setenv("ESCROW_CHANGE_PASS_DRY_RUN", "1")
    submit = _patch_route(monkeypatch, {JOB: LOCK - RELEASE})
    monkeypatch.setattr(ess, "_proposer_pending_txs", AsyncMock(return_value=[]))
    stats = await ess._change_pass_once(NOW)
    assert stats["dry_run"] == 1
    submit.assert_not_awaited()


@pytest.mark.asyncio
async def test_disabled_flag_is_inert(session, monkeypatch):
    _metered_chain(session)
    _row(session)
    _patch_pass_session(monkeypatch, session)
    submit = _patch_route(monkeypatch, {JOB: LOCK - RELEASE})
    monkeypatch.delenv("ESCROW_CHANGE_PASS_ENABLED", raising=False)
    stats = await ess._change_pass_once(NOW)
    assert not any(stats.values())
    submit.assert_not_awaited()


@pytest.mark.asyncio
async def test_submit_failure_backs_off(session, monkeypatch):
    """A deterministically rejected refund backs off instead of resubmitting
    every tick — same D9 discipline as the fee pass."""
    _metered_chain(session)
    _row(session)
    _patch_pass_session(monkeypatch, session)
    submit = _patch_route(monkeypatch, {JOB: LOCK - RELEASE}, submit_returns=None)
    monkeypatch.setattr(ess, "_proposer_pending_txs", AsyncMock(return_value=[]))
    ess._change_pass_failures.clear()
    try:
        stats = await ess._change_pass_once(NOW)
        assert stats["error"] == 1
        assert JOB in ess._change_pass_failures
        stats = await ess._change_pass_once(NOW + timedelta(seconds=30))
        assert stats["deferred_backoff"] == 1
        assert submit.await_count == 1
    finally:
        ess._change_pass_failures.clear()


@pytest.mark.asyncio
async def test_refund_unsealed_then_sealed_marks(session, monkeypatch):
    """The refund-unsealed case: tick 1 submits and the row stays unmarked;
    once the leg seals, the next tick heals the row from chain truth."""
    _metered_chain(session)
    row = _row(session)
    _patch_pass_session(monkeypatch, session)
    _patch_route(monkeypatch, {JOB: LOCK - RELEASE})
    monkeypatch.setattr(ess, "_proposer_pending_txs", AsyncMock(return_value=[]))
    stats = await ess._change_pass_once(NOW)
    assert stats["submitted"] == 1
    assert row.refunded_amount is None  # accepted ≠ sealed — nothing marked

    # The leg seals: the next tick marks the row and owes nothing more.
    _tx(session, "ESCROW_REFUND", "0xrefhash", OWED, job_id=JOB, at=NOW)
    stats = await ess._change_pass_once(NOW + timedelta(minutes=2))
    assert stats["marked"] == 1
    assert stats["submitted"] == 0
    assert row.refunded_amount == OWED
    assert row.refund_tx_hash == "0xrefhash"


@pytest.mark.asyncio
async def test_change_pass_runs_before_fee_pass(monkeypatch):
    """Sequencing: the change pass is evaluated ahead of the fee pass in the
    tick, so a refund it submits lands in the proposer mempool and trips the
    fee pass's pending guard — the two legs never share a mempool window."""
    order = []
    monkeypatch.setattr(ess, "_change_pass_once", AsyncMock(side_effect=lambda *a: order.append("change") or {}))
    monkeypatch.setattr(ess, "_fee_sweep_pass_once", AsyncMock(side_effect=lambda *a: order.append("fee") or {}))
    monkeypatch.setattr(ess, "_proposer_pending_hashes", AsyncMock(return_value=set()))
    from contextlib import contextmanager
    from unittest.mock import MagicMock

    @contextmanager
    def _scope():
        yield MagicMock()

    monkeypatch.setattr(ess, "session_scope", _scope)
    monkeypatch.setattr(ess, "sweep_once", lambda s, n, p: {"demoted": 0, "remarked": 0, "rows": 0, "verified": 0})
    await ess._sweep_once()
    assert order == ["change", "fee"]
