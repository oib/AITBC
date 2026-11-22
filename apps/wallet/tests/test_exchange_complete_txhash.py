"""#2550 route pin — POST /v1/exchange/deposits/{id}/complete records tx_hash.

The CLI has always sent ``{"tx_hash": …}`` and the endpoint used to take no
body, so ``ait_tx_hash`` stayed NULL forever. The route now accepts the
optional body, validates the hash shape, and writes it while the row is
still 'verified' — a crash between that write and the status flip leaves a
resumable row that already names its payment.
"""

from decimal import Decimal
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from wallet_app.bridge.bridge_db import get_deposit_by_id, init_db, insert_deposit, update_deposit_status
from wallet_app.bridge.bridge_routes import exchange_router
from wallet_app.settings import settings

_TEST_KEY = "complete-txhash-test-key"
_TX_HASH = "0x" + "ab" * 32


@pytest.fixture
def client(tmp_path, monkeypatch):
    path = str(tmp_path / "bridge.db")
    with patch("wallet_app.bridge.bridge_db.DB_PATH", path):
        init_db()
        monkeypatch.setattr(settings, "api_key", _TEST_KEY, raising=False)
        monkeypatch.setattr(settings, "auth_enabled", True, raising=False)
        app = FastAPI()
        app.include_router(exchange_router)
        yield TestClient(app)


def _verified_deposit() -> str:
    deposit_id = insert_deposit("0xeth1", "0xfrom", Decimal("0.1"), Decimal("100"), recipient="0x" + "c" * 40)
    assert update_deposit_status(deposit_id, "verified", expected_statuses={"pending"})
    return deposit_id


def _complete(client, deposit_id, body=None):
    kwargs = {"headers": {"X-Api-Key": _TEST_KEY}}
    if body is not None:
        kwargs["json"] = body
    return client.post(f"/v1/exchange/deposits/{deposit_id}/complete", **kwargs)


def test_complete_records_tx_hash(client):
    deposit_id = _verified_deposit()
    resp = _complete(client, deposit_id, {"tx_hash": _TX_HASH})
    assert resp.status_code == 200
    row = get_deposit_by_id(deposit_id)
    assert row["status"] == "completed"
    assert row["ait_tx_hash"] == _TX_HASH


def test_complete_without_body_still_works(client):
    deposit_id = _verified_deposit()
    resp = _complete(client, deposit_id)
    assert resp.status_code == 200
    row = get_deposit_by_id(deposit_id)
    assert row["status"] == "completed"
    assert row["ait_tx_hash"] is None


def test_complete_rejects_malformed_tx_hash(client):
    deposit_id = _verified_deposit()
    resp = _complete(client, deposit_id, {"tx_hash": "not-a-hash"})
    assert resp.status_code == 400
    row = get_deposit_by_id(deposit_id)
    assert row["status"] == "verified"
    assert row["ait_tx_hash"] is None


def test_complete_requires_verified(client):
    deposit_id = insert_deposit("0xeth2", "0xfrom", Decimal("0.1"), Decimal("100"))
    resp = _complete(client, deposit_id, {"tx_hash": _TX_HASH})
    assert resp.status_code == 400
