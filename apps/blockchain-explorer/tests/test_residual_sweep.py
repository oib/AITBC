"""TASK BATCH v1 defect-sweep residuals for blockchain-explorer.

Covers #1490 (EXPLORER-QUERY-1 unbounded analytics reads), #1491
(EXPLORER-LOG-1 unbounded alert-log read), #1492 (EXPLORER-RESP-1 per-block
transaction fan-out) and #1493 (EXPLORER-VALID-1 missing tx-hash validation
on the RPC fallback path).
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import chain_client
import routers.alerts as alerts_mod
import routers.analytics as analytics_router
import routers.blocks as blocks_router
from main import app
from chain_db_fixture import create_chain_db, patch_chain_db


@pytest.fixture()
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def reset_alert_caches():
    alerts_mod._events_cache = None
    alerts_mod._alerts_live_cache = None
    yield
    alerts_mod._events_cache = None
    alerts_mod._alerts_live_cache = None


def _insert_txs(db_file: Path, block_height: int, count: int) -> None:
    conn = sqlite3.connect(db_file)
    for i in range(count):
        conn.execute(
            """INSERT INTO "transaction" VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                f"0x{block_height:02d}{i:062x}",
                "0xsender",
                "0xrecipient",
                "{}",
                block_height,
                f"2026-01-01 00:00:{i:02d}",
                "TRANSFER",
                "confirmed",
                36_000_000,
                1,
                i,
            ),
        )
    conn.commit()
    conn.close()


# --- EXPLORER-VALID-1 (#1493) ---


@pytest.mark.parametrize("bad", ["../rpc/head", "abc?x=1", "not-a-hash", "0x" + "g" * 64, "a" * 63])
def test_get_transaction_rejects_invalid_hash(bad: str) -> None:
    """Invalid hashes must not reach the RPC fallback URL path."""
    out = asyncio.run(chain_client.get_transaction(bad))
    assert out == {}


