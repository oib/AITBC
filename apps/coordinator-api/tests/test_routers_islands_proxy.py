"""Tests for /v1/islands/* — the edge-api proxy router (#1289).

The router has no auth deps of its own (matrix ANY); enforcement lives at
edge-api, which requires a fleet JWT on every /v1 route (#1205). These tests
pin the proxy contract: the caller's Authorization header is forwarded
verbatim (or omitted), upstream status codes pass through, a 404 on the
detail route maps to a clean 404, and transport failures surface as 503.
``SharedHttpClient`` is stubbed — no live edge calls.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from aitbc.network import SharedHttpClient

EDGE = "http://127.0.0.1:8111/v1"


class _EdgeMock:
    """Records SharedHttpClient calls and replays scripted responses."""

    def __init__(self) -> None:
        self.get_calls: list[tuple[str, dict[str, Any]]] = []
        self.post_calls: list[tuple[str, dict[str, Any]]] = []
        self.get_response: httpx.Response | Exception = httpx.Response(
            200, json={"ok": True}, request=httpx.Request("GET", EDGE)
        )
        self.post_response: httpx.Response | Exception = httpx.Response(
            200, json={"ok": True}, request=httpx.Request("POST", EDGE)
        )

    @staticmethod
    def _respond(scripted: httpx.Response | Exception, url: str) -> httpx.Response:
        if isinstance(scripted, Exception):
            raise scripted
        # Rebind the request so raise_for_status()/json() see the real URL.
        return httpx.Response(
            scripted.status_code,
            content=scripted.content,
            headers=scripted.headers,
            request=httpx.Request(scripted.request.method, url),
        )

    async def get(self, url: str, **kwargs: Any) -> httpx.Response:
        self.get_calls.append((url, kwargs))
        return self._respond(self.get_response, url)

    async def post(self, url: str, **kwargs: Any) -> httpx.Response:
        self.post_calls.append((url, kwargs))
        return self._respond(self.post_response, url)


@pytest.fixture
def edge(monkeypatch: pytest.MonkeyPatch) -> _EdgeMock:
    mock = _EdgeMock()
    monkeypatch.setattr(SharedHttpClient, "get", mock.get)
    monkeypatch.setattr(SharedHttpClient, "post", mock.post)
    return mock


def _auth() -> dict[str, str]:
    return {"Authorization": "Bearer fleet-jwt"}


@pytest.mark.unit
class TestIslandsProxyForwarding:
    def test_list_forwards_authorization_header(self, client: TestClient, edge: _EdgeMock) -> None:
        resp = client.get("/v1/islands/", headers=_auth())
        assert resp.status_code == 200
        url, kwargs = edge.get_calls[0]
        assert url == f"{EDGE}/islands/"
        assert kwargs["headers"] == {"Authorization": "Bearer fleet-jwt"}

    def test_list_without_auth_sends_no_header(self, client: TestClient, edge: _EdgeMock) -> None:
        """No caller credentials -> no Authorization header upstream (edge 401s)."""
        resp = client.get("/v1/islands/")
        assert resp.status_code == 200
        _, kwargs = edge.get_calls[0]
        assert kwargs["headers"] == {}

    def test_get_island_success(self, client: TestClient, edge: _EdgeMock) -> None:
        resp = client.get("/v1/islands/isle-1", headers=_auth())
        assert resp.status_code == 200
        url, _ = edge.get_calls[0]
        assert url == f"{EDGE}/islands/isle-1"

    def test_get_island_404_maps_to_clean_404(self, client: TestClient, edge: _EdgeMock) -> None:
        req = httpx.Request("GET", f"{EDGE}/islands/nope")
        edge.get_response = httpx.HTTPStatusError(
            "nf", request=req, response=httpx.Response(404, text="not found", request=req)
        )
        resp = client.get("/v1/islands/nope")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Island nope not found"

    def test_upstream_error_status_passes_through(self, client: TestClient, edge: _EdgeMock) -> None:
        req = httpx.Request("GET", f"{EDGE}/islands/")
        edge.get_response = httpx.HTTPStatusError(
            "bad gw", request=req, response=httpx.Response(502, text="upstream bad", request=req)
        )
        resp = client.get("/v1/islands/")
        assert resp.status_code == 502

    def test_transport_failure_maps_to_503(self, client: TestClient, edge: _EdgeMock) -> None:
        edge.get_response = httpx.ConnectError("refused")
        resp = client.get("/v1/islands/")
        assert resp.status_code == 503
        assert resp.json()["detail"] == "Edge API unavailable"


@pytest.mark.unit
class TestIslandsProxyWrites:
    def test_join_forwards_body_and_auth(self, client: TestClient, edge: _EdgeMock) -> None:
        resp = client.post("/v1/islands/join", json={"island_id": "isle-2"}, headers=_auth())
        assert resp.status_code == 200
        url, kwargs = edge.post_calls[0]
        assert url == f"{EDGE}/islands/join"
        assert kwargs["json"] == {"island_id": "isle-2"}
        assert kwargs["headers"] == {"Authorization": "Bearer fleet-jwt"}

    def test_bridge_transport_failure_maps_to_503(self, client: TestClient, edge: _EdgeMock) -> None:
        edge.post_response = httpx.ConnectError("refused")
        resp = client.post("/v1/islands/bridge", json={"target": "isle-3"})
        assert resp.status_code == 503
