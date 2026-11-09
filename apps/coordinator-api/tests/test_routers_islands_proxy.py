"""Router tests for /v1/islands/* (#1289 round 9 batch 4).

Pure proxy to edge-api via SharedHttpClient. Contract under test:
503 when edge is unreachable, auth-header passthrough, and status/error
mapping — pinned with a fake SharedHttpClient plus the real down-state.
"""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

import coordinator_api.contexts.infrastructure.routers.islands_proxy as islands_mod
from aitbc.auth import create_access_token

BASE = "/v1/islands"


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token('u', 'client')}"}


class _FakeResponse:
    def __init__(self, status_code: int = 200, payload: dict | None = None) -> None:
        self.status_code = status_code
        self._payload = payload or {"ok": True}
        self.text = str(self._payload)

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "err", request=httpx.Request("GET", "http://x"), response=httpx.Response(self.status_code, text=self.text)
            )

    def json(self):
        return self._payload


class _FakeClient:
    """Stand-in for SharedHttpClient recording calls."""

    calls: list[dict] = []
    next_response: _FakeResponse = _FakeResponse()
    next_error: Exception | None = None

    @classmethod
    async def get(cls, url, **kw):
        cls.calls.append({"method": "GET", "url": url, **kw})
        if cls.next_error:
            raise cls.next_error
        return cls.next_response

    @classmethod
    async def post(cls, url, **kw):
        cls.calls.append({"method": "POST", "url": url, **kw})
        if cls.next_error:
            raise cls.next_error
        return cls.next_response


@pytest.fixture
def fake_edge(monkeypatch: pytest.MonkeyPatch) -> type[_FakeClient]:
    _FakeClient.calls = []
    _FakeClient.next_response = _FakeResponse()
    _FakeClient.next_error = None
    monkeypatch.setattr(islands_mod, "SharedHttpClient", _FakeClient)
    return _FakeClient


class TestIslandsProxyDown:
    def test_list_503_when_edge_down(self, client: TestClient) -> None:
        resp = client.get(BASE + "/", headers=_headers())
        assert resp.status_code == 503

    def test_get_island_503_when_edge_down(self, client: TestClient) -> None:
        assert client.get(f"{BASE}/isl-1", headers=_headers()).status_code == 503


class TestIslandsProxyForwarding:
    def test_list_forwards_and_returns(self, client: TestClient, fake_edge: type[_FakeClient]) -> None:
        fake_edge.next_response = _FakeResponse(200, {"islands": [1, 2]})
        resp = client.get(BASE + "/", headers=_headers())
        assert resp.status_code == 200
        assert resp.json() == {"islands": [1, 2]}
        assert fake_edge.calls[0]["url"].endswith("/islands/")

    def test_auth_header_passed_through(self, client: TestClient, fake_edge: type[_FakeClient]) -> None:
        client.get(BASE + "/", headers=_headers())
        assert fake_edge.calls[0]["headers"]["Authorization"].startswith("Bearer ")

    def test_no_auth_header_no_forward(self, client: TestClient, fake_edge: type[_FakeClient]) -> None:
        client.get(BASE + "/")
        assert fake_edge.calls[0]["headers"] == {}

    def test_get_island_404_mapping(self, client: TestClient, fake_edge: type[_FakeClient]) -> None:
        fake_edge.next_response = _FakeResponse(404, {"detail": "nope"})
        resp = client.get(f"{BASE}/ghost", headers=_headers())
        assert resp.status_code == 404
        assert "ghost" in resp.json()["detail"]

    def test_upstream_error_passthrough(self, client: TestClient, fake_edge: type[_FakeClient]) -> None:
        fake_edge.next_response = _FakeResponse(403, {"detail": "forbidden"})
        assert client.get(BASE + "/", headers=_headers()).status_code == 403

    def test_join_posts_body(self, client: TestClient, fake_edge: type[_FakeClient]) -> None:
        resp = client.post(f"{BASE}/join", json={"island_id": "i1"}, headers=_headers())
        assert resp.status_code == 200
        assert fake_edge.calls[0]["method"] == "POST"
        assert fake_edge.calls[0]["url"].endswith("/islands/join")

    def test_request_error_maps_503(self, client: TestClient, fake_edge: type[_FakeClient]) -> None:
        fake_edge.next_error = httpx.ConnectError("refused")
        assert client.post(f"{BASE}/bridge", json={}, headers=_headers()).status_code == 503
