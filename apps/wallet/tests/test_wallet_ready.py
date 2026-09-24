"""The wallet's /ready probe: required dependencies are the local sqlite
stores (keystore, wallet ledger, operation ledger) and the blockchain RPC the
send/balance routes broadcast through. The coordinator URL is deliberately
not required — it only serves receipt verification."""

import sqlite3

import httpx
import pytest
from fastapi.testclient import TestClient

from wallet_app.main import app, _wallet_readiness_checks
from wallet_app.settings import settings


@pytest.fixture
def client(tmp_path, monkeypatch):
    """The app with every local store under tmp_path and RPC stubbed healthy."""
    ledger = tmp_path / "wallet_ledger.db"
    monkeypatch.setenv("DATABASE_FILENAME", str(ledger))
    monkeypatch.setenv("WALLET_OPERATIONS_DB", str(tmp_path / "wallet_operations.db"))
    monkeypatch.setattr(type(settings), "ledger_db_path", property(lambda self: ledger))
    yield TestClient(app)


class _RPC:
    status = 200

    @staticmethod
    def get(url, timeout=0):
        req = httpx.Request("GET", url)
        if _RPC.status == 200:
            return httpx.Response(200, json={"status": "ok"}, request=req)
        return httpx.Response(503, request=req)


def _stub_rpc(monkeypatch, status: int = 200):
    _RPC.status = status
    monkeypatch.setattr(httpx, "get", _RPC.get)


def test_ready_when_dependencies_available(client, tmp_path, monkeypatch):
    _stub_rpc(monkeypatch)
    resp = client.get("/ready")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ready"
    assert sorted(body["checks"]) == ["blockchain_rpc", "keystore_db", "ledger_db", "operations_db"]


def test_not_ready_when_rpc_down(client, monkeypatch):
    _stub_rpc(monkeypatch, status=503)
    resp = client.get("/ready")
    assert resp.status_code == 503
    assert resp.json()["failed"] == ["blockchain_rpc"]


def test_not_ready_when_rpc_unreachable(client, monkeypatch):
    def refused(url, timeout=0):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(httpx, "get", refused)
    resp = client.get("/ready")
    assert resp.status_code == 503
    body = resp.json()
    assert "blockchain_rpc" in body["failed"]
    # The socket detail stays server-side; /ready is unauthenticated.
    assert "refused" not in resp.text


def test_sqlite_check_fails_on_directory(tmp_path):
    from wallet_app.main import _sqlite_check

    check = _sqlite_check(tmp_path)  # a directory is not a sqlite file
    with pytest.raises(sqlite3.OperationalError):
        check()


def test_readiness_checks_cover_the_ledger(tmp_path, monkeypatch):
    monkeypatch.setenv("WALLET_OPERATIONS_DB", str(tmp_path / "ops.db"))
    monkeypatch.setattr(type(settings), "ledger_db_path", property(lambda self: tmp_path / "wallet_ledger.db"))
    checks = _wallet_readiness_checks()
    assert set(checks) == {"keystore_db", "ledger_db", "operations_db", "blockchain_rpc"}
