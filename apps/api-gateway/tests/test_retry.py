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


# Headers httpx adds itself at send time — the gateway never chose them, so
# the fake must not record them as forwarded headers.
_TRANSPORT_HEADERS = {"host", "content-length", "accept", "accept-encoding", "connection", "user-agent", "transfer-encoding"}


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

    def build_request(self, method, url, **kwargs):
        return httpx.Request(method, url, **kwargs)

    async def send(self, request, stream=False):
        kwargs = {
            "headers": {k: v for k, v in request.headers.items() if k.lower() not in _TRANSPORT_HEADERS},
            "params": request.url.params,
        }
        if request.content:
            kwargs["content"] = request.content
        return await self._next(kwargs)

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


def test_idempotency_key_forwarded_but_client_request_id_not_honored(client, monkeypatch):
    """#1681: the edge generates its own X-Request-ID — a client-supplied one
    is a forgery vector and must never reach the upstream stamp."""
    flaky = _FlakyClient(httpx.Response(201, json={"ok": True}))
    monkeypatch.setattr(client.app.state, "http_client", flaky)

    client.post("/v1/coordinator/jobs", json={}, headers={"Idempotency-Key": "op-9", "X-Request-ID": "req-7"})

    assert flaky.last_headers.get("idempotency-key") == "op-9"
    forwarded_id = flaky.last_headers.get("x-request-id")
    assert forwarded_id and forwarded_id != "req-7"


def test_ambiguous_write_retry_denied_off_dedup_allowlist(client, monkeypatch):
    """#1667: Idempotency-Key alone must not enable retries on a route whose
    upstream does not deduplicate it — job cancel is not on the allowlist."""
    flaky = _FlakyClient(httpx.ReadTimeout("timed out", request=_request()))
    monkeypatch.setattr(client.app.state, "http_client", flaky)

    response = client.post("/v1/coordinator/jobs/job-1/cancel", json={}, headers={"Idempotency-Key": "op-1"})

    assert flaky.calls == 1
    assert response.status_code == 503
    assert response.json()["error"]["type"] == "outcome_unknown"


def test_ambiguous_write_retry_denied_without_key_even_on_allowlist(client, monkeypatch):
    """The allowlist still requires the client to actually send a key."""
    flaky = _FlakyClient(httpx.ReadTimeout("timed out", request=_request()))
    monkeypatch.setattr(client.app.state, "http_client", flaky)

    response = client.post("/v1/coordinator/jobs", json={})

    assert flaky.calls == 1
    assert response.status_code == 503
    assert response.json()["error"]["type"] == "outcome_unknown"


def test_ambiguous_write_retry_allowed_on_verified_dedup_route(client, monkeypatch):
    """POST /v1/coordinator/jobs maps to upstream v1/jobs — begin_operation
    dedups Idempotency-Key there, so the retry is safe."""
    flaky = _FlakyClient(httpx.ReadTimeout("t", request=_request()), httpx.Response(201, json={"ok": True}))
    monkeypatch.setattr(client.app.state, "http_client", flaky)

    response = client.post("/v1/coordinator/jobs", json={}, headers={"Idempotency-Key": "op-2"})

    assert flaky.calls == 2
    assert response.status_code == 201


def test_ambiguous_write_retry_allowed_via_v2_spelling(client, monkeypatch):
    """/v2/coordinator/v1/jobs (publicly /api/v2/coordinator/v1/jobs) resolves
    to the same upstream path — the allowlist matches upstream paths, not
    public spellings."""
    flaky = _FlakyClient(httpx.ReadTimeout("t", request=_request()), httpx.Response(201, json={"ok": True}))
    monkeypatch.setattr(client.app.state, "http_client", flaky)

    response = client.post("/v2/coordinator/v1/jobs", json={}, headers={"Idempotency-Key": "op-3"})

    assert flaky.calls == 2
    assert response.status_code == 201
