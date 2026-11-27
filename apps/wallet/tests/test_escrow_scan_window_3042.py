"""Pins for AUDIT-BRIDGE-ESCROW-SCAN-WINDOW-1 (#3042).

``/rpc/transactions`` clamps ``limit`` server-side (0/omitted -> newest 100,
max 500 — #1057/#2632). The escrow scan lanes were written against the old
"limit=0 returns complete history" contract, so an unprocessed lock evicted
from the newest-100 window was stranded silently. The fix pages backwards
with ``before_id`` cursors (the withdraw lane's #2918 pattern) until a short
page proves history exhausted.

The fake ``httpx.AsyncClient`` below emulates the *real* server contract:
newest-first ordering, ``id < before_id`` cursor, sender-or-recipient
address match, and the exact ``max(1, min(limit or 100, 500))`` clamp — so
a regression to a single bounded fetch fails these pins the same way it
fails in production.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from wallet_app.bridge import sell_escrow_monitor as sellmon
from wallet_app.bridge.bridge_db import (
    get_sell_lock_by_ait_tx_hash,
    init_db,
)

ESCROW = "0x" + "aa" * 20
SHOP = "0x" + "bb" * 20
TREASURY = "0x" + "cc" * 20


def _tx(transaction_id: int, *, sender: str = SHOP, recipient: str = ESCROW, **over: Any) -> dict[str, Any]:
    tx = {
        "transaction_id": transaction_id,
        "transaction_type": "TRANSFER",
        "tx_hash": f"0x{transaction_id:064x}",
        "sender": sender,
        "recipient": recipient,
        "value": 1_000_000,
        "status": "confirmed",
        "block_height": 100 + transaction_id,
        "payload": {},
    }
    tx.update(over)
    return tx


def _server_slice(txs: list[dict[str, Any]], params: dict[str, Any]) -> list[dict[str, Any]]:
    """Emulate ``/rpc/transactions``: newest-first, address = sender OR
    recipient, ``before_id`` cursor, and the real limit clamp."""
    addr = str(params.get("address") or "").lower()
    rows = [
        t
        for t in txs
        if t.get("transaction_type", "TRANSFER") == "TRANSFER"
        and addr in {str(t.get("sender") or "").lower(), str(t.get("recipient") or "").lower()}
    ]
    before = params.get("before_id")
    if before is not None:
        rows = [t for t in rows if int(t["transaction_id"]) < int(before)]
    limit = params.get("limit")
    if limit is not None:
        rows = rows[: max(1, min(int(limit) or 100, 500))]
    return rows


class _FakeResp:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self._payload


class _FakeClient:
    """Stands in for ``httpx.AsyncClient``; serves ``/rpc/transactions``
    from the fixture's tx list (newest-first by transaction_id) and records
    every request's params."""

    def __init__(self, state: dict[str, Any]) -> None:
        self._state = state

    async def __aenter__(self) -> _FakeClient:
        return self

    async def __aexit__(self, *args: Any) -> bool:
        return False

    async def get(self, url: str, params: dict[str, Any] | None = None) -> _FakeResp:
        assert url.endswith("/rpc/transactions"), url
        p = dict(params or {})
        self._state["requests"].append(p)
        rows = _server_slice(self._state["txs"], p)
        return _FakeResp({"transactions": rows})


