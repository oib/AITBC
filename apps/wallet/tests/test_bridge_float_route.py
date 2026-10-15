"""Route tests for GET /v1/bridge/float (CLI-5).

Read-only float view: wallet ETH balance (RPC, mocked), pending reserve
across the three release lanes, and today/24h release windows from the
committed-since ledger helpers. Admin-keyed like /settlements — the real
``require_admin_api_key`` dependency runs against a monkeypatched settings.
"""

import sqlite3
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from wallet_app.bridge.bridge_db import (
    init_db,
    insert_exchange_settlement,
    insert_sell_lock,
    insert_withdrawal,
    update_exchange_settlement,
    update_sell_lock_status,
    update_withdrawal_status,
)
from wallet_app.bridge.bridge_routes import bridge_router
from wallet_app.settings import settings

_TEST_KEY = "float-route-test-key"


@pytest.fixture
def db(tmp_path):
    path = str(tmp_path / "bridge.db")
    with patch("wallet_app.bridge.bridge_db.DB_PATH", path):
        init_db()
        yield path


@pytest.fixture
def client(db, monkeypatch):
    monkeypatch.setattr(settings, "api_key", _TEST_KEY, raising=False)
    monkeypatch.setattr(settings, "auth_enabled", True, raising=False)
    monkeypatch.setenv("ETH_WALLET_ADDRESS", "0x" + "aa" * 20)
    app = FastAPI()
    app.include_router(bridge_router)
    return TestClient(app)


def _mock_balance():
    async def fake(address: str) -> Decimal:
        return Decimal("1.5")

    return patch("wallet_app.bridge.bridge_withdraw_monitor._eth_balance", side_effect=fake)


def _backdate(db_path: str, table: str, key_col: str, key: str, hours: float) -> None:
    """Move a row's released_at into the past (fixture-level — the window
    math is what is under test, not the timestamp writers)."""
    conn = sqlite3.connect(db_path)
    conn.execute(
        f"UPDATE {table} SET released_at = ? WHERE {key_col} = ?",  # noqa: S608 - test-only fixture with literal table/column names
        ((datetime.now() - timedelta(hours=hours)).isoformat(), key),
    )
    conn.commit()
    conn.close()


def _seed_released(db_path: str, *, hours_ago: float = 0.0) -> None:
    """One released row in each of the three lanes."""
    insert_withdrawal("0xwd", "0x" + "11" * 20, "0x" + "22" * 20, Decimal("1"), Decimal("0"), Decimal("1"), Decimal("0.010"))
    update_withdrawal_status("0xwd", "released", eth_tx_hash="0xeth1")
    insert_sell_lock("0xsell", "0x" + "33" * 20, Decimal("2"), eth_amount=Decimal("0.020"))
    update_sell_lock_status("0xsell", "released", eth_tx_hash="0xeth2")
    sid = insert_exchange_settlement("trade", 7, eth_amount=Decimal("0.030"))
    update_exchange_settlement(sid, "released", eth_tx_hash="0xeth3")
    if hours_ago:
        _backdate(db_path, "eth_withdrawals", "ait_tx_hash", "0xwd", hours_ago)
        _backdate(db_path, "bridge_sell_locks", "ait_tx_hash", "0xsell", hours_ago)
        _backdate(db_path, "exchange_settlements", "id", sid, hours_ago)


class TestFloatAuth:
    def test_no_key_refused(self, client):
        assert client.get("/v1/bridge/float").status_code == 401

    def test_wrong_key_refused(self, client):
        assert client.get("/v1/bridge/float", headers={"X-Api-Key": "wrong"}).status_code == 401


