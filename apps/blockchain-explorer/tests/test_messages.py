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


# --- MSG-17: author/topic/search/detail surfaces ---


def test_messages_author_param_proxies(client):
    r = client.get("/api/messages?author=0xBdDF")
    assert r.status_code == 200
    url, params = _FakeClient.calls[-1]
    assert url.endswith("/rpc/messaging/messages")
    assert params["author"] == "0xBdDF"


def test_search_proxies_query_and_bounds(client):
    r = client.get("/api/messages/search?q=checkpoint&limit=7")
    assert r.status_code == 200
    url, params = _FakeClient.calls[-1]
    assert url.endswith("/rpc/messaging/messages/search")
    assert params["q"] == "checkpoint" and params["limit"] == 7


def test_search_offset_past_cap_is_400(client):
    assert client.get("/api/messages/search?offset=501").status_code == 400


def test_search_route_not_shadowed_by_tx_hash(client):
    """The literal /messages/search must resolve before /messages/{tx_hash}."""
    r = client.get("/api/messages/search?q=x")
    assert r.status_code == 200
    url, _ = _FakeClient.calls[-1]
    assert url.endswith("/rpc/messaging/messages/search")


def test_message_detail_proxies(client):
    h = "0x" + "ab" * 32
    r = client.get(f"/api/messages/{h}")
    assert r.status_code == 200
    url, _ = _FakeClient.calls[-1]
    assert url.endswith(f"/rpc/messaging/messages/{h}")


def test_message_votes_proxies(client):
    h = "0x" + "cd" * 32
    r = client.get(f"/api/messages/{h}/votes")
    assert r.status_code == 200
    url, _ = _FakeClient.calls[-1]
    assert url.endswith(f"/rpc/messaging/messages/{h}/votes")


def test_reputation_proxies(client):
    addr = "0x" + "12" * 20
    r = client.get(f"/api/messages/reputation/{addr}")
    assert r.status_code == 200
    url, _ = _FakeClient.calls[-1]
    assert url.endswith(f"/rpc/messaging/reputation/{addr}")


def test_topic_moderation_proxies(client):
    r = client.get("/api/messages/topics/msg-fix/moderation")
    assert r.status_code == 200
    url, _ = _FakeClient.calls[-1]
    assert url.endswith("/rpc/messaging/topics/msg-fix/moderation")


def test_search_404_detail_passes_through(client):
    _FakeClient.resp = _FakeResp(404, {"detail": "not found"})
    r = client.get("/api/messages/" + "0x" + "00" * 32)
    assert r.status_code == 404
    assert r.json()["detail"] == "not found"


# --- path-segment validation (MSG-17 follow-up) ---
#
# Path params land in the upstream URL. `..`, `?`, or a segment that does not
# match the upstream's expected shape must be a 4xx here and never reach the
# RPC (_FakeClient.calls stays empty).


@pytest.mark.parametrize("seg", ["%2E%2E", "a%3Fb", "x/x", "nothex"])
def test_tx_hash_segment_rejected(client, seg):
    r = client.get(f"/api/messages/{seg}")
    assert r.status_code in (400, 404, 422)
    assert not _FakeClient.calls


@pytest.mark.parametrize("seg", ["%2E%2E", "a%3Fb", "x/x", "nothex"])
def test_tx_hash_votes_segment_rejected(client, seg):
    r = client.get(f"/api/messages/{seg}/votes")
    assert r.status_code in (400, 404, 422)
    assert not _FakeClient.calls


@pytest.mark.parametrize("seg", ["%2E%2E", "a%3Fb", "x/x", "0x123"])
def test_address_segment_rejected(client, seg):
    r = client.get(f"/api/messages/reputation/{seg}")
    assert r.status_code in (400, 404, 422)
    assert not _FakeClient.calls


@pytest.mark.parametrize("seg", ["%2E%2E", "a%3Fb", "x/x", ".hidden", "-lead", "trail-"])
def test_slug_segment_rejected(client, seg):
    r = client.get(f"/api/messages/topics/{seg}/moderation")
    assert r.status_code in (400, 404, 422)
    assert not _FakeClient.calls


def test_valid_segments_still_proxy(client):
    h = "0x" + "ab" * 32
    for path in (
        f"/api/messages/{h}",
        f"/api/messages/{h}/votes",
        "/api/messages/reputation/" + "0x" + "cd" * 20,
        "/api/messages/topics/msg-fix/moderation",
    ):
        assert client.get(path).status_code == 200, path


def test_literal_dotdot_never_climbs_upstream(client):
    """Client-side normalization may fold a raw `..` before the router sees
    it, landing on a neighbouring route — the invariant is that nothing is
    proxied outside the /rpc/messaging/ namespace."""
    for path in (
        "/api/messages/..",
        "/api/messages/../votes",
        "/api/messages/reputation/..",
        "/api/messages/topics/../moderation",
    ):
        client.get(path)
    for url, _ in _FakeClient.calls:
        assert "/rpc/messaging/" in url, url
