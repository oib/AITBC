"""Gateway-level authentication.

Separate module because REQUIRE_AUTH and API_KEY are read into module constants at import
time; the routing tests run with auth disabled via conftest, so enabling it needs a reload.
"""

import importlib

import httpx
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def authed_gateway(monkeypatch):
    """A gateway reloaded with authentication required and a known key."""
    monkeypatch.setenv("API_GATEWAY_REQUIRE_AUTH", "true")
    monkeypatch.setenv("API_GATEWAY_KEY", "test-gateway-key")
    monkeypatch.setenv("API_GATEWAY_RATE_LIMIT", "10000/minute")

    import api_gateway.main as gateway

    gateway = importlib.reload(gateway)
    try:
        with TestClient(gateway.app) as client:
            yield client
    finally:
        importlib.reload(gateway)


class _CaptureClient:
    """Records the forwarded request; satisfies lifespan aclose."""

    def __init__(self):
        self.headers: dict[str, str] = {}

    async def get(self, url, **kwargs):
        self.headers = kwargs.get("headers", {})
        return httpx.Response(200, json={"ok": True})

    async def aclose(self):
        pass


def test_proxy_requires_credentials(authed_gateway):
    response = authed_gateway.get("/v1/coordinator/health")

    assert response.status_code == 401


def test_proxy_rejects_wrong_key(authed_gateway):
    """A supplied-but-wrong key is 403, distinct from 401 for no credentials at all.

    verify_auth draws that line deliberately, and compares with hmac.compare_digest so the
    check is constant-time.
    """
    response = authed_gateway.get("/v1/coordinator/health", headers={"X-Gateway-Key": "wrong-key"})

    assert response.status_code == 403


def test_proxy_accepts_gateway_key_header(authed_gateway):
    """X-Gateway-Key is the canonical credential."""
    response = authed_gateway.get("/v1/coordinator/health", headers={"X-Gateway-Key": "test-gateway-key"})

    assert response.status_code != 401


def test_proxy_accepts_bearer_alias(authed_gateway):
    """Bearer carrying the gateway key still works for existing callers."""
    response = authed_gateway.get("/v1/coordinator/health", headers={"Authorization": "Bearer test-gateway-key"})

    assert response.status_code != 401


def test_gateway_key_is_not_forwarded(authed_gateway, monkeypatch):
    """The gateway credential must not leak upstream in either header."""
    import api_gateway.main as gateway

    capture = _CaptureClient()
    monkeypatch.setattr(gateway.app.state, "http_client", capture)
    authed_gateway.get("/v1/coordinator/health", headers={"X-Gateway-Key": "test-gateway-key"})

    assert "x-gateway-key" not in capture.headers
    assert "authorization" not in capture.headers


def test_bearer_alias_is_not_forwarded(authed_gateway, monkeypatch):
    """Bearer carrying the *gateway* key is stripped — upstreams expect their own token."""
    import api_gateway.main as gateway

    capture = _CaptureClient()
    monkeypatch.setattr(gateway.app.state, "http_client", capture)
    authed_gateway.get("/v1/coordinator/health", headers={"Authorization": "Bearer test-gateway-key"})

    assert "authorization" not in capture.headers


def test_service_jwt_passes_through(authed_gateway, monkeypatch):
    """Gateway key + a service Bearer token stack: the JWT reaches the upstream."""
    import api_gateway.main as gateway

    capture = _CaptureClient()
    monkeypatch.setattr(gateway.app.state, "http_client", capture)
    authed_gateway.get(
        "/v1/coordinator/health",
        headers={"X-Gateway-Key": "test-gateway-key", "Authorization": "Bearer service-jwt"},
    )

    assert capture.headers.get("authorization") == "Bearer service-jwt"


def test_health_is_reachable_without_credentials(authed_gateway):
    """Health must stay open or orchestrators cannot probe the gateway."""
    response = authed_gateway.get("/health")

    assert response.status_code == 200
