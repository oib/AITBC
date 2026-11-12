"""#1859: broadcast outcome classification — definite rejection vs ambiguous.

Pre-fix ``_submit_transaction_to_chain`` returned ``{"success": False}``
for EVERY failure — HTTP 4xx refusals, 5xx crashes, timeouts, connection
resets alike — so the route could not tell "the node provably refused
before mempool" from "the tx may have landed". Every failure landed
``uncertain`` (operator resolution for routine rejections) while the
ambiguous case had no distinct handling.

Post-fix: 4xx / explicit success:false => ``definite`` (safe retry);
5xx / transport / unreadable => ``ambiguous`` (never a clean failure).
The route marks only definite rejections retryable; ambiguous stays
terminal/uncertain. Caller-supplied nonces below the confirmed account
nonce are refused locally.
"""

from unittest.mock import MagicMock

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import wallet_app.api_rest as api_rest
from wallet_app.api_rest import router
from wallet_app.deps import get_keystore, get_ledger, require_admin_api_key
from wallet_app.keystore.persistent_service import PersistentKeystoreService

from .conftest import TEST_PASSWORD


# ---------------------------------------------------------------------------
# _submit_transaction_to_chain classification
# ---------------------------------------------------------------------------

_TX = {"from": "0xa", "to": "0xb", "amount": 1, "fee": 1, "nonce": 0, "chain_id": "c", "type": "TRANSFER"}


class _Resp:
    def __init__(self, status_code: int = 200, body: dict | None = None):
        self.status_code = status_code
        self.text = "err" if status_code >= 400 else "ok"
        self._body = body or {"success": True, "transaction_hash": "0xabc"}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("err", request=MagicMock(), response=self)

    def json(self):
        return self._body


def _svc_with_post(monkeypatch, post):
    from wallet_app import keystore as _  # noqa: F401  (ensure package import order)
    import wallet_app.keystore.persistent_service as svc

    monkeypatch.setattr(svc.httpx, "post", post)
    return PersistentKeystoreService.__new__(PersistentKeystoreService)


def test_http_4xx_is_definite_rejection(monkeypatch):
    svc = _svc_with_post(monkeypatch, lambda *a, **k: _Resp(400))
    out = svc._submit_transaction_to_chain(_TX, "sig")
    assert out["success"] is False
    assert out.get("definite") is True
    assert not out.get("ambiguous")


def test_http_5xx_is_ambiguous(monkeypatch):
    svc = _svc_with_post(monkeypatch, lambda *a, **k: _Resp(503))
    out = svc._submit_transaction_to_chain(_TX, "sig")
    assert out["success"] is False
    assert out.get("ambiguous") is True
    assert not out.get("definite")


def test_transport_timeout_is_ambiguous(monkeypatch):
    def boom(*a, **k):
        raise httpx.ReadTimeout("timed out")

    svc = _svc_with_post(monkeypatch, boom)
    out = svc._submit_transaction_to_chain(_TX, "sig")
    assert out["success"] is False
    assert out.get("ambiguous") is True


def test_explicit_success_false_is_definite(monkeypatch):
    svc = _svc_with_post(monkeypatch, lambda *a, **k: _Resp(200, {"success": False, "error": "nonce conflict"}))
    out = svc._submit_transaction_to_chain(_TX, "sig")
    assert out["success"] is False
    assert out.get("definite") is True


# ---------------------------------------------------------------------------
# Route: definite -> retryable, ambiguous -> uncertain
# ---------------------------------------------------------------------------


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("WALLET_OPERATIONS_DB", str(tmp_path / "ops.db"))
    api_rest._operations_ledger = None

    keystore = MagicMock()
    app = FastAPI()
    app.include_router(router, prefix="/v1")
    app.dependency_overrides[get_keystore] = lambda: keystore
    app.dependency_overrides[get_ledger] = lambda: MagicMock()
    app.dependency_overrides[require_admin_api_key] = lambda: None
    yield TestClient(app), keystore
    api_rest._operations_ledger = None


BODY = {"password": "pw", "recipient": "0xrecipient", "amount": 5}


