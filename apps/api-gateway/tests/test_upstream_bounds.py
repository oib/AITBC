"""APIGW-OLLAMA-DEPTH2-1 / APIGW-DEPTH-1 (#1613/#1581): upstream response
bounds and circuit-breaker residuals.

The proxy used to buffer ``response.content`` whole — a huge or drip-fed
upstream could hold a connection and RAM per in-flight request. The body is
now read off the stream under ``GATEWAY_MAX_RESPONSE_BYTES`` inside
``GATEWAY_UPSTREAM_DEADLINE_SECONDS``. The breaker gained a single-probe
half-open state, a monotonic clock, and opt-in 5xx counting.
"""

import asyncio
import time

import httpx
import pytest
from fastapi.testclient import TestClient

import api_gateway.main as gateway


@pytest.fixture(autouse=True)
def _no_auth(monkeypatch):
    monkeypatch.setattr(gateway, "REQUIRE_AUTH", False)


@pytest.fixture(autouse=True)
def _restore_breaker():
    """Breaker state is module-global; don't leak an open breaker to other tests."""
    snapshot = {k: dict(v) for k, v in gateway.circuit_breaker_state.items()}
    yield
    gateway.circuit_breaker_state.clear()
    gateway.circuit_breaker_state.update(snapshot)


@pytest.fixture
def client():
    with TestClient(gateway.app) as test_client:
        yield test_client


class _ScriptedClient:
    """build_request/send stand-in; returns queued responses or sleeps."""

    def __init__(self, *results):
        self.results = list(results)
        self.calls = 0

    def build_request(self, method, url, **kwargs):
        return httpx.Request(method, url, **kwargs)

    async def send(self, request, stream=False):
        self.calls += 1
        item = self.results.pop(0)
        if isinstance(item, Exception):
            raise item
        if isinstance(item, float):
            await asyncio.sleep(item)
            item = self.results.pop(0)
        return item

    async def aclose(self):
        pass


def _ok(body: bytes = b'{"ok": true}', status: int = 200) -> httpx.Response:
    return httpx.Response(status, content=body, headers={"content-type": "application/json"})


def test_response_body_still_proxied(client, monkeypatch):
    fake = _ScriptedClient(_ok(b'{"hello":"world"}'))
    monkeypatch.setattr(client.app.state, "http_client", fake)
    resp = client.get("/v1/coordinator/jobs")
    assert resp.status_code == 200
    assert resp.json() == {"hello": "world"}


def test_upstream_response_over_cap_is_502(client, monkeypatch):
    monkeypatch.setattr(gateway, "MAX_RESPONSE_BYTES", 8)
    fake = _ScriptedClient(_ok(b"x" * 100))
    monkeypatch.setattr(client.app.state, "http_client", fake)
    resp = client.get("/v1/coordinator/jobs")
    assert resp.status_code == 502
    assert resp.json()["error"]["type"] == "upstream_response_too_large"


def test_upstream_deadline_is_outcome_unknown(client, monkeypatch):
    monkeypatch.setattr(gateway, "UPSTREAM_DEADLINE_SECONDS", 0.05)
    # A send that answers only after the deadline: the upstream may have
    # committed, so the client gets outcome_unknown, not a silent retry.
    fake = _ScriptedClient(0.5, _ok())
    monkeypatch.setattr(client.app.state, "http_client", fake)
    resp = client.post("/v1/coordinator/jobs", json={})
    assert resp.status_code == 503
    assert resp.json()["error"]["type"] == "outcome_unknown"


# ── Circuit breaker: half-open single probe, monotonic clock, opt-in 5xx ────


def _open_breaker(service: str = "coordinator") -> None:
    state = gateway.circuit_breaker_state[service]
    state.update({"failures": gateway.CIRCUIT_BREAKER_THRESHOLD, "is_open": True, "probe_in_flight": False})
    state["last_failure_time"] = time.monotonic() - gateway.CIRCUIT_BREAKER_TIMEOUT - 1


def test_half_open_admits_exactly_one_probe():
    _open_breaker()
    assert gateway.check_circuit_breaker("coordinator") is True  # the probe
    assert gateway.check_circuit_breaker("coordinator") is False  # everyone else waits


def test_half_open_probe_success_closes_breaker():
    _open_breaker()
    assert gateway.check_circuit_breaker("coordinator") is True
    gateway.note_upstream_response("coordinator", 200)
    state = gateway.circuit_breaker_state["coordinator"]
    assert state["is_open"] is False and state["failures"] == 0 and state["probe_in_flight"] is False
    assert gateway.check_circuit_breaker("coordinator") is True


def test_half_open_probe_5xx_reopens_immediately():
    _open_breaker()
    assert gateway.check_circuit_breaker("coordinator") is True
    gateway.note_upstream_response("coordinator", 503)
    state = gateway.circuit_breaker_state["coordinator"]
    assert state["is_open"] is True and state["probe_in_flight"] is False


def test_5xx_counts_only_when_opted_in(monkeypatch):
    service = "explorer"
    state = gateway.circuit_breaker_state[service]
    state.update({"failures": 0, "is_open": False, "probe_in_flight": False, "last_failure_time": None})
    monkeypatch.setattr(gateway, "BREAKER_COUNT_5XX", False)
    for _ in range(gateway.CIRCUIT_BREAKER_THRESHOLD + 1):
        gateway.note_upstream_response(service, 500)
    assert state["failures"] == 0
    monkeypatch.setattr(gateway, "BREAKER_COUNT_5XX", True)
    gateway.note_upstream_response(service, 500)
    assert state["failures"] == 1


def test_record_failure_clears_probe_flag():
    _open_breaker()
    assert gateway.check_circuit_breaker("coordinator") is True
    gateway.record_failure("coordinator")
    state = gateway.circuit_breaker_state["coordinator"]
    assert state["probe_in_flight"] is False and state["is_open"] is True
