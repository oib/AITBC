"""AUDIT-BN-INMEMORY-MEMPOOL-REPLACE-DROPS-OCCUPANT-BEFORE-REFUSAL-1 (#2665):

A higher-fee same-(sender, nonce) replacement dropped the occupant *before*
the stake-release conflict guard (and the full-pool check) could refuse the
newcomer — so a rejected add still evicted the sender's accepted pending
transaction. InMemoryMempool now restores the occupant when a later refusal
raises; DatabaseMempool was already safe because the delete and the raise sit
in one session that is never committed on the error path. These tests pin the
refused-replacement-keeps-occupant behaviour for both pool classes.
"""

from __future__ import annotations

import pytest

from aitbc_chain.mempool import DatabaseMempool, InMemoryMempool

CHAIN = "c2665"
LOCK = "0x" + "aa" * 32


def _release(sender: str, nonce: int, fee: int) -> dict:
    return {
        "from": sender,
        "to": "0xescrow",
        "amount": 0,
        "fee": fee,
        "nonce": nonce,
        "type": "STAKE_RELEASE",
        "payload": {"lock_tx_hashes": [LOCK]},
        "signature": "0xsig",
    }


def _transfer(sender: str, nonce: int, fee: int) -> dict:
    return {
        "from": sender,
        "to": "0xrecipient",
        "amount": 1,
        "fee": fee,
        "nonce": nonce,
        "type": "TRANSFER",
        "payload": {},
        "signature": "0xsig",
    }


def _seed_conflict(pool) -> str:
    """B's pending release claims LOCK; A holds slot (a, 0) with a fee-5 transfer.

    Returns A's occupant tx_hash."""
    pool.add(_release("0xb", 0, 1), chain_id=CHAIN)
    return pool.add(_transfer("0xa", 0, 5), chain_id=CHAIN)


def _assert_occupant_survives(pool, occupant_hash: str) -> None:
    hashes = {t.tx_hash for t in pool.list_transactions(chain_id=CHAIN)}
    assert occupant_hash in hashes
    assert len(hashes) == 2  # B's release + A's occupant; the refused newcomer is absent


def test_in_memory_refused_replacement_keeps_occupant() -> None:
    pool = InMemoryMempool(chain_id=CHAIN)
    occupant_hash = _seed_conflict(pool)

    # A's fee-9 release outbids the fee-5 occupant but collides with B's claim.
    with pytest.raises(ValueError, match="pending release"):
        pool.add(_release("0xa", 0, 9), chain_id=CHAIN)

    _assert_occupant_survives(pool, occupant_hash)


def test_database_refused_replacement_keeps_occupant(tmp_path) -> None:
    pool = DatabaseMempool(f"sqlite:///{tmp_path / 'mempool.db'}")
    occupant_hash = _seed_conflict(pool)

    with pytest.raises(ValueError, match="pending release"):
        pool.add(_release("0xa", 0, 9), chain_id=CHAIN)

    _assert_occupant_survives(pool, occupant_hash)


def test_in_memory_successful_replacement_still_evicticts() -> None:
    """The guard must not break the legitimate path: an outbid replacement
    that claims a *free* lock still evicts the occupant."""
    pool = InMemoryMempool(chain_id=CHAIN)
    _seed_conflict(pool)
    other_lock = "0x" + "bb" * 32
    newcomer = _release("0xa", 0, 9)
    newcomer["payload"] = {"lock_tx_hashes": [other_lock]}

    pool.add(newcomer, chain_id=CHAIN)

    hashes = {t.tx_hash for t in pool.list_transactions(chain_id=CHAIN)}
    assert len(hashes) == 2  # B's release + A's replacement
