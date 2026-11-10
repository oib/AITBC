"""Batch v3 item 21: pins for #1300 reservation mutants that survived the lifecycle suite.

Surviving mutants found by ``scratch/batch30/mutate1300.py`` against
``test_mempool_reservation_1300.py`` (SQLite) and what pins them here:

* the PostgreSQL ``_peek_reserve_session`` path was never exercised on SQLite
  (ignore other owners' reservations, skip TTL sweep, never write markers) ->
  parity legs drive BOTH implementations through the same scenarios;
* ``max_bytes`` bound; release reason recorded on fork revert; owner-scoped
  release; ``remove`` protection (the existing leg called ``pool.remove(chain,
  hash)`` with swapped arguments, so it never reached the reservation check);
  ``reconcile_sealed`` markers; expired markers do not protect rows.

Runs on SQLite; ``Q1300_PG_URL`` points the same legs at PostgreSQL.
"""

from __future__ import annotations

import os
import time
import uuid

import pytest
from sqlalchemy import text

from aitbc_chain.mempool import DatabaseMempool


def _tx(nonce: int, chain: str, sender: str = "0xsender", pad: int = 0) -> dict:
    return {
        "from": sender,
        "to": "0xrecipient",
        "amount": 5,
        "fee": 1,
        "nonce": nonce,
        "payload": {"to": "0xrecipient", "amount": 5, "memo": "x" * pad},
        "type": "TRANSFER",
        "chain_id": chain,
        "signature": "0xsig",
    }


@pytest.fixture
def pool(tmp_path):
    url = os.environ.get("Q1300_PG_URL") or f"sqlite:///{tmp_path / 'mempool.db'}"
    p = DatabaseMempool(url, max_size=100, min_fee=0)
    yield p
    p._engine.dispose()


@pytest.fixture
def chain() -> str:
    return "resv-" + uuid.uuid4().hex[:8]


def _seed(pool: DatabaseMempool, chain: str, n: int = 3, **kw) -> list[str]:
    return [pool.add(_tx(i, chain, **kw), chain_id=chain) for i in range(1, n + 1)]


def _peek(pool: DatabaseMempool, impl: str, chain: str, owner: str, **kw):
    """Drive one implementation directly: 'sqlite' (BEGIN IMMEDIATE) or 'session' (PG path)."""
    now = time.time()
    ttl = kw.pop("ttl_seconds", 60.0)
    args = {
        "owner_id": owner,
        "proposer": "0xp",
        "height": 10,
        "round": 0,
        "attempt_seq": 0,
        "now": now,
        "expires": now + ttl,
        "max_count": kw.pop("max_count", 0),
        "max_bytes": kw.pop("max_bytes", 0),
    }
    fn = pool._peek_reserve_sqlite if impl == "sqlite" else pool._peek_reserve_session
    return fn(chain, **args)


def _state(pool: DatabaseMempool, chain: str) -> dict[str, tuple[str, str | None, str | None]]:
    with pool._engine.begin() as conn:
        rows = conn.execute(
            text("SELECT tx_hash, owner_id, state, release_reason FROM mempool_reservation WHERE chain_id = :c"),
            {"c": chain},
        ).all()
    return {r[0]: (r[1], r[2], r[3]) for r in rows}


IMPLS = [
    "session",
    pytest.param("sqlite", marks=pytest.mark.skipif(bool(os.environ.get("Q1300_PG_URL")), reason="sqlite-only impl")),
]


@pytest.mark.parametrize("impl", IMPLS)
class TestPeekReserveImplementationParity:
    def test_reserves_without_deleting_and_writes_markers(self, pool, chain, impl):
        hashes = _seed(pool, chain)
        got = _peek(pool, impl, chain, "a")
        assert {t.tx_hash for t in got} == set(hashes)
        assert pool.size(chain_id=chain) == len(hashes)
        assert {h: v[0] for h, v in _state(pool, chain).items()} == dict.fromkeys(hashes, "a")
        assert pool.live_reservations(chain) == dict.fromkeys(hashes, "a")

    def test_other_owner_is_excluded_same_owner_replaces(self, pool, chain, impl):
        hashes = _seed(pool, chain)
        _peek(pool, impl, chain, "a")
        assert _peek(pool, impl, chain, "b") == []
        again = _peek(pool, impl, chain, "a")
        assert {t.tx_hash for t in again} == set(hashes)

    def test_expired_reservation_is_swept_and_taken_over(self, pool, chain, impl):
        hashes = _seed(pool, chain)
        _peek(pool, impl, chain, "a", ttl_seconds=0.01)
        time.sleep(0.05)
        got = _peek(pool, impl, chain, "b")
        assert {t.tx_hash for t in got} == set(hashes)
        assert pool.live_reservations(chain) == dict.fromkeys(hashes, "b")

    def test_max_count_bound(self, pool, chain, impl):
        _seed(pool, chain, 4)
        assert len(_peek(pool, impl, chain, "a", max_count=2)) == 2
        assert len(pool.live_reservations(chain)) == 2

    def test_max_bytes_bound(self, pool, chain, impl):
        # Rows are ~tens of bytes of JSON each; a bound below one row's size reserves nothing,
        # a bound above the whole set reserves everything.
        hashes = _seed(pool, chain, 3, pad=200)
        assert _peek(pool, impl, chain, "a", max_bytes=10) == []
        assert pool.live_reservations(chain) == {}
        assert {t.tx_hash for t in _peek(pool, impl, chain, "a", max_bytes=10_000_000)} == set(hashes)