def test_get_transaction_valid_hash_still_works(monkeypatch, tmp_path):
    db = create_chain_db(tmp_path)
    tx_hash = "0x" + "ab" * 32
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO block VALUES (1, '0x'||printf('%064d',0), 'p', 't', 1, 'r')",
    )
    conn.execute(
        """INSERT INTO "transaction" VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (tx_hash, "0xs", "0xr", "{}", 1, "2026-01-01", "TRANSFER", "confirmed", 1, 0, 0),
    )
    conn.commit()
    conn.close()
    patch_chain_db(monkeypatch, db)
    out = asyncio.run(chain_client.get_transaction(tx_hash))
    assert out["tx_hash"] == tx_hash


# --- EXPLORER-RESP-1 (#1492) ---


def _cap3(monkeypatch) -> None:
    for module in (chain_client, blocks_router):
        monkeypatch.setattr(module, "MAX_EMBEDDED_TXS_PER_BLOCK", 3)


def test_latest_blocks_caps_embedded_transactions(monkeypatch, tmp_path):
    db = create_chain_db(tmp_path)
    conn = sqlite3.connect(db)
    conn.execute("INSERT INTO block VALUES (1, '0xh', 'p', 't', 5, 'r')")
    conn.commit()
    conn.close()
    _insert_txs(db, 1, 5)
    patch_chain_db(monkeypatch, db)
    _cap3(monkeypatch)

    blocks = asyncio.run(chain_client.get_latest_blocks(10))
    assert len(blocks) == 1
    assert len(blocks[0]["transactions"]) == 3
    assert blocks[0]["transactions_truncated"] is True


def test_block_by_height_endpoint_caps_transactions(client, monkeypatch, tmp_path):
    db = create_chain_db(tmp_path)
    conn = sqlite3.connect(db)
    conn.execute("INSERT INTO block VALUES (1, '0xh', 'p', 't', 5, 'r')")
    conn.commit()
    conn.close()
    _insert_txs(db, 1, 5)
    patch_chain_db(monkeypatch, db)
    _cap3(monkeypatch)

    resp = client.get("/api/blocks/1")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["transactions"]) == 3
    assert body["transactions_truncated"] is True


def test_non_empty_blocks_caps_transactions(client, monkeypatch, tmp_path):
    db = create_chain_db(tmp_path)
    conn = sqlite3.connect(db)
    conn.execute("INSERT INTO block VALUES (1, '0xh', 'p', 't', 5, 'r')")
    conn.commit()
    conn.close()
    _insert_txs(db, 1, 5)
    patch_chain_db(monkeypatch, db)
    _cap3(monkeypatch)

    resp = client.get("/api/blocks/non-empty")
    assert resp.status_code == 200
    block = resp.json()["blocks"][0]
    assert len(block["transactions"]) == 3
    assert block["transactions_truncated"] is True


def test_untruncated_block_reports_false(client, monkeypatch, tmp_path):
    db = create_chain_db(tmp_path)
    conn = sqlite3.connect(db)
    conn.execute("INSERT INTO block VALUES (1, '0xh', 'p', 't', 1, 'r')")
    conn.commit()
    conn.close()
    _insert_txs(db, 1, 1)
    patch_chain_db(monkeypatch, db)

    resp = client.get("/api/blocks/1")
    assert resp.json()["transactions_truncated"] is False


# --- EXPLORER-QUERY-1 (#1490) ---


def test_network_stats_provider_extraction_in_sql(client, monkeypatch, tmp_path):
    """Provider ids come from a DISTINCT json_extract query; malformed payloads
    must not fail the endpoint (json_valid guard)."""
    db = create_chain_db(tmp_path)
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE account (chain_id VARCHAR, address VARCHAR, balance BIGINT, nonce BIGINT, updated_at DATETIME)")
    conn.execute("INSERT INTO block VALUES (1, '0xh', 'p', 't', 3, 'r')")
    rows = [
        ("0xt1", "0xs", "0xr", '{"provider_address": "0xprov1"}', 1, "GPU_MARKET"),
        ("0xt2", "0xs", "0xr", '{"provider_node_id": "node-7"}', 1, "GPU_REGISTER"),
        ("0xt3", "0xs", "0xr", "not-json{{{", 1, "GPU_MARKET"),  # malformed: skipped, not fatal
    ]
    for tx_hash, sender, recipient, payload, height, ttype in rows:
        conn.execute(
            'INSERT INTO "transaction" VALUES (?,?,?,?,?,?,?,?,?,?,?)',
            (tx_hash, sender, recipient, payload, height, "2026-01-01", ttype, "confirmed", 0, 0, 0),
        )
    conn.commit()
    conn.close()
    patch_chain_db(monkeypatch, db)

    stats = asyncio.run(analytics_router.api_network_stats())
    assert stats["unique_providers"] == 2


def test_provider_reputation_uses_sql_aggregates(client, monkeypatch, tmp_path):
    db = create_chain_db(tmp_path)
    conn = sqlite3.connect(db)
    conn.execute("INSERT INTO block VALUES (1, '0xh', 'p', 't', 2, 'r')")
    for i, ttype in enumerate(["GPU_MARKET", "TRANSFER"]):
        conn.execute(
            'INSERT INTO "transaction" VALUES (?,?,?,?,?,?,?,?,?,?,?)',
            (f"0xt{i}", "0xprov", "0xr", "{}", 1, "2026-01-01", ttype, "confirmed", 36_000_000, 0, i),
        )
    conn.commit()
    conn.close()
    patch_chain_db(monkeypatch, db)

    out = asyncio.run(analytics_router.api_provider_reputation("0xprov"))
    assert out["transactions"] == 2
    assert out["gpu_offers"] == 1
    assert out["total_volume"] == pytest.approx(2.0)


# --- EXPLORER-LOG-1 (#1491) ---


def test_read_events_is_tail_bounded(tmp_path, monkeypatch):
    log = tmp_path / "alerts.log"
    monkeypatch.setenv("AITBC_ALERT_LOG", str(log))
    # Small window: only the newest records survive.
    monkeypatch.setattr(alerts_mod, "_MAX_LOG_READ_BYTES", 400)

    old = {"event": "prometheus_alert_firing", "alertname": "OldAlert", "labels": {}}
    new = {"event": "prometheus_alert_firing", "alertname": "NewAlert", "labels": {}}
    filler = [{"event": "prometheus_alert_still_firing", "alertname": f"F{i}", "labels": {}} for i in range(30)]
    log.write_text("\n".join(json.dumps(r) for r in [old, *filler, new]) + "\n")

    events = alerts_mod._read_events()
    names = {e.get("alertname") for e in events}
    assert "OldAlert" not in names
    assert "NewAlert" in names


def test_read_events_small_file_reads_everything(tmp_path, monkeypatch):
    log = tmp_path / "alerts.log"
    monkeypatch.setenv("AITBC_ALERT_LOG", str(log))
    rec = {"event": "prometheus_alert_firing", "alertname": "A", "labels": {}}
    log.write_text(json.dumps(rec) + "\n")
    assert [e["alertname"] for e in alerts_mod._read_events()] == ["A"]
