"""Tests for GET /rpc/bridge/transfers — the public explorer listing.

The endpoint backs website/bridges.html: it must return persisted
``cross_chain_transfer`` rows across all statuses (not just in-memory
pending) with pagination, and reject invalid status filters.
"""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from datetime import UTC, datetime

import pytest
from fastapi import HTTPException

from aitbc_chain.base_models import CrossChainTransfer
from aitbc_chain.rpc.bridge import list_bridge_transfers


@pytest.fixture(autouse=True)
def _no_rate_limit(monkeypatch) -> None:
    monkeypatch.setenv("AITBC_ENABLE_RATE_LIMITING", "false")


@pytest.fixture(name="patched_db")
def patched_db_fixture(session, monkeypatch):
    """Point the handler's session_scope at the in-memory test session."""

    @contextmanager
    def _fake_scope(chain_id: str = ""):
        yield session

    monkeypatch.setattr("aitbc_chain.database.session_scope", _fake_scope)
    return session


def _transfer(tid: str, status: str = "locked", lock_time: datetime | None = None) -> CrossChainTransfer:
    return CrossChainTransfer(
        transfer_id=tid,
        source_chain="ait-testnet",
        target_chain="sepolia",
        sender="0xSENDER",
        recipient="0xRECIPIENT",
        amount=36_000_000,
        asset="native",
        status=status,
        lock_time=lock_time,
    )


def test_lists_all_statuses(patched_db):
    patched_db.add(_transfer("0xaaa", "locked", datetime(2026, 9, 1, tzinfo=UTC)))
    patched_db.add(_transfer("0xbbb", "refunded", datetime(2026, 9, 2, tzinfo=UTC)))
    patched_db.add(_transfer("0xccc", "pending", None))
    patched_db.commit()

    result = asyncio.run(list_bridge_transfers(None, "test-chain"))
    assert result["total"] == 3
    assert result["count"] == 3
    ids = [t["transfer_id"] for t in result["transfers"]]
    # newest lock_time first; NULL lock_time (pending) sinks last on DESC
    assert ids[:2] == ["0xbbb", "0xaaa"]
    assert ids[2] == "0xccc"


def test_status_filter_and_bad_status(patched_db):
    patched_db.add(_transfer("0xaaa", "completed", datetime(2026, 9, 1, tzinfo=UTC)))
    patched_db.add(_transfer("0xbbb", "locked", datetime(2026, 9, 2, tzinfo=UTC)))
    patched_db.commit()

    result = asyncio.run(list_bridge_transfers(None, "test-chain", status="completed"))
    assert result["total"] == 1
    assert result["transfers"][0]["status"] == "completed"
    assert result["transfers"][0]["amount"] == 36_000_000

    with pytest.raises(HTTPException) as exc:
        asyncio.run(list_bridge_transfers(None, "test-chain", status="bogus"))
    assert exc.value.status_code == 400


def test_limit_and_offset(patched_db):
    for i in range(5):
        patched_db.add(_transfer(f"0x{i:03x}", "locked", datetime(2026, 9, 1, i, tzinfo=UTC)))
    patched_db.commit()

    page1 = asyncio.run(list_bridge_transfers(None, "test-chain", limit=2))
    page2 = asyncio.run(list_bridge_transfers(None, "test-chain", limit=2, offset=2))
    assert page1["total"] == 5 and page1["count"] == 2
    assert page2["count"] == 2
    assert page1["transfers"][0]["transfer_id"] != page2["transfers"][0]["transfer_id"]

    capped = asyncio.run(list_bridge_transfers(None, "test-chain", limit=9999))
    assert capped["limit"] == 200


def test_empty_table(patched_db):
    result = asyncio.run(list_bridge_transfers(None, "test-chain"))
    assert result["total"] == 0
    assert result["transfers"] == []
