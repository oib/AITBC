"""chain_client sqlite reads + RPC fallbacks when no DB is present."""

from __future__ import annotations

import asyncio
import sqlite3

import httpx

import chain_client
from chain_db_fixture import create_chain_db, insert_blocks, patch_chain_db


def test_get_transaction_db_row(monkeypatch, tmp_path):
    db = create_chain_db(tmp_path)
    tx_hash = "0x" + "aa" * 32
    insert_blocks(db, 1, with_txs=True)
    conn = sqlite3.connect(db)
    conn.execute('UPDATE "transaction" SET tx_hash = ?, value = ?', (tx_hash, 72_000_000))
    conn.commit()
    conn.close()
    patch_chain_db(monkeypatch, db)

    out = asyncio.run(chain_client.get_transaction(tx_hash))
    assert out["hash"] == tx_hash
    assert out["from"] == "0xsender"
    assert "AIT" in out["value_ait"]


def test_get_block_db_with_transactions(monkeypatch, tmp_path):
    db = create_chain_db(tmp_path)
    insert_blocks(db, 2, with_txs=True)
    patch_chain_db(monkeypatch, db)

    block = asyncio.run(chain_client.get_block(1))
    assert block["height"] == 1
    assert block["txCount"] == 1
    assert len(block["transactions"]) == 1
    assert block["transactions"][0]["amount_ait"]


def test_get_latest_blocks_orders_newest_first(monkeypatch, tmp_path):
    db = create_chain_db(tmp_path)
    insert_blocks(db, 3, with_txs=True)
    patch_chain_db(monkeypatch, db)

    blocks = asyncio.run(chain_client.get_latest_blocks(limit=2))
    assert [b["height"] for b in blocks] == [3, 2]
    assert blocks[0]["transactions"]


def test_get_block_rpc_fallback(monkeypatch):
    monkeypatch.setattr(chain_client, "chain_db_path", lambda: None)

    class FakeResponse:
        def __init__(self, status_code, payload):
            self.status_code = status_code
            self._payload = payload

        def json(self):
            return self._payload

    calls: list[str] = []

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def get(self, url, params=None):
            calls.append(url)
            if url.endswith("/rpc/blocks/7"):
                return FakeResponse(200, {"height": 7, "proposer": "0xp", "tx_count": 0})
            return FakeResponse(404, {})

    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: FakeClient())
    block = asyncio.run(chain_client.get_block(7))
    assert block["validator"] == "0xp"
    assert any("/rpc/blocks/" in c for c in calls)


def test_get_latest_blocks_rpc_range(monkeypatch):
    monkeypatch.setattr(chain_client, "chain_db_path", lambda: None)

    class FakeResponse:
        def __init__(self, status_code, payload):
            self.status_code = status_code
            self._payload = payload

        def json(self):
            return self._payload

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def get(self, url, params=None):
            if url.endswith("/rpc/head"):
                return FakeResponse(200, {"height": 5})
            if url.endswith("/rpc/blocks-range"):
                return FakeResponse(
                    200,
                    {
                        "blocks": [
                            {"height": 4, "hash": "0x4", "tx_count": 0},
                            {"height": 5, "hash": "0x5", "tx_count": 1},
                        ]
                    },
                )
            return FakeResponse(404, {})

    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: FakeClient())
    blocks = asyncio.run(chain_client.get_latest_blocks(limit=2))
    assert [b["height"] for b in blocks] == [5, 4]


def test_get_latest_blocks_head_zero_returns_empty(monkeypatch):
    monkeypatch.setattr(chain_client, "chain_db_path", lambda: None)

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"height": 0}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def get(self, url, params=None):
            return FakeResponse()

    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: FakeClient())
    assert asyncio.run(chain_client.get_latest_blocks()) == []
