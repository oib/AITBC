"""main.py health wiring and CSP helper branches not covered by endpoint pins."""

import asyncio
import logging

import httpx
import pytest
from fastapi.testclient import TestClient

from main import app, health
from routers.csp import _integer, _safe_url


@pytest.fixture
def client():
    return TestClient(app)


def test_health_degraded_when_rpc_unreachable(monkeypatch):
    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def get(self, url, timeout=None):
            raise httpx.ConnectError("down")

    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: FakeClient())
    payload = asyncio.run(health())
    assert payload["status"] == "degraded"
    assert payload["node_status"] == "error"


def test_health_ok_when_rpc_returns_200(monkeypatch):
    class FakeResponse:
        status_code = 200

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def get(self, url, timeout=None):
            return FakeResponse()

    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: FakeClient())
    payload = asyncio.run(health())
    assert payload["status"] == "ok"
    assert payload["node_status"] == "ok"


@pytest.mark.parametrize("value", ["inline", "eval", "self", "wasm-eval"])
def test_safe_url_symbolic_passthrough(value):
    assert _safe_url(value) == value


def test_integer_rejects_bool_and_out_of_range():
    assert _integer(True, 100) is None
    assert _integer(-1, 100) is None
    assert _integer(600, 599) is None
    assert _integer(42, 100) == 42


def test_csp_invalid_content_length(client, caplog):
    with caplog.at_level(logging.WARNING, logger="routers.csp"):
        r = client.post(
            "/api/csp-report",
            content=b'{"csp-report":{"document-uri":"https://viewer.invalid/a.html","effective-directive":"style-src"}}',
            headers={"Content-Type": "application/csp-report", "Content-Length": "not-a-number"},
        )
    assert r.status_code == 400
    assert r.json()["detail"] == "Invalid content length"


def test_csp_negative_content_length(client, caplog):
    with caplog.at_level(logging.WARNING, logger="routers.csp"):
        r = client.post(
            "/api/csp-report",
            content=b'{"csp-report":{"document-uri":"https://viewer.invalid/a.html","effective-directive":"style-src"}}',
            headers={"Content-Type": "application/csp-report", "Content-Length": "-1"},
        )
    assert r.status_code == 400


def test_chain_head_endpoint_with_mocked_rpc(client, monkeypatch):
    async def _head(chain_id=None):
        return {"height": 5, "hash": "0xabc", "validator": "0xv"}

    monkeypatch.setattr("routers.chains.get_chain_head", _head)
    r = client.get("/api/chain/head")
    assert r.status_code == 200
    assert r.json()["height"] == 5
