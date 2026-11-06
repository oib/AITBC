"""PI-API-006 pins: hop-by-hop headers never reach the upstream.

The proxy used to forward ``request.headers`` verbatim minus a few pops, so a
chunked request arrived upstream carrying both ``transfer-encoding`` and a
re-framed ``content-length`` — a TE+CL conflict that 400'd every chunked
``/api/`` request. These pins assert the full RFC 7230 §6.1 set (plus anything
``Connection`` nominates) is stripped while end-to-end headers survive.
"""

import httpx
import pytest
import api_gateway.main as gateway
from fastapi.testclient import TestClient


class _CaptureClient:
    """Records every upstream call; satisfies lifespan aclose."""

    def __init__(self):
        self.calls: list[dict] = []

    def _record(self, method, url, kwargs):
        self.calls.append({"method": method, "url": url, **kwargs})
        return httpx.Response(200, json={"ok": True})

    async def get(self, url, **kwargs):
        return self._record("GET", url, kwargs)

    async def post(self, url, **kwargs):
        return self._record("POST", url, kwargs)

    async def put(self, url, **kwargs):
        return self._record("PUT", url, kwargs)

    async def delete(self, url, **kwargs):
        return self._record("DELETE", url, kwargs)

    async def patch(self, url, **kwargs):
        return self._record("PATCH", url, kwargs)

    async def options(self, url, **kwargs):
        return self._record("OPTIONS", url, kwargs)

    async def aclose(self):
        pass


@pytest.fixture(autouse=True)
def _no_auth(monkeypatch):
    monkeypatch.setattr(gateway, "REQUIRE_AUTH", False)


@pytest.fixture
def capture():
    client = _CaptureClient()
    with TestClient(gateway.app) as test_client:
        test_client.app.state.http_client = client
        yield client


HOP_BY_HOP = [
    "transfer-encoding",
    "te",
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "trailer",
    "upgrade",
]


def _forwarded_headers(capture) -> dict[str, str]:
    assert capture.calls, "proxy never reached the upstream"
    return {k.lower(): v for k, v in capture.calls[-1].get("headers", {}).items()}


def test_chunked_post_strips_all_hop_by_hop_headers(capture):
    """A request carrying the full hop-by-hop set forwards none of it."""
    with TestClient(gateway.app) as client:
        client.app.state.http_client = capture
        response = client.post(
            "/v1/coordinator/jobs",
            content=b'{"job": "chunked-body"}',
            headers={
                "transfer-encoding": "chunked",
                "te": "trailers",
                "connection": "keep-alive, x-nominated",
                "keep-alive": "timeout=5",
                "proxy-authenticate": "Basic",
                "proxy-authorization": "Basic abc",
                "trailer": "x-checksum",
                "upgrade": "websocket",
                "x-nominated": "should-not-survive",
                "x-custom": "keep-me",
            },
        )

    assert response.status_code == 200
    sent = _forwarded_headers(capture)
    for name in HOP_BY_HOP:
        assert name not in sent, f"{name} leaked upstream"
    assert "x-nominated" not in sent, "Connection-nominated header leaked upstream"
    assert sent.get("x-custom") == "keep-me"
    assert "content-length" not in sent, "gateway must not forward a stale content-length"


def test_chunked_body_reaches_upstream_whole(capture):
    """The de-chunked body is what httpx re-frames — upstream sees full content."""
    body = b"x" * 10000

    def chunks():
        for i in range(0, len(body), 1024):
            yield body[i : i + 1024]

    with TestClient(gateway.app) as client:
        client.app.state.http_client = capture
        response = client.post("/v1/coordinator/jobs", content=chunks())

    assert response.status_code == 200
    call = capture.calls[-1]
    assert call.get("content") == body


def test_multiple_connection_headers_and_mixed_case(capture):
    """Each Connection header nominates its own tokens; casing is irrelevant.

    ``dict(request.headers)`` would keep only the first Connection value —
    the second header's nominated names must still be stripped.
    """
    with TestClient(gateway.app) as client:
        client.app.state.http_client = capture
        response = client.post(
            "/v1/coordinator/jobs",
            content=b"{}",
            headers=[
                ("CoNNection", "X-Nominated-One"),
                ("connection", "x-nominated-two, X-Nominated-One"),
                ("X-Nominated-One", "a"),
                ("X-Nominated-Two", "b"),
                ("X-Keep", "c"),
            ],
        )

    assert response.status_code == 200
    sent = _forwarded_headers(capture)
    assert "x-nominated-one" not in sent
    assert "x-nominated-two" not in sent
    assert sent.get("x-keep") == "c"


def test_normal_get_unchanged(capture):
    """Requests without hop-by-hop headers forward identically."""
    with TestClient(gateway.app) as client:
        client.app.state.http_client = capture
        response = client.get("/v1/coordinator/jobs", headers={"x-custom": "yes"})

    assert response.status_code == 200
    sent = _forwarded_headers(capture)
    assert sent.get("x-custom") == "yes"


def test_upstream_response_still_strips_framing(capture):
    """Response-side hop-by-hop set is unchanged in coverage."""

    class _FramedClient(_CaptureClient):
        async def get(self, url, **kwargs):
            return httpx.Response(
                200,
                content=b"{}",
                headers={
                    "content-length": "2",
                    "transfer-encoding": "chunked",
                    "connection": "close",
                    "keep-alive": "timeout=5",
                    "upgrade": "h2c",
                    "proxy-authenticate": "Basic",
                    "x-upstream": "visible",
                },
            )

    framed = _FramedClient()
    with TestClient(gateway.app) as client:
        client.app.state.http_client = framed
        response = client.get("/v1/coordinator/jobs")

    assert response.status_code == 200
    assert response.headers.get("x-upstream") == "visible"
    for name in ("transfer-encoding", "connection", "keep-alive", "upgrade", "proxy-authenticate"):
        assert response.headers.get(name) is None
