"""Tests for GET /api/analytics/network-stats semantics.

total_ait must be circulating supply (account balances converted from base
units), transfer_volume_ait the labeled cumulative volume, and active_offers
the distinct offer anchors across GPU_MARKET/GPU_MARKETPLACE/GPU_REGISTER —
the same keys the marketplace page uses for confirmation.
"""

from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

import pytest

from routers import analytics


@pytest.fixture(name="chain_db")
def chain_db_fixture(tmp_path: Path, monkeypatch) -> Path:
    db = tmp_path / "chain.db"
    conn = sqlite3.connect(db)
    conn.execute(
        'CREATE TABLE account (chain_id VARCHAR NOT NULL, address VARCHAR NOT NULL, balance BIGINT NOT NULL, nonce BIGINT NOT NULL, updated_at DATETIME NOT NULL, PRIMARY KEY (chain_id, address))'
    )
    conn.execute(
        'CREATE TABLE "transaction" (id INTEGER PRIMARY KEY, chain_id VARCHAR, tx_hash VARCHAR, block_height INTEGER, sender VARCHAR, recipient VARCHAR, payload JSON, created_at DATETIME, nonce BIGINT, value BIGINT, fee BIGINT, type VARCHAR, status VARCHAR, timestamp VARCHAR, tx_metadata VARCHAR)'
    )
    conn.executemany(
        "INSERT INTO account (chain_id, address, balance, nonce, updated_at) VALUES ('c', ?, ?, 0, '2026-01-01')",
        # 1 AIT + 2 AIT in base units (36e6 per AIT)
        [("0xaaa", 36_000_000), ("0xbbb", 72_000_000)],
    )
    conn.executemany(
        'INSERT INTO "transaction" (chain_id, tx_hash, sender, recipient, payload, value, type, status) VALUES (\'c\', ?, \'0xs\', \'0xr\', ?, ?, ?, \'confirmed\')',
        [
            ("0xt1", '{"offer_id": "sw_1"}', 0, "GPU_MARKET"),
            ("0xt2", '{"offer_id": "sw_2"}', 0, "GPU_MARKETPLACE"),
            ("0xt3", '{"gpu_id": "gpu-1"}', 0, "GPU_REGISTER"),
            ("0xt4", '{"gpu_id": "gpu-1"}', 0, "GPU_REGISTER"),  # re-register: counts once
            ("0xt5", "{}", 36_000_000, "TRANSFER"),  # 1 AIT volume
        ],
    )
    conn.commit()
    conn.close()
    monkeypatch.setattr(analytics, "_chain_db_path", lambda: db)
    return db


def test_network_stats_supply_and_anchors(chain_db):
    stats = asyncio.run(analytics.api_network_stats())
    assert stats["total_ait"] == 3.0  # 108e6 units / 36e6
    assert stats["transfer_volume_ait"] == 1.0  # 36e6 units / 36e6
    assert stats["active_offers"] == 3  # sw_1, sw_2, gpu-1 (distinct)
    assert stats["total_transactions"] == 5
    assert stats["unique_nodes"] == 1  # one sender
    assert stats["unique_providers"] == 0  # no provider fields in payloads


def test_network_stats_provider_fields(chain_db):
    conn = sqlite3.connect(chain_db)
    conn.execute(
        'INSERT INTO "transaction" (chain_id, tx_hash, sender, recipient, payload, value, type, status) VALUES (\'c\', \'0xt6\', \'0xs\', \'0xr\', \'{"offer_id":"sw_3","provider_address":"0xprov"}\', 0, \'GPU_MARKET\', \'confirmed\')'
    )
    conn.commit()
    conn.close()

    stats = asyncio.run(analytics.api_network_stats())
    assert stats["unique_providers"] == 1
    assert stats["active_offers"] == 4


def test_top_addresses_volume_in_ait(chain_db):
    result = asyncio.run(analytics.api_top_addresses())
    assert len(result["addresses"]) == 1
    # 36e6 base units -> 1.0 AIT
    assert result["addresses"][0]["volume"] == 1.0