class TestFloatRead:
    def test_balance_reserve_windows(self, client, db):
        _seed_released(db)
        with _mock_balance():
            resp = client.get("/v1/bridge/float", headers={"X-Api-Key": _TEST_KEY})
        assert resp.status_code == 200
        body = resp.json()
        assert body["eth_address"] == "0x" + "aa" * 20
        assert body["balance_eth"] == "1.5"
        assert body["balance_error"] is None
        # All three rows are released-committed, none pending → reserve 0.
        assert body["pending_reserve_eth"] == "0"
        assert body["available_eth"] == "1.5"
        for window in ("today", "last_24h"):
            w = body["windows"][window]
            assert w["withdrawals_eth"] == "0.01"
            assert w["sell_eth"] == "0.02"
            assert w["exchange_eth"] == "0.03"
            assert w["total_eth"] == "0.06"
        cap = body["sell_daily_cap"]
        assert cap["max_eth_per_day"] == "0.03"
        assert cap["committed_24h"] == "0.02"
        assert cap["remaining"] == "0.01"
        assert cap["window"] == "rolling 24h"

    def test_today_window_excludes_yesterday(self, client, db):
        """'today' = service-local midnight → a row released 26h ago is out
        of 'today' but still inside the rolling 24h window is not; 48h is
        out of both."""
        _seed_released(db, hours_ago=48)
        insert_withdrawal(
            "0xwd2", "0x" + "11" * 20, "0x" + "22" * 20, Decimal("1"), Decimal("0"), Decimal("1"), Decimal("0.005")
        )
        update_withdrawal_status("0xwd2", "released", eth_tx_hash="0xeth9")
        resp = client.get("/v1/bridge/float", headers={"X-Api-Key": _TEST_KEY})
        body = resp.json()
        today = body["windows"]["today"]
        # Only the fresh 0.005 withdrawal counts today.
        assert today["withdrawals_eth"] == "0.005"
        assert today["sell_eth"] == "0"
        assert today["total_eth"] == "0.005"
        # Rolling 24h sees the fresh row; the 48h-old sell/exchange are out.
        last = body["windows"]["last_24h"]
        assert last["withdrawals_eth"] == "0.005"
        assert last["sell_eth"] == "0"

    def test_pending_reserve_counts_open_rows(self, client, db):
        insert_sell_lock("0xsellopen", "0x" + "33" * 20, Decimal("2"), eth_amount=Decimal("0.04"))
        insert_withdrawal(
            "0xwopen", "0x" + "11" * 20, "0x" + "22" * 20, Decimal("1"), Decimal("0"), Decimal("1"), Decimal("0.03")
        )
        sid = insert_exchange_settlement("trade", 9, eth_amount=Decimal("0.02"))
        assert sid
        with _mock_balance():
            resp = client.get("/v1/bridge/float", headers={"X-Api-Key": _TEST_KEY})
        body = resp.json()
        # locked sell + pending withdrawal + locked settlement = 0.09
        assert body["pending_reserve_eth"] == "0.09"
        assert body["available_eth"] == "1.41"
        # Nothing released → windows all zero.
        assert body["windows"]["today"]["total_eth"] == "0"

    def test_rpc_failure_keeps_ledger_numbers(self, client, db):
        _seed_released(db)

        async def boom(address: str):
            raise RuntimeError("rpc down https://user:secret@provider.invalid/v3/key")

        with patch("wallet_app.bridge.bridge_withdraw_monitor._eth_balance", side_effect=boom):
            resp = client.get("/v1/bridge/float", headers={"X-Api-Key": _TEST_KEY})
        assert resp.status_code == 200
        body = resp.json()
        assert body["balance_eth"] is None
        assert body["available_eth"] is None
        # The error is surfaced but the URL inside it is redacted to origin.
        assert body["balance_error"] == "rpc down https://provider.invalid"
        assert body["windows"]["today"]["total_eth"] == "0.06"

    def test_failed_and_refunded_rows_not_committed(self, client, db):
        insert_withdrawal(
            "0xwfail", "0x" + "11" * 20, "0x" + "22" * 20, Decimal("1"), Decimal("0"), Decimal("1"), Decimal("0.02")
        )
        update_withdrawal_status("0xwfail", "failed", error="reverted")
        insert_sell_lock("0xsellf", "0x" + "33" * 20, Decimal("2"), eth_amount=Decimal("0.02"))
        update_sell_lock_status("0xsellf", "failed", error="x")
        sid = insert_exchange_settlement("order_refund", -5, eth_amount=Decimal("0.02"))
        update_exchange_settlement(sid, "refunded")
        resp = client.get("/v1/bridge/float", headers={"X-Api-Key": _TEST_KEY})
        body = resp.json()
        assert body["windows"]["today"]["total_eth"] == "0"
        assert body["windows"]["last_24h"]["total_eth"] == "0"
