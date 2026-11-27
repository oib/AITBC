"""AUDIT-PERIMETER-RESIDUAL-1 / M-1 (#3082): mutating chain escrow routes are
an nginx source-IP chokepoint (``limit_except GET`` under ``/rpc/escrow/``).
The gateway forwards ``X-API-Key``/``X-Settlement-Key`` verbatim, so without
a route-class gate a caller holding the gateway credential plus those shared
keys could settle escrow from any source IP — collapsing the chokepoint to
the credential pair alone.

Pins:

* POST/PUT/PATCH/DELETE under the v1 ``escrow`` service (``/v1/escrow/*`` →
  ``/rpc/escrow/*``) are refused 403 before any upstream call.
* The same mutations spelled through the v2 chain qualifier
  (``/v2/chain/rpc/escrow/*``) are refused identically.
* Read-only escrow state (GET) still proxies on both spellings.
* The coordinator JWT escrow relays (``/v1/coordinator`` → ``v1/escrow/*``)
  and non-escrow chain writes are unaffected — settlement flows do not use
  the gateway (CLI/agent-coordinator call the chain RPC directly).
"""

import httpx
import pytest
from fastapi.testclient import TestClient

import api_gateway.main as gateway


@pytest.fixture(autouse=True)
def _no_auth(monkeypatch):
    monkeypatch.setattr(gateway, "REQUIRE_AUTH", False)


@pytest.fixture(autouse=True)
def _reset_breakers():
    for state in gateway.circuit_breaker_state.values():
        state["failures"] = 0
        state["is_open"] = False
        state["last_failure_time"] = None


@pytest.fixture
def client():
    with TestClient(gateway.app) as test_client:
        yield test_client


class _RecordingClient:
    """Stands in for app.state.http_client; records each call, returns 200."""

    def __init__(self):
        self.calls: list[dict] = []

    def build_request(self, method, url, **kwargs):
        return httpx.Request(method, url, **kwargs)

    async def send(self, request, stream=False):
        url, _, _query = str(request.url).partition("?")
        self.calls.append({"method": request.method, "url": url})
        return httpx.Response(200, json={"ok": True})

    async def aclose(self):
        pass


@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
@pytest.mark.parametrize(
    "path",
    [
        "/v1/escrow/create",
        "/v1/escrow/job-1/release",
        "/v1/escrow/job-1/refund",
    ],
)
def test_v1_escrow_mutations_refused_before_upstream(client, monkeypatch, method, path):
    recorder = _RecordingClient()
    monkeypatch.setattr(gateway.app.state, "http_client", recorder)

    if method == "delete":
        resp = client.request(method.upper(), path)
    else:
        resp = getattr(client, method)(path, json={})

    assert resp.status_code == 403
    assert resp.json()["error"]["type"] == "escrow_mutation_not_proxied"
    assert recorder.calls == []


@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
@pytest.mark.parametrize(
    "path",
    [
        "/v2/chain/rpc/escrow/create",
        "/v2/chain/rpc/escrow/job-1/release",
        "/v2/chain/rpc/escrow/job-1/refund",
    ],
)
def test_v2_chain_escrow_mutations_refused_before_upstream(client, monkeypatch, method, path):
    recorder = _RecordingClient()
    monkeypatch.setattr(gateway.app.state, "http_client", recorder)

    if method == "delete":
        resp = client.request(method.upper(), path)
    else:
        resp = getattr(client, method)(path, json={})

    assert resp.status_code == 403
    assert resp.json()["error"]["type"] == "escrow_mutation_not_proxied"
    assert recorder.calls == []


def test_escrow_reads_still_proxy(client, monkeypatch):
    recorder = _RecordingClient()
    monkeypatch.setattr(gateway.app.state, "http_client", recorder)

    resp = client.get("/v1/escrow/job-1")
    assert resp.status_code == 200
    assert recorder.calls[-1]["url"].endswith("/rpc/escrow/job-1")

    resp = client.get("/v2/chain/rpc/escrow/job-1")
    assert resp.status_code == 200
    assert recorder.calls[-1]["url"].endswith("/rpc/escrow/job-1")


def test_coordinator_escrow_relay_still_proxies(client, monkeypatch):
    """The customer-facing JWT relay (``/v1/coordinator`` → ``v1/escrow/*``)
    is the documented settlement path and must keep working."""
    recorder = _RecordingClient()
    monkeypatch.setattr(gateway.app.state, "http_client", recorder)

    resp = client.post("/v1/coordinator/escrow/release", json={"job_id": "job-1"})

    assert resp.status_code == 200
    assert recorder.calls[-1]["method"] == "POST"
    assert recorder.calls[-1]["url"].endswith("/v1/escrow/release")


def test_non_escrow_chain_writes_still_proxy(client, monkeypatch):
    recorder = _RecordingClient()
    monkeypatch.setattr(gateway.app.state, "http_client", recorder)

    resp = client.post("/v2/chain/rpc/transactions", json={"tx": {}})

    assert resp.status_code == 200
    assert recorder.calls[-1]["url"].endswith("/rpc/transactions")
