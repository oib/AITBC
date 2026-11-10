"""Regression tests for the coder-C wallet defect sweep.

* #1452 — ``update_deposit_status`` stamped ``completed_at`` for every
  non-``verified`` status, so a ``pending`` reset fabricated a completion
  timestamp.
* #1453 — ``create_wallet`` registered the caller-claimed
  ``metadata.address`` on-chain instead of the address derived from the
  stored secret.
* #1455 — JSON-RPC ``wallet.create`` 500'd on malformed base64
  ``secret_key``, non-dict ``params``/``metadata``, or keystore
  ``ValueError``s.
* #1458 — ``GET /v1/bridge/sell/list`` was publicly enumerable (shop AIT +
  ETH payout addresses); it is now admin-keyed like ``/settlements``.
"""

from __future__ import annotations

import sqlite3
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from .conftest import TEST_PASSWORD


@pytest.fixture
def bridge_db(tmp_path: Path):
    """A fresh bridge DB in a temporary directory (same shape as test_bridge_db)."""
    from wallet_app.bridge.bridge_db import init_db

    db_path = tmp_path / "bridge.db"
    with patch("wallet_app.bridge.bridge_db.DB_PATH", str(db_path)):
        init_db()
        yield str(db_path)


# ---------------------------------------------------------------------------
# #1452 — deposit status timestamps
# ---------------------------------------------------------------------------


class TestDepositStatusTimestamps:
    def test_pending_reset_clears_completed_at(self, bridge_db):
        from wallet_app.bridge.bridge_db import insert_deposit, update_deposit_status

        deposit_id = insert_deposit(
            tx_hash="0xts" + "1" * 60,
            from_address="0x9999999999999999999999999999999999999999",
            amount_eth=Decimal("0.01"),
            amount_ait=Decimal("100"),
            recipient="0x1111111111111111111111111111111111111111",
        )
        # Drive the row through the completion path, then reset to pending —
        # the reset must not leave a fabricated completed_at behind.
        assert update_deposit_status(deposit_id, "verified")
        assert update_deposit_status(deposit_id, "completed")
        assert update_deposit_status(deposit_id, "pending")

        conn = sqlite3.connect(bridge_db)
        row = conn.execute(
            "SELECT status, verified_at, completed_at FROM eth_deposits WHERE id = ?",
            (deposit_id,),
        ).fetchone()
        conn.close()
        assert row[0] == "pending"
        assert row[2] is None, f"pending reset left completed_at={row[2]!r}"
        # verified_at is real history — the row did verify once.
        assert row[1] is not None

    def test_completed_still_stamps_completed_at(self, bridge_db):
        from wallet_app.bridge.bridge_db import insert_deposit, update_deposit_status

        deposit_id = insert_deposit(
            tx_hash="0xts" + "2" * 60,
            from_address="0x9999999999999999999999999999999999999999",
            amount_eth=Decimal("0.01"),
            amount_ait=Decimal("100"),
            recipient="0x1111111111111111111111111111111111111111",
        )
        assert update_deposit_status(deposit_id, "completed")
        conn = sqlite3.connect(bridge_db)
        row = conn.execute("SELECT completed_at FROM eth_deposits WHERE id = ?", (deposit_id,)).fetchone()
        conn.close()
        assert row[0] is not None

    def test_unknown_status_does_not_stamp_any_timestamp(self, bridge_db):
        from wallet_app.bridge.bridge_db import insert_deposit, update_deposit_status

        deposit_id = insert_deposit(
            tx_hash="0xts" + "3" * 60,
            from_address="0x9999999999999999999999999999999999999999",
            amount_eth=Decimal("0.01"),
            amount_ait=Decimal("100"),
            recipient="0x1111111111111111111111111111111111111111",
        )
        assert update_deposit_status(deposit_id, "failed")
        conn = sqlite3.connect(bridge_db)
        row = conn.execute("SELECT status, verified_at, completed_at FROM eth_deposits WHERE id = ?", (deposit_id,)).fetchone()
        conn.close()
        assert row == ("failed", None, None)


# ---------------------------------------------------------------------------
# #1453 — on-chain registration uses the derived address
# ---------------------------------------------------------------------------


class TestCreateWalletDerivedAddress:
    def test_metadata_address_mismatch_registers_derived(self, keystore, monkeypatch):
        from wallet_app.keystore.persistent_service import PersistentKeystoreService

        seen: list[str] = []

        def _capture(self, address: str):
            seen.append(address)
            return {"success": False, "created": False, "message": "stubbed", "balance": 0}

        monkeypatch.setattr(PersistentKeystoreService, "_register_account_on_chain", _capture)
        record = keystore.create_wallet(
            "mallory",
            TEST_PASSWORD,
            metadata={"address": "0x000000000000000000000000000000000000dEaD"},
        )
        assert seen == [record.public_key]
        assert record.public_key != "0x000000000000000000000000000000000000dEaD"

    def test_matching_metadata_address_still_registers(self, keystore, monkeypatch):
        from wallet_app.keystore.persistent_service import PersistentKeystoreService

        seen: list[str] = []

        def _capture(self, address: str):
            seen.append(address)
            return {"success": False, "created": False, "message": "stubbed", "balance": 0}

        monkeypatch.setattr(PersistentKeystoreService, "_register_account_on_chain", _capture)
        record = keystore.create_wallet("alice2", TEST_PASSWORD)
        assert seen == [record.public_key]


