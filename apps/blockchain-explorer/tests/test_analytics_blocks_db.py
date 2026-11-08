"""Analytics + blocks DB-heavy paths and overview RPC fallback."""

from __future__ import annotations

import asyncio
import sqlite3
from datetime import UTC, datetime, timedelta
from urllib.parse import quote

import httpx
import pytest
from fastapi.testclient import TestClient

from chain_db_fixture import create_chain_db, insert_blocks, patch_chain_db
from main import app
from routers import analytics
import routers.analytics as analytics_router
import routers.blocks as blocks_router


@pytest.fixture
def client():
    return TestClient(app)


def test_activity_timeline_unknown_type_gets_hsl_color(monkeypatch, tmp_path):
    db = create_chain_db(tmp_path)
    patch_chain_db(monkeypatch, db)
    now = datetime.now(UTC).replace(tzinfo=None).strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect(db)
    conn.execute(
        'INSERT INTO "transaction" VALUES (?,?,?,?,?,?,?,?,?,?,?)',
        (
            "0xcustom",
            "0xs",
            "0xr",
            "{}",
            1,
            now,
            "CUSTOM_TEST_TYPE",
            "confirmed",
            0,
            0,
            0,
        ),
    )
    conn.commit()
    conn.close()

    out = asyncio.run(analytics.api_activity_timeline(days=7))
    assert out["labels"]
    dataset = out["datasets"][0]
    assert dataset["label"] == "CUSTOM_TEST_TYPE"
    assert dataset["backgroundColor"].startswith("hsl(")


def test_provider_reputation_score_levels(monkeypatch, tmp_path):
    db = create_chain_db(tmp_path)
    patch_chain_db(monkeypatch, db)
    conn = sqlite3.connect(db)
    first = (datetime.now(UTC).replace(tzinfo=None) - timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
    for i in range(5):
        conn.execute(
            'INSERT INTO "transaction" VALUES (?,?,?,?,?,?,?,?,?,?,?)',
            (f"0x{i:064x}", "0xprov", "0xr", "{}", 1, first, "GPU_MARKET", "confirmed", 36_000_000, 0, i),
        )
    conn.commit()
    conn.close()

    out = asyncio.run(analytics.api_provider_reputation("0xprov"))
    assert out["transactions"] == 5
    assert out["gpu_offers"] == 5
    assert out["level"] in ("Established", "Trusted", "Elite")
    assert out["total_volume"] >= 1.0


def test_analytics_overview_rpc_404_via_client(client, monkeypatch):
    """501 intent when RPC has no overview is wrapped as 500 by the outer handler."""
    monkeypatch.setattr(analytics_router, "USE_DATA_LAYER", False)

    class FakeResponse:
        status_code = 404
        text = "n/a"

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def get(self, url, params=None):
            return FakeResponse()

    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: FakeClient())
    resp = client.get("/api/analytics/overview")
    assert resp.status_code == 500


def test_block_by_height_includes_transactions(client, monkeypatch, tmp_path):
    db = create_chain_db(tmp_path)
    insert_blocks(db, 1, with_txs=True)
    patch_chain_db(monkeypatch, db)
    resp = client.get("/api/blocks/1")
    assert resp.status_code == 200
    body = resp.json()
    assert body["height"] == 1
    assert len(body["transactions"]) == 1


def test_non_empty_blocks_include_nested_tx_rows(client, monkeypatch, tmp_path):
    db = create_chain_db(tmp_path)
    insert_blocks(db, 2, with_txs=True)
    patch_chain_db(monkeypatch, db)
    resp = client.get("/api/blocks/non-empty", params={"limit": 5})
    assert resp.status_code == 200
    blocks = resp.json()["blocks"]
    assert len(blocks) == 2
    assert blocks[0]["transactions"][0]["tx_hash"]


def test_blocks_by_address_like_escape(client, monkeypatch, tmp_path):
    db = create_chain_db(tmp_path)
    insert_blocks(db, 1, with_txs=True)
    conn = sqlite3.connect(db)
    conn.execute('UPDATE "transaction" SET sender = ?', ("0xweird_addr",))
    conn.commit()
    conn.close()
    patch_chain_db(monkeypatch, db)

    address = "0xweird_addr"
    resp = client.get(f"/api/blocks/by-address/{quote(address, safe='')}")
    assert resp.status_code == 200
    assert len(resp.json()["blocks"]) == 1


def test_block_by_hash_rpc_scan_finds_match(monkeypatch):
    monkeypatch.setattr(blocks_router, "chain_db_path", lambda: None)
    target_hash = "0x" + "bb" * 32

    class FakeResponse:
        def __init__(self, status, payload):
            self.status_code = status
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
                return FakeResponse(200, {"height": 100, "hash": "0xother"})
            if url.endswith("/rpc/blocks-range"):
                return FakeResponse(200, {"blocks": [{"height": 99, "hash": target_hash, "tx_count": 0}]})
            return FakeResponse(404, {})

    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: FakeClient())
    out = asyncio.run(blocks_router.api_block_by_hash(target_hash))
    assert out["hash"] == target_hash
