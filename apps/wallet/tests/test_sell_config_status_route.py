"""Route tests for GET /v1/bridge/sell/config-status (CLI-5).

The sell lane's enabled/disabled state readable without journald —
admin-keyed like /settlements, carrying sell_status_document()'s
non-secret shape (key slots as configured booleans only).
"""

import json
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from wallet_app.bridge.bridge_db import init_db
from wallet_app.bridge.bridge_routes import bridge_router
from wallet_app.settings import settings

_TEST_KEY = "sell-cfg-route-test-key"


@pytest.fixture
def client(tmp_path, monkeypatch):
    # init_db on a tmp bridge.db keeps _pending-style helpers happy if the
    # doc builder ever touches the ledger; the route itself is env-only.
    with patch("wallet_app.bridge.bridge_db.DB_PATH", str(tmp_path / "bridge.db")):
        init_db()
    monkeypatch.setattr(settings, "api_key", _TEST_KEY, raising=False)
    monkeypatch.setattr(settings, "auth_enabled", True, raising=False)
    for key in ("SELL_ESCROW_ENABLED", "BRIDGE_ENABLED", "AIT_SELL_ESCROW", "SELL_TREASURY_ADDRESS", "CHAIN_ID"):
        monkeypatch.delenv(key, raising=False)
    app = FastAPI()
    app.include_router(bridge_router)
    return TestClient(app)


class TestSellConfigStatusAuth:
    def test_no_key_refused(self, client):
        assert client.get("/v1/bridge/sell/config-status").status_code == 401

    def test_wrong_key_refused(self, client):
        assert client.get("/v1/bridge/sell/config-status", headers={"X-Api-Key": "wrong"}).status_code == 401


class TestSellConfigStatusRead:
    def test_disabled_default(self, client):
        resp = client.get("/v1/bridge/sell/config-status", headers={"X-Api-Key": _TEST_KEY})
        assert resp.status_code == 200
        body = resp.json()
        assert body["enabled"] is False
        assert body["reason"] == "sell escrow disabled"
        assert body["flags"]["sell_escrow_enabled"] is False

    def test_enabled_with_config(self, client, monkeypatch):
        monkeypatch.setenv("SELL_ESCROW_ENABLED", "true")
        # wdm.BRIDGE_ENABLED binds at module import — set the attr, not env.
        monkeypatch.setattr("wallet_app.bridge.bridge_withdraw_monitor.BRIDGE_ENABLED", True)
        monkeypatch.setenv("AIT_SELL_ESCROW", "0x" + "11" * 20)
        monkeypatch.setenv("SELL_TREASURY_ADDRESS", "0x" + "22" * 20)
        monkeypatch.setenv("CHAIN_ID", "ait-testnet")
        resp = client.get("/v1/bridge/sell/config-status", headers={"X-Api-Key": _TEST_KEY})
        body = resp.json()
        assert body["enabled"] is True
        cfg = body["config"]
        assert cfg["chain_id"] == "ait-testnet"
        assert cfg["escrow_address"] == "0x" + "11" * 20
        assert cfg["max_eth_per_day"] == "0.03"
        # Key slots surface only as booleans — never path or name content.
        assert cfg["escrow_wallet_configured"] is True
        assert "escrow_wallet_path" not in cfg
        assert "escrow_credential_file" not in cfg
        assert "/etc/aitbc" not in json.dumps(cfg)
