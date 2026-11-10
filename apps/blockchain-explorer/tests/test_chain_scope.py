"""#1620: every chain.db read is scoped by chain_id.

The fallback ``/var/lib/aitbc/data/chain.db`` is a multi-chain store —
``block``/``transaction``/``account`` rows carry ``chain_id`` and heights,
hashes and addresses collide across chains. These tests build a DB with the
real (multi-chain) columns, plant rows for two chains, and assert the
configured chain's reads never see the foreign chain's rows — both for the
default chain and for an explicit ``chain_id`` argument.

The legacy single-chain shape (no ``chain_id`` column) keeps working
unscoped — that path is covered by the older fixtures in
``chain_db_fixture.py``/``test_pagination_bounds.py``.
"""

from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import chain_client
from aitbc_explorer_main import app
from routers import analytics

_CHAIN = chain_client.default_chain_id()
_FOREIGN = "ait-foreignchain"

MINE_TX = "0x" + "11" * 32
FOREIGN_TX = "0x" + "22" * 32
MINE_BLOCK = "0x" + "33" * 32
FOREIGN_BLOCK = "0x" + "44" * 32
MINE_SENDER = "0xmine_sender"
FOREIGN_SENDER = "0xforeign_sender"


@pytest.fixture()
def client():
    return TestClient(app)


@pytest.fixture(name="chain_db")
def chain_db_fixture(tmp_path: Path, monkeypatch) -> Path:
    db = tmp_path / "chain.db"
    conn = sqlite3.connect(db)
    conn.execute(
        """CREATE TABLE block (
            id INTEGER PRIMARY KEY, chain_id VARCHAR, height INTEGER, hash TEXT,
            proposer TEXT, timestamp TEXT, tx_count INTEGER, state_root TEXT
        )"""
    )
    conn.execute(
        """CREATE TABLE "transaction" (
            id INTEGER PRIMARY KEY, chain_id VARCHAR, tx_hash TEXT, sender TEXT,
            recipient TEXT, payload TEXT, block_height INTEGER, created_at TEXT,
            type TEXT, status TEXT, value INTEGER, fee INTEGER, nonce INTEGER
        )"""
    )
    # Same height on both chains — only chain_id tells the rows apart.
    for chain, tx_hash, block_hash, sender in (
        (_CHAIN, MINE_TX, MINE_BLOCK, MINE_SENDER),
        (_FOREIGN, FOREIGN_TX, FOREIGN_BLOCK, FOREIGN_SENDER),
    ):
        conn.execute(
            "INSERT INTO block (chain_id, height, hash, proposer, timestamp, tx_count, state_root) VALUES (?,?,?,?,?,?,?)",
            (chain, 1, block_hash, "0xproposer", "2026-01-01 00:00:01", 1, "0xroot"),
        )
        conn.execute(
            """INSERT INTO "transaction"
               (chain_id, tx_hash, sender, recipient, payload, block_height, created_at, type, status, value, fee, nonce)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                chain,
                tx_hash,
                sender,
                "0xrecipient",
                "{}",
                1,
                "2026-01-01 00:00:01",
                "TRANSFER",
                "confirmed",
                36_000_000,
                1,
                0,
            ),
        )
    conn.commit()
    conn.close()

    import routers.analytics as analytics_router
    import routers.blocks as blocks_router
    import routers.transactions as transactions_router

    for module in (chain_client, analytics_router, blocks_router, transactions_router):
        monkeypatch.setattr(module, "chain_db_path", lambda: db)
    return db


def test_get_transaction_returns_only_matching_chain(chain_db):
    out = asyncio.run(chain_client.get_transaction(MINE_TX))
    assert out["tx_hash"] == MINE_TX
    assert out["sender"] == MINE_SENDER

    foreign = asyncio.run(chain_client.get_transaction(FOREIGN_TX))
    # Exists on the foreign chain only: the scoped DB read misses and the
    # RPC fallback (unreachable in tests) yields {} — no cross-chain leak.
    assert foreign == {}


def test_get_transaction_explicit_chain_id(chain_db):
    out = asyncio.run(chain_client.get_transaction(FOREIGN_TX, chain_id=_FOREIGN))
    assert out["tx_hash"] == FOREIGN_TX
    assert out["sender"] == FOREIGN_SENDER


def test_get_block_scoped(chain_db):
    block = asyncio.run(chain_client.get_block(1))
    assert block["hash"] == MINE_BLOCK
    assert [t["tx_hash"] for t in block["transactions"]] == [MINE_TX]

    foreign = asyncio.run(chain_client.get_block(1, chain_id=_FOREIGN))
    assert foreign["hash"] == FOREIGN_BLOCK
    assert [t["tx_hash"] for t in foreign["transactions"]] == [FOREIGN_TX]


def test_get_latest_blocks_scoped(chain_db):
    blocks = asyncio.run(chain_client.get_latest_blocks(limit=10))
    assert [b["hash"] for b in blocks] == [MINE_BLOCK]
    assert [t["tx_hash"] for t in blocks[0]["transactions"]] == [MINE_TX]
    blocks = asyncio.run(chain_client.get_latest_blocks(limit=10, chain_id=_FOREIGN))
    assert [b["hash"] for b in blocks] == [FOREIGN_BLOCK]


def test_tx_search_and_by_hash_endpoints_scoped(client, chain_db):
    resp = client.get("/api/transactions/search", params={"address": "sender"})
    assert resp.status_code == 200
    assert {t["tx_hash"] for t in resp.json()["transactions"]} == {MINE_TX}

    resp = client.get("/api/transactions/search", params={"address": "sender", "chain_id": _FOREIGN})
    assert {t["tx_hash"] for t in resp.json()["transactions"]} == {FOREIGN_TX}

    # DB read misses under the local chain; whatever the RPC fallback
    # answers, the foreign chain's row must not come back.
    resp = client.get(f"/api/transactions/by-hash/{FOREIGN_TX}")
    assert resp.json().get("tx_hash") != FOREIGN_TX


def test_blocks_endpoints_scoped(client, chain_db):
    resp = client.get("/api/blocks/latest")
    assert [b["hash"] for b in resp.json()["blocks"]] == [MINE_BLOCK]

    resp = client.get("/api/blocks/non-empty")
    blocks = resp.json()["blocks"]
    assert [b["hash"] for b in blocks] == [MINE_BLOCK]
    assert [t["tx_hash"] for t in blocks[0]["transactions"]] == [MINE_TX]

    resp = client.get(f"/api/blocks/by-address/{MINE_SENDER}")
    assert [b["hash"] for b in resp.json()["blocks"]] == [MINE_BLOCK]

    resp = client.get(f"/api/blocks/by-hash/{FOREIGN_BLOCK}")
    # DB read misses; whatever the RPC fallback answers, the foreign
    # chain's block must not come back.
    assert resp.json().get("hash") != FOREIGN_BLOCK


def test_provider_reputation_scoped(chain_db):
    out = asyncio.run(analytics.api_provider_reputation(MINE_SENDER))
    assert out["transactions"] == 1
    assert out["total_volume"] == 1.0

    out = asyncio.run(analytics.api_provider_reputation(FOREIGN_SENDER))
    assert out["transactions"] == 0  # no cross-chain leak