@pytest.fixture
def rpc_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Wire ``_fetch_transfers`` to the emulated server; returns the state
    dict (``txs`` newest-first, ``requests`` log)."""
    state: dict[str, Any] = {"txs": [], "requests": []}
    monkeypatch.setattr(sellmon.httpx, "AsyncClient", lambda **kw: _FakeClient(state))
    monkeypatch.setattr(sellmon.wdm, "BLOCKCHAIN_RPC_URL", "http://chain.test")
    return state


class TestFetchTransfersPaging:
    @pytest.mark.asyncio
    async def test_complete_history_beyond_server_clamp(self, rpc_env):
        """120 escrow txs > the server's 100-row clamp: limit=0 must still
        return every one — the pre-#3042 single fetch silently dropped 20."""
        rpc_env["txs"] = [_tx(i) for i in range(120, 0, -1)]
        txs = await sellmon._fetch_transfers(ESCROW)
        assert [t["transaction_id"] for t in txs] == list(range(120, 0, -1))
        # The fetch asked for a full page, not the legacy limit=0.
        assert rpc_env["requests"][0]["limit"] == sellmon._ESCROW_TX_PAGE_SIZE

    @pytest.mark.asyncio
    async def test_pages_backwards_with_before_id(self, rpc_env, monkeypatch):
        """More than one server page: the second request must carry
        before_id = the lowest transaction_id already seen."""
        monkeypatch.setattr(sellmon, "_ESCROW_TX_PAGE_SIZE", 100)
        rpc_env["txs"] = [_tx(i) for i in range(250, 0, -1)]
        txs = await sellmon._fetch_transfers(ESCROW)
        assert len(txs) == 250
        assert [t["transaction_id"] for t in txs] == list(range(250, 0, -1))
        assert len(rpc_env["requests"]) == 3
        assert rpc_env["requests"][1]["before_id"] == 151
        assert rpc_env["requests"][2]["before_id"] == 51

    @pytest.mark.asyncio
    async def test_address_filter_matches_sender_or_recipient(self, rpc_env):
        """Outbound sweeps (sender=escrow) are part of the window too —
        the scan sees both directions, like the server's address filter."""
        rpc_env["txs"] = [
            _tx(3, sender=ESCROW, recipient=SHOP),
            _tx(2, sender=SHOP, recipient=ESCROW),
            _tx(1, sender="0x" + "dd" * 20, recipient="0x" + "ee" * 20),
        ]
        txs = await sellmon._fetch_transfers(ESCROW)
        assert [t["transaction_id"] for t in txs] == [3, 2]

    @pytest.mark.asyncio
    async def test_explicit_limit_stays_single_page(self, rpc_env):
        rpc_env["txs"] = [_tx(i) for i in range(50, 0, -1)]
        txs = await sellmon._fetch_transfers(ESCROW, limit=7)
        assert len(txs) == 7
        assert len(rpc_env["requests"]) == 1
        assert rpc_env["requests"][0]["limit"] == 7

    @pytest.mark.asyncio
    async def test_missing_transaction_id_fails_closed(self, rpc_env, monkeypatch):
        """A full page without transaction_id cannot be paged past — the
        fetch must raise rather than return a possibly-truncated history."""
        monkeypatch.setattr(sellmon, "_ESCROW_TX_PAGE_SIZE", 3)
        bad = _tx(9)
        del bad["transaction_id"]
        rpc_env["txs"] = [bad, _tx(8), _tx(7), _tx(6)]
        with pytest.raises(RuntimeError, match="transaction_id"):
            await sellmon._fetch_transfers(ESCROW)

    @pytest.mark.asyncio
    async def test_page_cap_fails_closed(self, rpc_env, monkeypatch):
        monkeypatch.setattr(sellmon, "_ESCROW_TX_PAGE_SIZE", 3)
        monkeypatch.setattr(sellmon, "_ESCROW_TX_MAX_PAGES", 2)
        rpc_env["txs"] = [_tx(i) for i in range(20, 0, -1)]
        with pytest.raises(RuntimeError, match="exceeds"):
            await sellmon._fetch_transfers(ESCROW)


@pytest.fixture
def sell_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Sell-monitor DB on tmp_path + the env ``_sell_config`` needs."""
    db_path = tmp_path / "bridge.db"
    monkeypatch.setenv("AIT_SELL_ESCROW", ESCROW)
    monkeypatch.setenv("SELL_TREASURY_ADDRESS", TREASURY)
    monkeypatch.setenv("CHAIN_ID", "ait-testnet")
    monkeypatch.setenv("BLOCKCHAIN_RPC_URL", "http://chain.test")
    monkeypatch.delenv("SELL_ESCROW_FUNDING_SOURCES", raising=False)
    with patch("wallet_app.bridge.bridge_db.DB_PATH", str(db_path)):
        init_db()
        yield


class TestScanSeesEvictedLock:
    @pytest.mark.asyncio
    async def test_lock_buried_under_newest_100_still_recorded(self, rpc_env, sell_db):
        """The issue's headline repro: an unprocessed lock at the bottom of
        a >100-tx window must still be seen and recorded by one scan pass.
        Under the old contract the server's 100-row clamp hid it forever."""
        lock_hash = "0x" + "11" * 32
        # Oldest tx = the unprocessed lock; 119 newer txs fill the window —
        # half inbound noise, half outbound sweep legs (the real eviction
        # pressure: every settled trade spends two window rows).
        txs = [_tx(1, tx_hash=lock_hash, sender=SHOP, recipient=ESCROW, payload={"sell_quote": "sellq_abc"})]
        for i in range(2, 61):
            txs.append(_tx(i, sender=SHOP, recipient=ESCROW))  # inbound, no quote -> not this lane's lock? see below
        for i in range(61, 121):
            txs.append(_tx(i, sender=ESCROW, recipient=SHOP))  # outbound sweep legs
        rpc_env["txs"] = list(reversed(txs))  # newest-first for the server

        cfg = sellmon._sell_config()
        stats = await sellmon._scan_escrow_locks(cfg)

        # The lock was recorded despite sitting below the old 100-row window.
        row = get_sell_lock_by_ait_tx_hash(lock_hash)
        assert row is not None, "lock evicted from the scan window — stranded"
        assert stats["recorded"] >= 1
