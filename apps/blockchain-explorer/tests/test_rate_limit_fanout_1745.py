"""EXPLORER-DEEP2-1 (#1745): in-app rate limit + batched embedded-tx fetch.

Two regressions pinned here:

- Every explorer read endpoint was unauthenticated with no request-rate
  bound; ``RateLimitMiddleware`` now caps per-client-IP request rate
  (``EXPLORER_RATE_LIMIT``, pinned to ``5/minute`` by conftest).
- ``/api/blocks/latest`` and ``/api/blocks/non-empty`` ran one transaction
  query per block (N+1, ~40k embedded tx rows worst case). They now go
  through ``chain_client.get_block_transactions_batch`` — ONE ``IN ()``
  query per page with the same per-block cap and truncation sentinel.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import chain_client
import routers.blocks as blocks_router
from chain_db_fixture import create_chain_db, insert_blocks, patch_chain_db
from main import app
from validation import MAX_EMBEDDED_TXS_PER_BLOCK


@pytest.fixture()
def client():
    return TestClient(app)


# --- rate limit -------------------------------------------------------------


def test_rate_limit_trips_after_budget(client, monkeypatch):
    """The 6th request inside the window answers 429; earlier ones pass."""
    monkeypatch.setenv("AITBC_ENABLE_RATE_LIMITING", "true")
    codes = [client.get("/api/chains").status_code for _ in range(6)]
    assert codes[:5] == [200] * 5
    assert codes[5] == 429


def test_health_endpoint_exempt_from_rate_limit(client, monkeypatch):
    """Probes must not trip the limiter — /health stays exempt."""
    monkeypatch.setenv("AITBC_ENABLE_RATE_LIMITING", "true")
    for _ in range(6):
        client.get("/api/chains")
    assert client.get("/health").status_code == 200


# --- batched fan-out --------------------------------------------------------


def _insert_txs(db_file: Path, height: int, count: int, *, prefix: str = "tx") -> None:
    conn = sqlite3.connect(db_file)
    for i in range(count):
        conn.execute(
            """INSERT INTO "transaction" VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                f"0x{prefix}{height:03d}{i:04d}",
                "0xsender",
                "0xrecipient",
                "{}",
                height,
                f"2026-01-01 00:{i // 60:02d}:{i % 60:02d}.{i:06d}",
                "TRANSFER",
                "confirmed",
                100,
                1,
                i,
            ),
        )
    conn.commit()
    conn.close()


def test_latest_blocks_uses_single_batched_tx_query(client, monkeypatch, tmp_path):
    """A 10-block page must cost ONE batched tx fetch, not ten queries."""
    db = create_chain_db(tmp_path)
    insert_blocks(db, 10, with_txs=True)
    patch_chain_db(monkeypatch, db)

    calls: list[int] = []

    async def spy(conn, chain_id, heights):
        heights = list(heights)
        calls.append(len(heights))
        return await _orig_batch(conn, chain_id, heights)

    _orig_batch = chain_client.get_block_transactions_batch
    monkeypatch.setattr(chain_client, "get_block_transactions_batch", spy)

    resp = client.get("/api/blocks/latest", params={"limit": 10})
    assert resp.status_code == 200
    assert calls == [10]
    assert len(resp.json()["blocks"]) == 10


def test_non_empty_blocks_uses_single_batched_tx_query(client, monkeypatch, tmp_path):
    db = create_chain_db(tmp_path)
    insert_blocks(db, 10, with_txs=True)
    patch_chain_db(monkeypatch, db)

    calls: list[int] = []

    async def spy(conn, chain_id, heights):
        heights = list(heights)
        calls.append(len(heights))
        return await _orig_batch(conn, chain_id, heights)

    _orig_batch = chain_client.get_block_transactions_batch
    monkeypatch.setattr(blocks_router, "get_block_transactions_batch", spy)

    resp = client.get("/api/blocks/non-empty", params={"limit": 10})
    assert resp.status_code == 200
    assert calls == [10]


async def test_batch_helper_bounds_per_block_and_orders(tmp_path):
    """The helper caps each block at MAX+1 rows (sentinel) in created_at order."""
    db = create_chain_db(tmp_path)
    insert_blocks(db, 3, with_txs=False)
    _insert_txs(db, 1, 3)
    _insert_txs(db, 3, MAX_EMBEDDED_TXS_PER_BLOCK + 5)

    async with chain_client.chain_db_connect(db) as conn:
        grouped = await chain_client.get_block_transactions_batch(conn, "ait-testchain", [3, 1, 2, 3])

    # Duplicate heights collapse; height 2 has no txs and is absent.
    assert set(grouped) == {1, 3}
    assert len(grouped[1]) == 3
    assert len(grouped[3]) == MAX_EMBEDDED_TXS_PER_BLOCK + 1  # cap+1 sentinel
    # Same column order the per-block queries returned.
    assert grouped[1][0][0].startswith("0xtx001")
    created = [row[6] for row in grouped[3]]
    assert created == sorted(created)


# --- response shape unchanged ------------------------------------------------


def test_latest_blocks_payload_shape_unchanged(client, monkeypatch, tmp_path):
    db = create_chain_db(tmp_path)
    insert_blocks(db, 2, with_txs=True)
    patch_chain_db(monkeypatch, db)

    resp = client.get("/api/blocks/latest", params={"limit": 5})
    assert resp.status_code == 200
    block = resp.json()["blocks"][0]
    assert set(block) == {
        "height",
        "hash",
        "proposer",
        "timestamp",
        "txCount",
        "stateRoot",
        "transactions",
        "transactions_truncated",
    }
    tx = block["transactions"][0]
    assert set(tx) == {
        "tx_hash",
        "sender",
        "recipient",
        "payload",
        "amount",
        "amount_ait",
        "fee",
        "fee_ait",
        "nonce",
        "type",
        "status",
        "created_at",
    }


def test_non_empty_blocks_payload_shape_unchanged(client, monkeypatch, tmp_path):
    """non-empty embeds a slimmer tx dict (no *_ait fields) — pin it."""
    db = create_chain_db(tmp_path)
    insert_blocks(db, 1, with_txs=True)
    patch_chain_db(monkeypatch, db)

    resp = client.get("/api/blocks/non-empty", params={"limit": 5})
    assert resp.status_code == 200
    tx = resp.json()["blocks"][0]["transactions"][0]
    assert set(tx) == {
        "tx_hash",
        "sender",
        "recipient",
        "payload",
        "amount",
        "fee",
        "nonce",
        "type",
        "status",
        "created_at",
    }


def test_truncation_sentinel_survives_batching(client, monkeypatch, tmp_path):
    """A block with > MAX embedded txs still flags transactions_truncated."""
    db = create_chain_db(tmp_path)
    insert_blocks(db, 1, with_txs=False)
    _insert_txs(db, 1, MAX_EMBEDDED_TXS_PER_BLOCK + 1)
    patch_chain_db(monkeypatch, db)

    resp = client.get("/api/blocks/latest", params={"limit": 5})
    assert resp.status_code == 200
    block = resp.json()["blocks"][0]
    assert block["transactions_truncated"] is True
    assert len(block["transactions"]) == MAX_EMBEDDED_TXS_PER_BLOCK
