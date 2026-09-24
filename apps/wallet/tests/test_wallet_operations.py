"""Idempotency-Key handling on POST /wallets/{id}/send.

Wallet sends are the highest-risk replay surface: a broadcast that timed out
may have landed, so the ledger uses ``allow_adopt=False`` and terminal
failures — ambiguous outcomes go ``uncertain`` for operator resolution rather
than re-signing a second transaction.
"""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from wallet_app.api_rest import router
from wallet_app.deps import get_keystore, get_ledger, require_admin_api_key
from fastapi import FastAPI

import wallet_app.api_rest as api_rest


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("WALLET_OPERATIONS_DB", str(tmp_path / "ops.db"))
    api_rest._operations_ledger = None  # reset the module singleton

    keystore = MagicMock()
    keystore.sign_and_submit_transaction.return_value = {
        "success": True,
        "tx_hash": "0xdeadbeef",
        "status": "pending",
        "sender": "0xsender",
        "recipient": "0xrecipient",
        "amount": 5,
        "fee": 36,
        "nonce": 1,
    }
    app = FastAPI()
    app.include_router(router, prefix="/v1")
    app.dependency_overrides[get_keystore] = lambda: keystore
    app.dependency_overrides[get_ledger] = lambda: MagicMock()
    app.dependency_overrides[require_admin_api_key] = lambda: None
    yield TestClient(app), keystore
    api_rest._operations_ledger = None


BODY = {"password": "pw", "recipient": "0xrecipient", "amount": 5}


def test_send_replays_same_tx(client):
    tc, keystore = client
    r1 = tc.post("/v1/wallets/w1/send", json=BODY, headers={"Idempotency-Key": "k1"})
    assert r1.status_code == 200
    r2 = tc.post("/v1/wallets/w1/send", json=BODY, headers={"Idempotency-Key": "k1"})
    assert r2.status_code == 200
    assert r2.json()["tx_hash"] == "0xdeadbeef"
    assert keystore.sign_and_submit_transaction.call_count == 1


def test_send_key_conflict_on_different_body(client):
    tc, _ = client
    tc.post("/v1/wallets/w1/send", json=BODY, headers={"Idempotency-Key": "k2"})
    r = tc.post("/v1/wallets/w1/send", json={**BODY, "amount": 9}, headers={"Idempotency-Key": "k2"})
    assert r.status_code == 409


def test_send_failure_marks_uncertain_not_retryable(client):
    tc, keystore = client
    keystore.sign_and_submit_transaction.return_value = {"success": False, "error": "insufficient funds"}
    r1 = tc.post("/v1/wallets/w1/send", json=BODY, headers={"Idempotency-Key": "k3"})
    assert r1.status_code == 400
    # A retry with the same key is refused — the outcome may have broadcast.
    keystore.sign_and_submit_transaction.return_value = {
        "success": True,
        "tx_hash": "0xabc",
        "status": "pending",
        "sender": "s",
        "recipient": "r",
        "amount": 5,
        "fee": 36,
        "nonce": 2,
    }
    r2 = tc.post("/v1/wallets/w1/send", json=BODY, headers={"Idempotency-Key": "k3"})
    assert r2.status_code == 409
    assert "unknown" in r2.json()["detail"]
    assert keystore.sign_and_submit_transaction.call_count == 1


def test_send_exception_marks_uncertain(client):
    tc, keystore = client
    keystore.sign_and_submit_transaction.side_effect = TimeoutError("rpc timeout")
    r1 = tc.post("/v1/wallets/w1/send", json=BODY, headers={"Idempotency-Key": "k4"})
    assert r1.status_code == 500
    keystore.sign_and_submit_transaction.side_effect = None
    r2 = tc.post("/v1/wallets/w1/send", json=BODY, headers={"Idempotency-Key": "k4"})
    assert r2.status_code == 409


def test_send_without_key_unaffected(client):
    tc, _ = client
    r = tc.post("/v1/wallets/w1/send", json=BODY)
    assert r.status_code == 200
