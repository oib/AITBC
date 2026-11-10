"""PI-EX-001 (#1176): pagination bounds on every public explorer endpoint.

FastAPI ``int`` parameters accept negatives and arbitrarily large values;
SQLite treats ``LIMIT -1`` as unlimited and a huge ``LIMIT``/``OFFSET`` turns
a bounded query into a full-table dump plus per-row fan-out. Every
client-supplied ``limit``/``offset``/``days`` must be clamped or rejected
before it reaches SQL or an upstream RPC parameter.

The DB-backed tests build a real sqlite chain.db in ``tmp_path`` and
monkeypatch ``chain_db_path`` (the single lookup point added for this fix)
so the actual SQL LIMIT/OFFSET values are exercised, not just the helpers.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from main import app


@pytest.fixture()
def client():
    return TestClient(app)


# --- helper units -----------------------------------------------------------


def test_clamp_page_limit_bounds():
    from validation import MAX_PAGE_LIMIT, clamp_page_limit

    assert clamp_page_limit(0) == 1
    assert clamp_page_limit(-1) == 1
    assert clamp_page_limit(-(10**9)) == 1
    assert clamp_page_limit(1) == 1
    assert clamp_page_limit(50) == 50
    assert clamp_page_limit(MAX_PAGE_LIMIT) == MAX_PAGE_LIMIT
    assert clamp_page_limit(10**9) == MAX_PAGE_LIMIT
    assert clamp_page_limit(10**18) == MAX_PAGE_LIMIT


def test_check_page_offset_bounds():
    import fastapi

    from validation import MAX_PAGE_OFFSET, check_page_offset

    assert check_page_offset(0) == 0
    assert check_page_offset(5000) == 5000
    assert check_page_offset(MAX_PAGE_OFFSET) == MAX_PAGE_OFFSET
    for bad in (-1, -100, MAX_PAGE_OFFSET + 1, 10**9):
        with pytest.raises(fastapi.HTTPException) as exc:
            check_page_offset(bad)
        assert exc.value.status_code == 400


def test_clamp_analytics_days_bounds():
    from validation import MAX_ANALYTICS_DAYS, clamp_analytics_days

    assert clamp_analytics_days(-5) == 1
    assert clamp_analytics_days(0) == 1
    assert clamp_analytics_days(30) == 30
    assert clamp_analytics_days(MAX_ANALYTICS_DAYS) == MAX_ANALYTICS_DAYS
    assert clamp_analytics_days(10**9) == MAX_ANALYTICS_DAYS


# --- DB fixture -------------------------------------------------------------


@pytest.fixture()
def chain_db(tmp_path, monkeypatch):
    """Real sqlite chain.db + monkeypatched lookup for every consumer."""
    db_file = tmp_path / "chain.db"
    conn = sqlite3.connect(db_file)
    conn.execute(
        """CREATE TABLE block (
            height INTEGER, hash TEXT, proposer TEXT, timestamp TEXT,
            tx_count INTEGER, state_root TEXT
        )"""
    )
    conn.execute(
        """CREATE TABLE "transaction" (
            tx_hash TEXT, sender TEXT, recipient TEXT, payload TEXT,
            block_height INTEGER, created_at TEXT, type TEXT, status TEXT,
            value INTEGER, fee INTEGER, nonce INTEGER
        )"""
    )
    conn.commit()
    conn.close()

    import chain_client
    import routers.analytics as analytics_router
    import routers.blocks as blocks_router
    import routers.transactions as transactions_router

    for module in (chain_client, analytics_router, blocks_router, transactions_router):
        monkeypatch.setattr(module, "chain_db_path", lambda: db_file)
    return db_file


def _insert_blocks(db_file: Path, count: int, *, with_txs: bool = False) -> None:
    conn = sqlite3.connect(db_file)
    for i in range(1, count + 1):
        conn.execute(
            "INSERT INTO block VALUES (?,?,?,?,?,?)",
            (i, f"0x{i:064x}", "0xproposer", f"2026-01-01 00:{i // 60:02d}:{i % 60:02d}", 1 if with_txs else 0, "0xroot"),
        )
        if with_txs:
            conn.execute(
                """INSERT INTO "transaction" VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    f"0x{i:064x}",
                    "0xsender",
                    "0xrecipient",
                    "{}",
                    i,
                    f"2026-01-01 00:{i // 60:02d}:{i % 60:02d}",
                    "TRANSFER",
                    "confirmed",
                    100,
                    1,
                    0,
                ),
            )
    conn.commit()
    conn.close()


# --- endpoint bounds --------------------------------------------------------


def test_latest_blocks_limit_capped_end_to_end(client, chain_db):
    """limit=10**9 must return at most MAX_PAGE_LIMIT rows, not the table."""
    from validation import MAX_PAGE_LIMIT

    _insert_blocks(chain_db, MAX_PAGE_LIMIT + 5)
    resp = client.get("/api/blocks/latest", params={"limit": 10**9})
    assert resp.status_code == 200
    assert len(resp.json()["blocks"]) == MAX_PAGE_LIMIT


def test_latest_blocks_negative_limit_clamped(client, chain_db):
    _insert_blocks(chain_db, 3)
    resp = client.get("/api/blocks/latest", params={"limit": -1})
    assert resp.status_code == 200
    assert len(resp.json()["blocks"]) == 1  # clamped to 1, newest first


