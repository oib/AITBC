"""
Test API Gateway routing

These previously described an older gateway and 6 of 7 failed on every build: they hit
`/gpu/health` when the registered prefix is `/v1/gpu`, expected `/services` to return
`{"services": [...]}` when it returns a dict keyed by service name, and never
authenticated while REQUIRE_AUTH defaults to true (so everything 401'd).

They now exercise the real surface. Routing tests run with auth disabled via conftest.
"""

import httpx
import pytest
import api_gateway.main as gateway
from api_gateway.main import SERVICES
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _no_auth(monkeypatch):
    """Force REQUIRE_AUTH off for this module's routing tests.

    test_auth.py reloads api_gateway.main with auth enabled; its finally-reload
    runs before monkeypatch restores the env, leaving the module global stuck at
    True. verify_auth reads that global at request time, so it must be pinned
    here regardless of collection order.
    """
    monkeypatch.setattr(gateway, "REQUIRE_AUTH", False)


@pytest.fixture
def client():
    """Test client with lifespan run, so app.state.http_client exists.

    Without the context manager the proxy route raises AttributeError on the missing
    client and every proxied request 500s regardless of routing.
    """
    # Serve gateway.app (looked up at fixture time) rather than a module-level
    # `app` import — test_auth/test_rate_limiting reload the module and proxy_request
    # reads the *current* module global app.state.
    with TestClient(gateway.app) as test_client:
        yield test_client


def test_gateway_health_check(client):
    """Test gateway health check endpoint"""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "api-gateway"


def test_service_registry(client):
    """`/services` returns a mapping of service name -> {prefix, url}."""
    response = client.get("/services")
    assert response.status_code == 200

    data = response.json()
    assert "market" in data
    assert data["market"]["prefix"] == "/v1/market"
    assert data["market"]["url"] == "http://localhost:8102"


def test_service_registry_covers_every_registered_service(client):
    response = client.get("/services")

    assert set(response.json()) == set(SERVICES)


class _CaptureClient:
    """Records the upstream URL the proxy built; satisfies lifespan aclose."""

    def __init__(self):
        self.url = ""

    async def get(self, url, **kwargs):
        self.url = url
        return httpx.Response(200, json={"ok": True})

    async def aclose(self):
        pass


@pytest.mark.parametrize(
    "path,expected_url",
    [
        ("/v1/coordinator/jobs", "http://localhost:8203/v1/jobs"),
        ("/v1/market/jobs", "http://localhost:8102/v1/market/jobs"),
        # Coordinator-owned market families must not land on :8102.
        ("/v1/market/gpu/quote", "http://localhost:8203/v1/market/gpu/quote"),
        ("/v1/market/providers", "http://localhost:8203/v1/market/providers"),
        ("/v1/market/orders", "http://localhost:8203/v1/market/orders"),
        ("/v1/exchange/orders", "http://localhost:8106/api/orders"),
        ("/v1/trading/exchange/rates", "http://localhost:8104/v1/exchange/rates"),
        ("/v1/agent/messages/send", "http://localhost:8107/api/v1/agent/messages/send"),
        ("/v1/agent-coordinator/agents", "http://localhost:8107/v1/agents"),
        ("/v1/governance/proposals", "http://localhost:8105/v1/governance/proposals"),
        ("/v1/pool-hub/miners/heartbeat", "http://localhost:8210/v1/miners/heartbeat"),
        ("/v1/explorer/blocks/latest", "http://localhost:8100/api/blocks/latest"),
        ("/v1/plugin/register", "http://localhost:8203/v1/market/register"),
    ],
)
def test_route_rewrites_to_real_upstream_path(client, monkeypatch, path, expected_url):
    """Every registered prefix must forward to a path its backend actually serves."""
    capture = _CaptureClient()
    monkeypatch.setattr(client.app.state, "http_client", capture)
    response = client.get(path)

    assert response.status_code == 200
    assert capture.url == expected_url


def test_unknown_route_returns_404(client):
    """Unmatched paths are rejected with 404 rather than proxied to the coordinator.

    The old silent coordinator fallback (APP-48 in the v0.22 audit) let a typo'd
    path reach the coordinator; the gateway now returns an explicit 404.
    """
    response = client.get("/definitely-not-a-registered-prefix/xyz")

    assert response.status_code == 404


def test_escrow_prefix_forwards_to_rpc_escrow(client, monkeypatch):
    """`/v1/escrow/X` must forward to `<rpc>/escrow/X`, not `<rpc>/X`.

    The generic prefix-strip drops `v1/escrow`; without the rewrite entry the
    registered prefix could never reach the node's `/rpc/escrow/*` routes.
    """
    import httpx

    captured: dict[str, str] = {}

    class FakeClient:
        async def post(self, url, **kwargs):
            captured["url"] = url
            return httpx.Response(200, json={"ok": True})

        async def aclose(self):
            # Lifespan shutdown calls aclose() before monkeypatch restores the real client.
            pass

    # Patch the app the client actually serves — the module-level `app` name can
    # go stale when test_rate_limiting reloads api_gateway.main.
    monkeypatch.setattr(client.app.state, "http_client", FakeClient())
    response = client.post("/v1/escrow/create", json={})

    assert response.status_code == 200
    assert captured["url"].endswith("/rpc/escrow/create")
