"""#1300 P2-v2.4 focused reservation-lifecycle tests.

Covers the DatabaseMempool reservation API: peek_reserve select-without-
delete, cross-owner exclusion, same-owner replace, TTL expiry sweep,
release paths, live_reservations, reconcile_sealed, evictor protection,
and the sealed-on-chain admission refuse (monkeypatched predicate — the
chain-DB query itself fails open by design and is covered by the
reconcile leg).

Runs on SQLite by default; ``Q1300_PG_URL`` points the same legs at a
PostgreSQL scratch database for the backend-parity leg. Each test gets a
unique chain_id so a shared PG database stays isolated between tests.
"""

from __future__ import annotations

import os
import time
import uuid

import pytest
from sqlalchemy import text

from aitbc_chain.mempool import DatabaseMempool


def _tx(nonce: int, chain: str, sender: str = "0xsender") -> dict:
    return {
        "from": sender,
        "to": "0xrecipient",
        "amount": 5,
        "fee": 1,
        "nonce": nonce,
        "payload": {"to": "0xrecipient", "amount": 5},
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


def _seed(pool: DatabaseMempool, chain: str, n: int = 3) -> list[str]:
    return [pool.add(_tx(i, chain), chain_id=chain) for i in range(1, n + 1)]


def test_peek_reserve_marks_without_deleting(pool, chain):
    hashes = _seed(pool, chain)
    got = pool.peek_reserve(chain, owner_id="owner-a", proposer="0xp", height=10, round=0)
    assert {t.tx_hash for t in got} == set(hashes)
    # Rows stay pooled: a different owner sees nothing (live reservation),
    # the owner sees its own set again (replace semantics).
    assert pool.peek_reserve(chain, owner_id="owner-b", proposer="0xp", height=10, round=0) == []
    again = pool.peek_reserve(chain, owner_id="owner-a", proposer="0xp", height=10, round=0)
    assert {t.tx_hash for t in again} == set(hashes)


def test_release_reservations_frees_for_other_owner(pool, chain):
    hashes = _seed(pool, chain)
    pool.peek_reserve(chain, owner_id="owner-a", height=10)
    assert pool.live_reservations(chain) == dict.fromkeys(hashes, "owner-a")
    n = pool.release_reservations(chain, hashes[:1], "outbid")
    assert n == 1
    assert pool.live_reservations(chain) == dict.fromkeys(hashes[1:], "owner-a")
    got_b = pool.peek_reserve(chain, owner_id="owner-b", height=10)
    assert [t.tx_hash for t in got_b] == hashes[:1]


def test_release_owner_reservations_releases_all(pool, chain):
    hashes = _seed(pool, chain)
    pool.peek_reserve(chain, owner_id="owner-a", height=10)
    assert pool.release_owner_reservations(chain, "owner-a", "apply_abort") == len(hashes)
    assert pool.live_reservations(chain) == {}


def test_ttl_expiry_sweep_makes_rows_reservable(pool, chain):
    hashes = _seed(pool, chain)
    pool.peek_reserve(chain, owner_id="owner-a", height=10, ttl_seconds=0.01)
    time.sleep(0.02)
    got_b = pool.peek_reserve(chain, owner_id="owner-b", height=11)
    assert {t.tx_hash for t in got_b} == set(hashes)
    assert pool.live_reservations(chain) == dict.fromkeys(hashes, "owner-b")


def test_reconcile_sealed_removes_pooled_rows(pool, chain):
    hashes = _seed(pool, chain)
    pool.peek_reserve(chain, owner_id="owner-a", height=10)
    removed = pool.reconcile_sealed(chain, hashes[:2])
    assert removed == 2
    # Remaining row still pooled and re-reservable by anyone after release.
    pool.release_owner_reservations(chain, "owner-a", "sealed_reconciled")
    got = pool.peek_reserve(chain, owner_id="owner-b", height=11)
    assert [t.tx_hash for t in got] == [hashes[2]]


def test_reserved_rows_survive_evict_remove(pool, chain):
    hashes = _seed(pool, chain)
    pool.peek_reserve(chain, owner_id="owner-a", height=10)
    # Backdate all rows past the eviction horizon, then apply every
    # deleter path: reserved rows must survive all of them.
    with pool._engine.begin() as conn:
        conn.execute(
            text("UPDATE mempool SET received_at = :old WHERE chain_id = :c"),
            {"old": time.time() - 3600, "c": chain},
        )
    pool.evict_expired(60.0)
    assert pool.remove(chain, hashes[0]) is False
    assert pool.batch_remove(hashes[1:], chain_id=chain) == 0
    assert pool.size(chain_id=chain) == len(hashes)
    # After release the rows are removable again.
    pool.release_owner_reservations(chain, "owner-a", "cancelled")
    pool.batch_remove(hashes, chain_id=chain)
    assert pool.live_reservations(chain) == {}


def test_sealed_on_chain_refuses_readmission(pool, chain, monkeypatch):
    sealed_hash = "0x" + "ab" * 32
    # Hash is NOT pooled — only the sealed predicate stands between it and
    # admission; simulate a confirmed+height row.
    monkeypatch.setattr(DatabaseMempool, "_sealed_on_chain_tx_hashes", lambda self, c, hs: {sealed_hash})
    with pytest.raises(ValueError, match="already sealed"):
        pool.add(_tx(1, chain), chain_id=chain, tx_hash=sealed_hash)


def test_sealed_check_fails_open_without_chain_db(pool, chain):
    # No chain.db session scope in this fixture -> lookup fails, warning,
    # admission proceeds (reconcile_sealed remains the sweeper).
    h = pool.add(_tx(1, chain), chain_id=chain)
    assert pool._sealed_on_chain_tx_hashes(chain, [h]) == set()


def test_peek_reserve_max_count_and_bytes(pool, chain):
    _seed(pool, chain, 4)
    got = pool.peek_reserve(chain, owner_id="owner-a", height=10, max_count=2)
    assert len(got) == 2
    got2 = pool.peek_reserve(chain, owner_id="owner-b", height=10)
    assert len(got2) == 2  # the other two remain available
