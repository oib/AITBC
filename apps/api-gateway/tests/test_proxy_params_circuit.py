"""#1425 / #1428 pins: query params survive the proxy verbatim; the circuit
breaker forgives a recovered service.

The proxy forwards ``request.url.query`` — the raw query string — so
repeated params reach the upstream byte-for-byte (``?a=1&a=2`` no longer
collapses to ``?a=2`` the way the starlette ``QueryParams`` mapping did).

The circuit breaker only ever counted failures: five sporadic upstream
errors — however far apart — opened the circuit on a service that had been
healthy for weeks. A completed upstream response now resets the count.
"""

import asyncio

import httpx
import pytest

import api_gateway.main as gateway


@pytest.fixture(autouse=True)
def _no_auth(monkeypatch):
    monkeypatch.setattr(gateway, "REQUIRE_AUTH", False)


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    with TestClient(gateway.app) as test_client:
        yield test_client


class _CaptureParamsClient:
    """Records the params kwarg the proxy built; satisfies lifespan aclose.

    The proxy builds an httpx.Request then send()s it, so the fake mirrors
    that two-step interface.
    """

    def __init__(self):
        self.params = None

    def build_request(self, method, url, **kwargs):
        self.params = kwargs.get("params")
        return httpx.Request(method, url, params=self.params, content=kwargs.get("content"))

    async def send(self, request, stream=False):
        return httpx.Response(200, json={"ok": True}, request=request)

    async def aclose(self):
        pass


def test_repeated_query_params_reach_upstream_verbatim(client, monkeypatch):
    capture = _CaptureParamsClient()
    monkeypatch.setattr(client.app.state, "http_client", capture)
    response = client.get("/v1/coordinator/jobs?tag=a&tag=b&status=open")

    assert response.status_code == 200
    # The raw query string preserves every pair and their order.
    assert capture.params == "tag=a&tag=b&status=open"


def test_upstream_sees_both_values_of_a_repeated_param(client, monkeypatch):
    """End-to-end through httpx URL building, not just the captured kwarg."""
    seen: dict[str, str] = {}

    class _EchoClient:
        def build_request(self, method, url, **kwargs):
            return httpx.Request(method, url, params=kwargs.get("params"), content=kwargs.get("content"))

        async def send(self, request, stream=False):
            # httpx already merged the params kwarg into request.url — this
            # is exactly what the upstream would receive.
            seen["url"] = str(request.url)
            return httpx.Response(200, json={"ok": True}, request=request)

        async def aclose(self):
            pass

    monkeypatch.setattr(client.app.state, "http_client", _EchoClient())
    response = client.get("/v1/coordinator/jobs?tag=a&tag=b")

    assert response.status_code == 200
    assert "tag=a" in seen["url"] and "tag=b" in seen["url"]


def _fresh_breaker_state(monkeypatch):
    """Isolate the module-level breaker dict for one service name."""
    name = "test-svc-circuit"
    gateway.circuit_breaker_state[name] = {
        "failures": 0,
        "last_failure_time": None,
        "is_open": False,
        "probe_in_flight": False,
    }
    return name


def test_success_resets_accumulated_failures(monkeypatch):
    name = _fresh_breaker_state(monkeypatch)

    async def scenario():
        # Sporadic errors far below the threshold used to accumulate forever.
        for _ in range(gateway.CIRCUIT_BREAKER_THRESHOLD - 1):
            gateway.record_failure(name)
        assert gateway.circuit_breaker_state[name]["failures"] == gateway.CIRCUIT_BREAKER_THRESHOLD - 1
        gateway.note_upstream_response(name, 200)
        assert gateway.circuit_breaker_state[name]["failures"] == 0
        # A fresh burst of CIRCUIT_BREAKER_THRESHOLD-1 failures must NOT open
        # the circuit — the count restarted at the last success.
        for _ in range(gateway.CIRCUIT_BREAKER_THRESHOLD - 1):
            gateway.record_failure(name)
        assert gateway.check_circuit_breaker(name) is True

    asyncio.run(scenario())


def test_success_closes_an_open_breaker_on_half_open_probe(monkeypatch):
    name = _fresh_breaker_state(monkeypatch)

    async def scenario():
        for _ in range(gateway.CIRCUIT_BREAKER_THRESHOLD):
            gateway.record_failure(name)
        assert gateway.check_circuit_breaker(name) is False
        # Timeout elapsed -> the breaker admits a single half-open probe;
        # its <500 response closes the breaker and resets the count.
        gateway.circuit_breaker_state[name]["last_failure_time"] = 0
        assert gateway.check_circuit_breaker(name) is True
        gateway.note_upstream_response(name, 200)
        assert gateway.circuit_breaker_state[name]["is_open"] is False
        assert gateway.circuit_breaker_state[name]["failures"] == 0
        assert gateway.check_circuit_breaker(name) is True

    asyncio.run(scenario())
