"""Followers must evict confirmed transactions from the mempool on block import.

Only proposers drain the mempool (consensus/poa.py). Without eviction on the
import path, every tx a follower ever sees stays until size-cap eviction —
that is how node1 accumulated 11 confirmed-but-stale entries.
"""

from __future__ import annotations

import pytest

from aitbc_chain import mempool as mempool_mod
from aitbc_chain.mempool import compute_tx_hash, init_mempool
from aitbc_chain.sync_block_import import BlockImportMixin


@pytest.fixture
def fresh_mempool():
    init_mempool("memory")
    yield mempool_mod.get_mempool()
    mempool_mod._MEMPOOL = None


def _importer(chain_id: str = "test-chain") -> BlockImportMixin:
    obj = BlockImportMixin.__new__(BlockImportMixin)
    obj._chain_id = chain_id
    return obj


def _tx(nonce: int = 1) -> dict:
    return {
        "from": "0xsender",
        "to": "0xrecipient",
        "amount": 5,
        "fee": 0,
        "nonce": nonce,
        "payload": {"to": "0xrecipient", "amount": 5},
        "type": "TRANSFER",
        "chain_id": "test-chain",
        "signature": "0xsig",
    }


def test_included_tx_is_evicted(fresh_mempool):
    tx = _tx()
    tx_hash = fresh_mempool.add(tx, chain_id="test-chain")
    assert tx_hash == compute_tx_hash(tx)

    # On the wire the tx has no tx_hash field; normalization recomputes it.
    wire_tx = dict(tx, tx_hash=compute_tx_hash(tx))
    _importer()._evict_included_from_mempool([wire_tx])

    assert fresh_mempool.list_transactions("test-chain") == []


def test_unrelated_txs_are_kept(fresh_mempool):
    keep = _tx(nonce=7)
    fresh_mempool.add(keep, chain_id="test-chain")
    fresh_mempool.add(_tx(nonce=8), chain_id="test-chain")

    included = _tx(nonce=8)
    _importer()._evict_included_from_mempool([dict(included, tx_hash=compute_tx_hash(included))])

    remaining = fresh_mempool.list_transactions("test-chain")
    assert len(remaining) == 1
    assert remaining[0].tx_hash == compute_tx_hash(keep)


def test_eviction_failure_never_propagates(fresh_mempool, monkeypatch):
    def _boom(*args, **kwargs):
        raise RuntimeError("mempool exploded")

    monkeypatch.setattr(mempool_mod, "get_mempool", _boom)
    # Must not raise — a mempool hiccup cannot fail a committed block import.
    _importer()._evict_included_from_mempool([{"tx_hash": "0xdeadbeef"}])


def test_missing_tx_hash_entries_are_skipped(fresh_mempool):
    tx = _tx()
    fresh_mempool.add(tx, chain_id="test-chain")
    _importer()._evict_included_from_mempool([{"from": "0xsender"}])
    assert len(fresh_mempool.list_transactions("test-chain")) == 1