# ---------------------------------------------------------------------------
# #1455 — JSON-RPC input validation
# ---------------------------------------------------------------------------


class TestJsonRpcInputValidation:
    _KEY = "wallet-rpc-pin-key-0123456789abcdef"

    @pytest.fixture
    def rpc_client(self, monkeypatch):
        from wallet_app.api_jsonrpc import router as rpc_router
        from wallet_app.deps import get_keystore, get_ledger, get_receipt_service
        from wallet_app.settings import settings

        monkeypatch.setattr(settings, "auth_enabled", True, raising=False)
        monkeypatch.setattr(settings, "api_key", self._KEY, raising=False)

        keystore = MagicMock()
        app = FastAPI()
        app.include_router(rpc_router, prefix="/v1")
        app.dependency_overrides[get_keystore] = lambda: keystore
        app.dependency_overrides[get_ledger] = lambda: MagicMock()
        app.dependency_overrides[get_receipt_service] = lambda: MagicMock()
        return TestClient(app), keystore

    def _post(self, client: TestClient, payload: dict, key: str | None = _KEY):
        headers = {"X-API-Key": key} if key else {}
        return client.post("/v1/rpc", json=payload, headers=headers)

    def test_bad_base64_secret_returns_rpc_error_not_500(self, rpc_client):
        client, _ = rpc_client
        resp = self._post(
            client,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "wallet.create",
                "params": {"wallet_id": "w1", "password": "correct horse", "secret_key": "!!!not-base64!!!"},
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["error"]["code"] == -32602
        assert "base64" in body["error"]["message"]

    def test_non_dict_params_returns_rpc_error(self, rpc_client):
        client, _ = rpc_client
        resp = self._post(
            client,
            {"jsonrpc": "2.0", "id": 2, "method": "wallet.list", "params": ["not", "a", "dict"]},
        )
        assert resp.status_code == 200
        assert resp.json()["error"]["code"] == -32602

    def test_non_dict_metadata_returns_rpc_error(self, rpc_client):
        client, _ = rpc_client
        resp = self._post(
            client,
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "wallet.create",
                "params": {"wallet_id": "w2", "password": "correct horse", "metadata": "oops"},
            },
        )
        assert resp.status_code == 200
        assert resp.json()["error"]["code"] == -32602

    def test_keystore_value_error_returns_rpc_error(self, rpc_client):
        client, keystore = rpc_client
        keystore.create_wallet.side_effect = ValueError("wallet already exists")
        resp = self._post(
            client,
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "wallet.create",
                "params": {"wallet_id": "w3", "password": "correct horse"},
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["error"]["code"] == -32602
        assert "already exists" in body["error"]["message"]

    def test_valid_create_still_works(self, rpc_client):
        client, keystore = rpc_client
        record = MagicMock()
        record.wallet_id = "w4"
        record.public_key = "0xabc"
        record.metadata = {}
        keystore.create_wallet.return_value = record
        keystore.list_records.return_value = []
        resp = self._post(
            client,
            {
                "jsonrpc": "2.0",
                "id": 5,
                "method": "wallet.create",
                "params": {"wallet_id": "w4", "password": "correct horse"},
            },
        )
        assert resp.status_code == 200
        assert resp.json()["result"]["wallet"]["wallet_id"] == "w4"


# ---------------------------------------------------------------------------
# #1458 — sell/list is admin-keyed
# ---------------------------------------------------------------------------


class TestSellListAuth:
    _KEY = "wallet-sell-list-pin-key-0123456789abcdef"

    @pytest.fixture
    def sell_client(self, monkeypatch):
        from wallet_app.bridge import bridge_routes
        from wallet_app.bridge.bridge_routes import bridge_router
        from wallet_app.settings import settings

        monkeypatch.setattr(settings, "auth_enabled", True, raising=False)
        monkeypatch.setattr(settings, "api_key", self._KEY, raising=False)
        monkeypatch.setattr(bridge_routes, "get_all_sell_quotes", lambda **kw: [])
        monkeypatch.setattr(bridge_routes, "get_all_sell_locks", lambda **kw: [])

        app = FastAPI()
        app.include_router(bridge_router)  # router carries its own /v1/bridge prefix
        return TestClient(app)

    def test_sell_list_401_without_key(self, sell_client):
        resp = sell_client.get("/v1/bridge/sell/list")
        assert resp.status_code == 401

    def test_sell_list_200_with_key(self, sell_client):
        resp = sell_client.get("/v1/bridge/sell/list", headers={"X-API-Key": self._KEY})
        assert resp.status_code == 200
        assert resp.json()["quotes"] == []

    def test_sell_status_stays_public(self, sell_client, monkeypatch):
        """Per-quote status lookup is the buyer-facing read — it stays keyless."""
        from wallet_app.bridge import bridge_routes

        monkeypatch.setattr(
            bridge_routes,
            "get_sell_quote",
            lambda _id: {"quote_id": "q1", "status": "open", "shop_ait_address": "0xaaa"},
        )
        monkeypatch.setattr(bridge_routes, "get_sell_lock_by_quote_id", lambda _id: None)
        resp = sell_client.get("/v1/bridge/sell/status/q1")
        assert resp.status_code == 200
