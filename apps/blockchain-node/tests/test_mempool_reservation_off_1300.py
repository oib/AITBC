"""#1300 P2-v2.4 — flag OFF (``mempool_reservation_enabled=False``) leaks no
reservation state into the mempool.

The existing reservation suite proves the armed lifecycle and that OFF takes
the drain branch. This file pins the OFF *side effects*: through select,
fork-revert requeue and the deleter paths, the ``mempool_reservation`` table
stays empty, no release counter moves and the legacy delete-on-read drain
stays authoritative. It also characterizes what a disarm leaves behind
(markers written while armed) so that behavior is recorded, not assumed.

SQLite by default; ``Q1300_PG_URL`` runs the same legs on PostgreSQL.
"""

from __future__ import annotations

import time

from aitbc_chain.config import settings
from aitbc_chain.metrics import mempool_reservation_release_total
from sqlalchemy import text

from . import test_mempool_reservation_1300 as _base

_chain_session = _base._chain_session
_proposer_stub = _base._proposer_stub
_seed = _base._seed
_tx = _base._tx
# Re-exported pytest fixtures (assignment, not import: parameters named
# ``pool``/``chain`` must not trip F811).
chain = _base.chain
pool = _base.pool


def _marker_rows(pool, chain: str) -> int:
    with pool._engine.begin() as conn:
        return int(
            conn.execute(text("SELECT COUNT(*) FROM mempool_reservation WHERE chain_id = :c"), {"c": chain}).scalar() or 0
        )


def _release_counter_total() -> float:
    return sum(
        sample.value
        for metric in mempool_reservation_release_total.collect()
        for sample in metric.samples
        if sample.name.endswith("_total")
    )


def test_off_select_and_drain_write_no_markers(pool, chain, tmp_path, monkeypatch):
    """Several OFF proposal selections over a refilling pool: rows are
    consumed by drain, the marker table never gains a row and no release
    counter moves."""
    monkeypatch.setattr(settings, "mempool_reservation_enabled", False)
    proposer = _proposer_stub(chain)
    before = _release_counter_total()
    for rnd in range(5):
        hashes = [pool.add(_tx(rnd * 10 + i, chain), chain_id=chain) for i in range(1, 4)]
        with _chain_session(tmp_path) as session:
            txs, reserved = proposer._select_mempool_txs(
                session,
                pool,
                100,
                10_000_000,
                reservation_owner="owner-a",  # supplied but flag OFF: must be ignored
                reservation_proposer="0xp",
                reservation_height=10 + rnd,
                reservation_round=0,
            )
        assert {t.tx_hash for t in txs} == set(hashes)
        assert reserved == set()
        assert pool.size(chain_id=chain) == 0
        assert _marker_rows(pool, chain) == 0
        assert pool.live_reservations(chain) == {}
    assert _release_counter_total() == before


def test_off_fork_revert_requeue_creates_nothing(pool, chain, monkeypatch):
    """requeue_orphaned_transactions calls release_reservations(…,
    "fork_reverted") even OFF. With no markers that must be a pure no-op:
    no row appears and the release counter does not move."""
    from aitbc_chain import mempool as mempool_mod
    from aitbc_chain.state.block_deltas import requeue_orphaned_transactions

    monkeypatch.setattr(settings, "mempool_reservation_enabled", False)
    hashes = _seed(pool, chain)
    monkeypatch.setattr(mempool_mod, "_MEMPOOL", pool)
    before = _release_counter_total()
    payloads = [{**_tx(i, chain), "tx_hash": h} for i, h in enumerate(hashes, 1)]
    requeue_orphaned_transactions(chain, payloads)
    assert _marker_rows(pool, chain) == 0
    assert pool.live_reservations(chain) == {}
    assert _release_counter_total() == before


def test_off_deleters_not_blocked(pool, chain):
    """OFF pool: remove / batch_remove / evict_expired behave as baseline —
    the empty marker table must not shield any row."""
    hashes = _seed(pool, chain)
    assert pool.remove(hashes[0], chain) is True
    assert pool.batch_remove(hashes[1:], chain_id=chain) == 2
    assert pool.size(chain_id=chain) == 0
    assert _marker_rows(pool, chain) == 0


def test_release_ledger_without_reserved_hashes_is_silent():
    """An OFF attempt has reserved_hashes == set(): the ledger must make no
    release call on any exit path (cancelled / sealed / leftovers)."""
    from aitbc_chain.consensus.poa import _ProposalReleaseLedger

    calls: list[tuple] = []

    class _Pool:
        def release_reservations(self, *a, **kw):
            calls.append((a, kw))

    ledger = _ProposalReleaseLedger(_Pool(), "c", set(), {}, "owner-a")
    ledger.release_hashes(["0xabc"], "sealed")
    ledger.release_leftovers("cancelled")
    assert calls == []


def test_disarm_leaves_live_markers_until_released_or_ttl(pool, chain, tmp_path, monkeypatch):
    """Characterization (not a defect claim): markers written while armed
    survive a disarm. OFF drain() ignores them (legacy stays authoritative,
    rows are consumed), but the marker rows persist as 'reserved' until
    expiry or an explicit release, and until then shield the pool-side
    deleters. Pins the residue an operator disarm leaves behind."""
    hashes = _seed(pool, chain)
    pool.peek_reserve(chain, owner_id="owner-a", height=10)
    assert set(pool.live_reservations(chain)) == set(hashes)

    monkeypatch.setattr(settings, "mempool_reservation_enabled", False)
    # Deleters still honor the live markers after disarm.
    assert pool.remove(hashes[0], chain) is False
    # OFF drain takes the rows regardless.
    proposer = _proposer_stub(chain)
    with _chain_session(tmp_path) as session:
        txs, reserved = proposer._select_mempool_txs(session, pool, 100, 10_000_000)
    assert {t.tx_hash for t in txs} == set(hashes)
    assert reserved == set()
    assert pool.size(chain_id=chain) == 0
    # Markers persist (orphaned) until TTL sweep / release.
    assert set(pool.live_reservations(chain)) == set(hashes)
    # An explicit release clears them.
    pool.release_owner_reservations(chain, "owner-a", "cancelled")
    assert pool.live_reservations(chain) == {}


def test_disarm_markers_expire_by_ttl(pool, chain):
    """The residue above is bounded: after the TTL the marker no longer
    counts as live (the sweep/`expires_at>now` predicates ignore it)."""
    _seed(pool, chain)
    pool.peek_reserve(chain, owner_id="owner-a", height=10, ttl_seconds=0.01)
    time.sleep(0.05)
    assert pool.live_reservations(chain) == {}
