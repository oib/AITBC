"""Gateway-level authentication.

Separate module because REQUIRE_AUTH and API_KEY are read into module constants at import
time; the routing tests run with auth disabled via conftest, so enabling it needs a reload.
"""

import importlib

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


def test_proxy_requires_credentials(authed_gateway):
    response = authed_gateway.get("/v1/gpu/health")

    assert response.status_code == 401


def test_proxy_rejects_wrong_key(authed_gateway):
    """A supplied-but-wrong key is 403, distinct from 401 for no credentials at all.

    verify_auth draws that line deliberately, and compares with hmac.compare_digest so the
    check is constant-time.
    """
    response = authed_gateway.get("/v1/gpu/health", headers={"Authorization": "Bearer wrong-key"})

    assert response.status_code == 403


def test_proxy_accepts_correct_key(authed_gateway):
    """A valid key gets past the gateway; whatever the backend then answers is its own."""
    response = authed_gateway.get("/v1/gpu/health", headers={"Authorization": "Bearer test-gateway-key"})

    assert response.status_code != 401


def test_health_is_reachable_without_credentials(authed_gateway):
    """Health must stay open or orchestrators cannot probe the gateway."""
    response = authed_gateway.get("/health")

    assert response.status_code == 200
