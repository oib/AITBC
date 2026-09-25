"""Tests for block metadata in GET /rpc/transactions results.

The marketplace resolves offer confirmation from these rows and renders
Block Hash / Proposer on offer cards; the endpoint must join the ``block``
table on (chain_id, height) and return both fields alongside block_height.
"""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from datetime import UTC, datetime

import pytest

from aitbc_chain.base_models import Block, Transaction
from aitbc_chain.rpc.transactions import query_transactions


@pytest.fixture(autouse=True)
def _no_rate_limit(monkeypatch) -> None:
    monkeypatch.setenv("AITBC_ENABLE_RATE_LIMITING", "false")


@pytest.fixture(name="patched_db")
def patched_db_fixture(session, monkeypatch):
    """Point the handler's session_scope at the in-memory test session.

    transactions.py binds session_scope at module level, so the patch
    must target the name *in that module*, not aitbc_chain.database.
    """

    @contextmanager
    def _fake_scope(chain_id: str = ""):
        yield session

    monkeypatch.setattr("aitbc_chain.rpc.transactions.session_scope", _fake_scope)
    return session


def _block(chain_id: str, height: int, block_hash: str, proposer: str) -> Block:
    return Block(
        chain_id=chain_id,
        height=height,
        hash=block_hash,
        parent_hash="0xparent",
        proposer=proposer,
        timestamp=datetime(2026, 9, 24, tzinfo=UTC),
    )


def _tx(chain_id: str, tx_hash: str, height: int | None) -> Transaction:
    return Transaction(
        chain_id=chain_id,
        tx_hash=tx_hash,
        block_height=height,
        sender="0xSENDER",
        recipient="0xRECIPIENT",
        payload={"offer_id": "sw_offer_test"},
        type="GPU_MARKET",
        status="confirmed",
    )


def test_block_fields_joined_for_sealed_tx(patched_db):
    patched_db.add(_block("test-chain", 100, "0xblock100", "0xPROPOSER"))
    patched_db.add(_tx("test-chain", "0xtx100", 100))
    patched_db.commit()

    result = asyncio.run(query_transactions(None, chain_id="test-chain"))
    assert len(result) == 1
    tx = result[0]
    assert tx["block_height"] == 100
    assert tx["block_hash"] == "0xblock100"
    assert tx["block_proposer"] == "0xPROPOSER"


def test_unsealed_tx_has_null_block_fields(patched_db):
    patched_db.add(_tx("test-chain", "0xtxmempool", None))
    patched_db.commit()

    result = asyncio.run(query_transactions(None, chain_id="test-chain"))
    assert len(result) == 1
    tx = result[0]
    assert tx["block_height"] is None
    assert tx["block_hash"] is None
    assert tx["block_proposer"] is None


def test_missing_block_row_yields_null_fields(patched_db):
    # Tx points at a height with no block row (corrupt/legacy data) — the
    # join must degrade to nulls, not drop the transaction.
    patched_db.add(_tx("test-chain", "0xtxorphan", 999))
    patched_db.commit()

    result = asyncio.run(query_transactions(None, chain_id="test-chain"))
    assert len(result) == 1
    assert result[0]["block_height"] == 999
    assert result[0]["block_hash"] is None