@pytest.mark.parametrize("offset", [-1, 10001, 10**9])
def test_latest_blocks_offset_rejected(client, chain_db, offset):
    resp = client.get("/api/blocks/latest", params={"offset": offset})
    assert resp.status_code == 400


def test_non_empty_blocks_limit_capped(client, chain_db):
    from validation import MAX_PAGE_LIMIT

    _insert_blocks(chain_db, MAX_PAGE_LIMIT + 5, with_txs=True)
    resp = client.get("/api/blocks/non-empty", params={"limit": 10**9})
    assert resp.status_code == 200
    assert len(resp.json()["blocks"]) == MAX_PAGE_LIMIT


def test_tx_search_negative_limit_returns_single_row(client, chain_db):
    """SQLite LIMIT -1 would dump every match; the clamp must bound it."""
    _insert_blocks(chain_db, 3, with_txs=True)
    resp = client.get("/api/transactions/search", params={"address": "0xsender", "limit": -1})
    assert resp.status_code == 200
    assert len(resp.json()["transactions"]) == 1


def test_tx_search_huge_limit_capped(client, chain_db):
    from validation import MAX_PAGE_LIMIT

    _insert_blocks(chain_db, MAX_PAGE_LIMIT + 5, with_txs=True)
    resp = client.get("/api/transactions/search", params={"address": "0xsender", "limit": 10**9})
    assert resp.status_code == 200
    assert len(resp.json()["transactions"]) == MAX_PAGE_LIMIT


@pytest.mark.parametrize("offset", [-1, 10001, 999999999])
def test_tx_search_offset_rejected(client, chain_db, offset):
    """/api/transactions/search ignored offset entirely — out-of-range must 400."""
    _insert_blocks(chain_db, 3, with_txs=True)
    resp = client.get("/api/transactions/search", params={"address": "0xsender", "offset": offset})
    assert resp.status_code == 400


def test_tx_search_offset_pages_results(client, chain_db):
    _insert_blocks(chain_db, 5, with_txs=True)
    resp = client.get("/api/transactions/search", params={"address": "0xsender", "limit": 2, "offset": 4})
    assert resp.status_code == 200
    assert len(resp.json()["transactions"]) == 1


def test_blocks_by_address_limit_capped(client, chain_db):
    from validation import MAX_PAGE_LIMIT

    _insert_blocks(chain_db, MAX_PAGE_LIMIT + 5, with_txs=True)
    resp = client.get("/api/blocks/by-address/0xsender", params={"limit": 10**9})
    assert resp.status_code == 200
    assert len(resp.json()["blocks"]) == MAX_PAGE_LIMIT


def test_top_addresses_limit_capped(client, chain_db):
    _insert_blocks(chain_db, 5, with_txs=True)
    resp = client.get("/api/analytics/top-addresses", params={"limit": -1})
    assert resp.status_code == 200
    assert len(resp.json()["addresses"]) == 1


@pytest.mark.parametrize("days", [-100, 0, 10**9])
def test_activity_days_bounded(client, chain_db, days):
    resp = client.get("/api/analytics/activity", params={"days": days})
    assert resp.status_code == 200


def test_alerts_history_limit_bounded(client, monkeypatch, tmp_path):
    monkeypatch.setenv("AITBC_ALERT_LOG", str(tmp_path / "alerts.log"))
    resp = client.get("/api/alerts/history", params={"limit": -1})
    assert resp.status_code == 200


@pytest.mark.parametrize("offset", [-1, 10001])
def test_search_endpoints_offset_rejected(client, offset):
    """Offset bounds fire before any upstream RPC call."""
    assert client.get("/api/search/transactions", params={"offset": offset}).status_code == 400
    assert client.get("/api/search/blocks", params={"offset": offset}).status_code == 400


# --- indexed hash lookups ---------------------------------------------------


def test_tx_by_hash_indexed_fast_path(client, chain_db):
    """Canonical 0x+lowercase storage resolves via the exact-match index path."""
    tx_hash = "0x" + "ab" * 32
    _insert_blocks(chain_db, 1, with_txs=True)
    conn = sqlite3.connect(chain_db)
    conn.execute('UPDATE "transaction" SET tx_hash = ?', (tx_hash,))
    conn.commit()
    conn.close()
    resp = client.get(f"/api/transactions/by-hash/{tx_hash}")
    assert resp.status_code == 200
    assert resp.json()["tx_hash"] == tx_hash


def test_tx_by_hash_noncanonical_falls_back(client, chain_db):
    """A non-canonical stored hash still resolves through the legacy scan."""
    weird = "0x" + "CD" * 32  # uppercase storage
    _insert_blocks(chain_db, 1, with_txs=True)
    conn = sqlite3.connect(chain_db)
    conn.execute('UPDATE "transaction" SET tx_hash = ?', (weird,))
    conn.commit()
    conn.close()
    resp = client.get(f"/api/transactions/by-hash/{weird.lower()}")
    assert resp.status_code == 200
    assert resp.json()["tx_hash"] == weird


def test_block_by_hash_indexed_fast_path(client, chain_db):
    block_hash = "0x" + "ef" * 32
    _insert_blocks(chain_db, 1)
    conn = sqlite3.connect(chain_db)
    conn.execute("UPDATE block SET hash = ? WHERE height = 1", (block_hash,))
    conn.commit()
    conn.close()
    resp = client.get(f"/api/blocks/by-hash/{block_hash}")
    assert resp.status_code == 200
    assert resp.json()["hash"] == block_hash
