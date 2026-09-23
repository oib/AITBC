"""Retry-semantics tests for proxy_with_retry.

The gateway used to retry every method after any timeout — including POSTs that
may already have committed upstream. Retries are now split by whether the
request provably left the gateway: pre-send failures retry for every method,
post-send failures only for safe methods or writes carrying Idempotency-Key.
"""

import httpx
import pytest
from fastapi.testclient import TestClient

import api_gateway.main as gateway


@pytest.fixture(autouse=True)
def _no_auth(monkeypatch):
    monkeypatch.setattr(gateway, "REQUIRE_AUTH", False)


@pytest.fixture
def client():
    with TestClient(gateway.app) as test_client:
        yield test_client


def _request(method: str = "POST") -> httpx.Request:
    return httpx.Request(method, "http://upstream.invalid/x")


class _FlakyClient:
    """Returns queued results/exceptions; records call count and headers."""

    def __init__(self, *results):
        self.results = list(results)
        self.calls = 0
        self.last_headers: dict = {}

    async def _next(self, kwargs):
        self.calls += 1
        self.last_headers = kwargs.get("headers", {})
        item = self.results.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    async def get(self, url, **kwargs):
        return await self._next(kwargs)

    async def head(self, url, **kwargs):
        return await self._next(kwargs)

    async def post(self, url, **kwargs):
        return await self._next(kwargs)

    async def put(self, url, **kwargs):
        return await self._next(kwargs)

    async def patch(self, url, **kwargs):
        return await self._next(kwargs)

    async def delete(self, url, **kwargs):
        return await self._next(kwargs)

    async def options(self, url, **kwargs):
        return await self._next(kwargs)

    async def aclose(self):
        pass


def test_post_read_timeout_is_not_replayed(client, monkeypatch):
    """A post-send timeout on a keyless write must not be repeated upstream."""
    flaky = _FlakyClient(httpx.ReadTimeout("timed out", request=_request()))
    monkeypatch.setattr(client.app.state, "http_client", flaky)

    response = client.post("/v1/coordinator/jobs", json={})

    assert flaky.calls == 1
    assert response.status_code == 503
    assert response.json()["error"]["type"] == "outcome_unknown"


def test_post_read_timeout_retries_with_idempotency_key(client, monkeypatch):
    """A write carrying Idempotency-Key is safe to replay — the upstream dedups."""
    flaky = _FlakyClient(httpx.ReadTimeout("timed out", request=_request()), httpx.Response(201, json={"ok": True}))
    monkeypatch.setattr(client.app.state, "http_client", flaky)

    response = client.post("/v1/coordinator/jobs", json={}, headers={"Idempotency-Key": "op-123"})

    assert flaky.calls == 2
    assert response.status_code == 201


def test_get_read_timeout_retries(client, monkeypatch):
    """Safe methods keep retrying ambiguous failures."""
    flaky = _FlakyClient(httpx.ReadTimeout("t", request=_request("GET")), httpx.Response(200, json={"ok": True}))
    monkeypatch.setattr(client.app.state, "http_client", flaky)

    response = client.get("/v1/coordinator/jobs")

    assert flaky.calls == 2
    assert response.status_code == 200


def test_connect_error_retries_any_method(client, monkeypatch):
    """ConnectError means the request never left the gateway — safe for POST."""
    flaky = _FlakyClient(httpx.ConnectError("refused", request=_request()), httpx.Response(201, json={"ok": True}))
    monkeypatch.setattr(client.app.state, "http_client", flaky)

    response = client.post("/v1/coordinator/jobs", json={})

    assert flaky.calls == 2
    assert response.status_code == 201


def test_exhausted_unsent_retries_report_unavailable(client, monkeypatch):
    flaky = _FlakyClient(*[httpx.ConnectError("refused", request=_request())] * 3)
    monkeypatch.setattr(client.app.state, "http_client", flaky)

    response = client.post("/v1/coordinator/jobs", json={})

    assert flaky.calls == 3
    assert response.status_code == 503
    assert response.json()["error"]["type"] == "service_unavailable"


def test_idempotency_key_and_request_id_forwarded(client, monkeypatch):
    flaky = _FlakyClient(httpx.Response(201, json={"ok": True}))
    monkeypatch.setattr(client.app.state, "http_client", flaky)

    client.post("/v1/coordinator/jobs", json={}, headers={"Idempotency-Key": "op-9", "X-Request-ID": "req-7"})

    assert flaky.last_headers.get("idempotency-key") == "op-9"
    assert flaky.last_headers.get("x-request-id") == "req-7"