def test_max_bytes_cuts_between_rows(pool, chain):
    _seed(pool, chain, 3, pad=200)
    with pool._engine.begin() as conn:
        sizes = [r[0] for r in conn.execute(text("SELECT size_bytes FROM mempool WHERE chain_id = :c"), {"c": chain})]
    bound = sizes[0] + 1  # fits one row, not two
    assert len(pool.peek_reserve(chain, owner_id="a", height=10, max_bytes=bound)) == 1


def test_fork_revert_records_reason_and_leaves_other_reservations(pool, chain, monkeypatch):
    from aitbc_chain import mempool as mempool_mod
    from aitbc_chain.state.block_deltas import requeue_orphaned_transactions

    hashes = _seed(pool, chain, 3)
    pool.peek_reserve(chain, owner_id="a", height=10, max_count=3)
    monkeypatch.setattr(mempool_mod, "_MEMPOOL", pool)
    reverted = hashes[:2]
    requeue_orphaned_transactions(chain, [{**_tx(i, chain), "tx_hash": h} for i, h in enumerate(reverted, 1)])
    state = _state(pool, chain)
    for h in reverted:
        assert state[h][1:] == ("released", "fork_reverted")
    assert state[hashes[2]][1] == "reserved"  # a tx that was not reverted stays reserved


def test_release_owner_is_scoped_to_that_owner(pool, chain):
    hashes = _seed(pool, chain, 4)
    pool.peek_reserve(chain, owner_id="a", height=10, max_count=2)
    pool.peek_reserve(chain, owner_id="b", height=10, max_count=2)
    live = pool.live_reservations(chain)
    assert sorted(set(live.values())) == ["a", "b"]
    pool.release_owner_reservations(chain, "a", "apply_abort")
    after = pool.live_reservations(chain)
    assert set(after.values()) == {"b"} and len(after) == 2
    assert len(hashes) == 4


def test_release_reservations_with_owner_only_touches_that_owner(pool, chain):
    hashes = _seed(pool, chain, 2)
    pool.peek_reserve(chain, owner_id="a", height=10)
    assert pool.release_reservations(chain, hashes, "outbid", owner_id="other") == 0
    assert pool.live_reservations(chain) == dict.fromkeys(hashes, "a")
    assert pool.release_reservations(chain, hashes, "outbid", owner_id="a") == 2


def test_remove_protects_live_reservation_with_correct_arguments(pool, chain):
    hashes = _seed(pool, chain, 2)
    pool.peek_reserve(chain, owner_id="a", height=10)
    # remove(tx_hash, chain_id): the lifecycle suite called remove(chain, hash) and never got here.
    assert pool.remove(hashes[0], chain_id=chain) is False
    assert pool.size(chain_id=chain) == 2
    pool.release_owner_reservations(chain, "a", "cancelled")
    assert pool.remove(hashes[0], chain_id=chain) is True
    assert pool.size(chain_id=chain) == 1


def test_expired_marker_no_longer_protects_row(pool, chain):
    hashes = _seed(pool, chain, 1)
    pool.peek_reserve(chain, owner_id="a", height=10, ttl_seconds=0.01)
    time.sleep(0.05)
    assert pool.remove(hashes[0], chain_id=chain) is True


def test_reconcile_sealed_clears_markers_of_sealed_rows(pool, chain):
    hashes = _seed(pool, chain, 3)
    pool.peek_reserve(chain, owner_id="a", height=10)
    pool.reconcile_sealed(chain, hashes[:2])
    live = pool.live_reservations(chain)
    assert set(live) == {hashes[2]}  # sealed rows' markers are released, not left dangling
    state = _state(pool, chain)
    assert state[hashes[0]][1:] == ("released", "sealed_reconciled")