def _ok_result():
    return {
        "success": True,
        "tx_hash": "0xdeadbeef",
        "status": "pending",
        "sender": "0xsender",
        "recipient": "0xrecipient",
        "amount": 5,
        "fee": 36,
        "nonce": 1,
    }


def test_definite_rejection_is_retryable(client):
    """A 4xx-class refusal never broadcast — the same Idempotency-Key may
    retry and must NOT hit the uncertain 409."""
    tc, keystore = client
    keystore.sign_and_submit_transaction.return_value = {
        "success": False,
        "definite": True,
        "error": "HTTP 400: nonce conflict",
    }
    r1 = tc.post("/v1/wallets/w1/send", json=BODY, headers={"Idempotency-Key": "d1"})
    assert r1.status_code == 400

    keystore.sign_and_submit_transaction.return_value = _ok_result()
    r2 = tc.post("/v1/wallets/w1/send", json=BODY, headers={"Idempotency-Key": "d1"})
    assert r2.status_code == 200
    assert keystore.sign_and_submit_transaction.call_count == 2


def test_ambiguous_failure_stays_uncertain(client):
    """Timeout/5xx may have broadcast — retry with the same key is refused."""
    tc, keystore = client
    keystore.sign_and_submit_transaction.return_value = {
        "success": False,
        "ambiguous": True,
        "error": "ReadTimeout",
    }
    r1 = tc.post("/v1/wallets/w1/send", json=BODY, headers={"Idempotency-Key": "a1"})
    assert r1.status_code == 400

    keystore.sign_and_submit_transaction.return_value = _ok_result()
    r2 = tc.post("/v1/wallets/w1/send", json=BODY, headers={"Idempotency-Key": "a1"})
    assert r2.status_code == 409
    assert keystore.sign_and_submit_transaction.call_count == 1


def test_unclassified_failure_stays_uncertain(client):
    """Backward-compat: a bare {"success": False} with no classification
    keeps the conservative uncertain semantics."""
    tc, keystore = client
    keystore.sign_and_submit_transaction.return_value = {"success": False, "error": "insufficient funds"}
    tc.post("/v1/wallets/w1/send", json=BODY, headers={"Idempotency-Key": "u1"})
    keystore.sign_and_submit_transaction.return_value = _ok_result()
    r2 = tc.post("/v1/wallets/w1/send", json=BODY, headers={"Idempotency-Key": "u1"})
    assert r2.status_code == 409


# ---------------------------------------------------------------------------
# Caller-supplied nonce sanity
# ---------------------------------------------------------------------------


def test_supplied_nonce_below_account_nonce_refused(keystore: PersistentKeystoreService, monkeypatch):
    keystore.create_wallet("nia", TEST_PASSWORD)
    monkeypatch.setattr(PersistentKeystoreService, "_get_account_nonce", lambda self, addr: 9)
    captured = {}
    monkeypatch.setattr(
        PersistentKeystoreService,
        "_submit_transaction_to_chain",
        lambda self, tx_data, sig: captured.setdefault("called", True) or {"success": True},
    )
    monkeypatch.setenv("CHAIN_ID", "test-chain")

    result = keystore.sign_and_submit_transaction("nia", TEST_PASSWORD, "0x" + "44" * 20, 5, nonce=3, chain_id="test-chain")

    assert result["success"] is False
    assert "below the account nonce" in result["error"]
    assert "called" not in captured  # never reached broadcast


def test_supplied_nonce_at_account_nonce_proceeds(keystore: PersistentKeystoreService, monkeypatch):
    keystore.create_wallet("nib", TEST_PASSWORD)
    monkeypatch.setattr(PersistentKeystoreService, "_get_account_nonce", lambda self, addr: 9)
    monkeypatch.setattr(
        PersistentKeystoreService,
        "_submit_transaction_to_chain",
        lambda self, tx_data, sig: {"success": True, "transaction_hash": "0x1"},
    )
    monkeypatch.setenv("CHAIN_ID", "test-chain")

    result = keystore.sign_and_submit_transaction("nib", TEST_PASSWORD, "0x" + "44" * 20, 5, nonce=9, chain_id="test-chain")

    assert result["success"] is True
    assert result["nonce"] == 9
