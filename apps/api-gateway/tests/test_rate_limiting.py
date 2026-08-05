"""Rate limiting is actually enforced on the proxy route.

The limiter, its 429 handler and app.state.limiter were all wired up, but the
`rate_limit()` decorator was applied to no route -- so every request passed unthrottled
while the code read as though it were protected. These tests fail if that detaches again.

The gateway reads RATE_LIMIT into a module constant at import time, so this module
reloads `api_gateway.main` under a deliberately low limit rather than sharing the
high-limit app the routing tests use.
"""

import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def throttled_client(monkeypatch):
    """A gateway reloaded with a 3/minute cap."""
    monkeypatch.setenv("API_GATEWAY_REQUIRE_AUTH", "false")
    monkeypatch.setenv("API_GATEWAY_RATE_LIMIT", "3/minute")

    import api_gateway.main as gateway

    gateway = importlib.reload(gateway)
    try:
        with TestClient(gateway.app) as client:
            yield client, gateway
    finally:
        # Restore the shared module state for any test importing it afterwards.
        importlib.reload(gateway)


def test_limit_is_configurable_from_env(throttled_client):
    _, gateway = throttled_client

    assert gateway.RATE_LIMIT == "3/minute"


def test_requests_beyond_the_limit_get_429(throttled_client):
    client, _ = throttled_client

    codes = [client.get("/v1/gpu/health").status_code for _ in range(6)]

    assert 429 in codes, f"no request was throttled: {codes}"


def test_requests_within_the_limit_are_not_throttled(throttled_client):
    client, _ = throttled_client

    first_three = [client.get("/v1/gpu/health").status_code for _ in range(3)]

    assert 429 not in first_three, f"throttled below the configured limit: {first_three}"


def test_throttled_response_body_identifies_the_cause(throttled_client):
    client, _ = throttled_client

    for _ in range(6):
        response = client.get("/v1/gpu/health")
        if response.status_code == 429:
            assert response.json()["error"] == "Rate limit exceeded"
            return

    pytest.fail("never received a 429 to inspect")


def test_limiter_is_attached_to_the_app(throttled_client):
    """app.state.limiter must be set, or slowapi's 429 handler cannot resolve it."""
    _, gateway = throttled_client

    assert getattr(gateway.app.state, "limiter", None) is not None
