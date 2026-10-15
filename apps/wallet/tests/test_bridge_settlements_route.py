"""Route tests for GET /v1/bridge/settlements (CLI-1).

The route is admin-keyed like sell/quote — the /v1/bridge mount is publicly
exposed on hub and settlement rows carry diagnostic error text plus release
nonces/hashes. These tests run the REAL ``require_admin_api_key`` dependency
against a monkeypatched settings object; nothing touches a live service.
"""

from decimal import Decimal
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from wallet_app.bridge.bridge_db import init_db, insert_exchange_settlement
from wallet_app.bridge.bridge_routes import bridge_router
from wallet_app.settings import settings

_TEST_KEY = "settlements-route-test-key"


@pytest.fixture
def db(tmp_path):
    path = str(tmp_path / "bridge.db")
    with patch("wallet_app.bridge.bridge_db.DB_PATH", path):
        init_db()
        yield


@pytest.fixture
def client(db, monkeypatch):
    monkeypatch.setattr(settings, "api_key", _TEST_KEY, raising=False)
    monkeypatch.setattr(settings, "auth_enabled", True, raising=False)
    app = FastAPI()
    app.include_router(bridge_router)
    return TestClient(app)


def _seed():
    sid = insert_exchange_settlement(
        "trade",
        7,
        buyer_address="0x" + "11" * 20,
        seller_address="0x" + "22" * 20,
        amount_ait=Decimal("10"),
        eth_amount=Decimal("0.001"),
        fee_ait=Decimal("0"),
    )
    rid = insert_exchange_settlement("order_refund", -42, amount_ait=Decimal("0.5"))
    return sid, rid


class TestSettlementsAuth:
    def test_no_key_refused(self, client):
        resp = client.get("/v1/bridge/settlements")
        assert resp.status_code == 401

    def test_wrong_key_refused(self, client):
        resp = client.get("/v1/bridge/settlements", headers={"X-Api-Key": "wrong"})
        assert resp.status_code == 401

    def test_flag_off_empty_with_key(self, client):
        # Empty table (nothing ever ran under the flag) answers [] with the key.
        resp = client.get("/v1/bridge/settlements", headers={"X-Api-Key": _TEST_KEY})
        assert resp.status_code == 200
        body = resp.json()
        assert body["settlements"] == []
        assert body["count"] == 0


class TestSettlementsRead:
    def test_lists_rows_with_key(self, client):
        sid, rid = _seed()
        resp = client.get("/v1/bridge/settlements", headers={"X-Api-Key": _TEST_KEY})
        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] == 2
        rows = {r["id"]: r for r in body["settlements"]}
        assert sid in rows and rid in rows
        assert rows[sid]["kind"] == "trade"
        assert rows[sid]["amount_ait"] == "10"
        assert rows[rid]["kind"] == "order_refund"
        assert rows[rid]["ref_id"] == -42

    def test_kind_filter(self, client):
        _seed()
        resp = client.get(
            "/v1/bridge/settlements",
            params={"kind": "order_refund"},
            headers={"X-Api-Key": _TEST_KEY},
        )
        body = resp.json()
        assert body["count"] == 1
        assert body["settlements"][0]["kind"] == "order_refund"

    def test_status_filter(self, client):
        _seed()
        resp = client.get(
            "/v1/bridge/settlements",
            params={"status": "locked"},
            headers={"X-Api-Key": _TEST_KEY},
        )
        assert resp.json()["count"] == 2
        resp = client.get(
            "/v1/bridge/settlements",
            params={"status": "settled"},
            headers={"X-Api-Key": _TEST_KEY},
        )
        assert resp.json()["count"] == 0

    def test_bad_kind_400(self, client):
        resp = client.get(
            "/v1/bridge/settlements",
            params={"kind": "bogus"},
            headers={"X-Api-Key": _TEST_KEY},
        )
        assert resp.status_code == 400
