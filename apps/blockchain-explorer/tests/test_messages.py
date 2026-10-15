"""MSG-4 — /api/messages/* proxy contract tests.

The routes are read-only proxies to the chain RPC's /rpc/messaging/* surface.
These tests pin: the upstream URL, the bounds (limit clamps to 1..100, offset
rejects past 500 with the upstream wording), cursor pass-through, and error
shape forwarding (upstream detail on 4xx, 503 on transport failure). No real
RPC is contacted — httpx.AsyncClient is faked.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import routers.messages as messages
from main import app


class _FakeResp:
    def __init__(self, status: int = 200, body: object = None, text: str = ""):
        self.status_code = status
        self._body = body if body is not None else {"success": True}
        self.text = text

    def json(self):
        if isinstance(self._body, Exception):
            raise self._body
        return self._body


class _FakeClient:
    """Records the GET and returns a canned response."""

    resp: _FakeResp = _FakeResp()
    calls: list[tuple[str, dict]] = []

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, params=None, timeout=None):
        _FakeClient.calls.append((url, dict(params or {})))
        return _FakeClient.resp


@pytest.fixture
def client(monkeypatch):
    _FakeClient.calls.clear()
    _FakeClient.resp = _FakeResp()
    monkeypatch.setattr(messages.httpx, "AsyncClient", _FakeClient)
    return TestClient(app)


# --- happy path: forwards to the right upstream route ---


def test_state_proxies(client):
    r = client.get("/api/messages/state")
    assert r.status_code == 200
    url, params = _FakeClient.calls[-1]
    assert url.endswith("/rpc/messaging/state")
    assert "chain_id" in params


def test_topics_proxies_with_bounds(client):
    r = client.get("/api/messages/topics?limit=7&offset=3")
    assert r.status_code == 200
    url, params = _FakeClient.calls[-1]
    assert url.endswith("/rpc/messaging/topics")
    assert params["limit"] == 7 and params["offset"] == 3


def test_messages_proxies_topic_and_cursor(client):
    r = client.get("/api/messages?topic=msg-fix&cursor=48865:0xabc")
    assert r.status_code == 200
    url, params = _FakeClient.calls[-1]
    assert url.endswith("/rpc/messaging/messages")
    assert params["topic"] == "msg-fix"
    assert params["cursor"] == "48865:0xabc"


def test_no_write_routes(client):
    r = client.post("/api/messages", json={"body": "x"})
    assert r.status_code == 405


# --- bounds ---


def test_limit_clamps_to_100(client):
    r = client.get("/api/messages?limit=9999")
    assert r.status_code == 200
    assert _FakeClient.calls[-1][1]["limit"] == 100


def test_limit_floor_is_1(client):
    r = client.get("/api/messages?limit=0")
    assert r.status_code == 200
    assert _FakeClient.calls[-1][1]["limit"] == 1


def test_offset_past_cap_is_400(client):
    r = client.get("/api/messages?offset=501")
    assert r.status_code == 400
    assert "offset must be 0..500" in r.json()["detail"]
    assert not _FakeClient.calls  # rejected without touching upstream


def test_topics_offset_past_cap_is_400(client):
    assert client.get("/api/messages/topics?offset=501").status_code == 400


# --- error shape forwarding ---


def test_upstream_400_detail_passes_through(client):
    _FakeClient.resp = _FakeResp(400, {"detail": "topic 'X' is not a valid slug"})
    r = client.get("/api/messages?topic=X")
    assert r.status_code == 400
    assert r.json()["detail"] == "topic 'X' is not a valid slug"


def test_upstream_non_json_error_forwarded(client):
    _FakeClient.resp = _FakeResp(502, ValueError("nope"), text="bad gateway")
    r = client.get("/api/messages/state")
    assert r.status_code == 502


def test_transport_failure_is_503(client):
    import httpx

    class _BoomClient(_FakeClient):
        async def get(self, url, params=None, timeout=None):
            raise httpx.ConnectError("refused")

    with TestClient(app) as c:
        messages.httpx.AsyncClient = _BoomClient
        try:
            r = c.get("/api/messages/state")
        finally:
            messages.httpx.AsyncClient = _FakeClient
    assert r.status_code == 503
