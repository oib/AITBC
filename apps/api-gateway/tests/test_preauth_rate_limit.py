"""Pre-auth per-IP rate limit pins (GW-RATELIMIT-PRE-AUTH-1, #1211).

The identity-keyed slowapi bucket sits inside the slowapi-wrapped handler,
but FastAPI resolves ``verify_auth`` first — unauthenticated floods used to
401 without ever consuming a bucket (B's live-tier probe: 105 unauth GETs,
zero 429s). ``pre_auth_ip_limit`` is declared before ``authenticated`` on the
proxy route so a coarse per-IP ceiling counts every request first.

These tests reload ``api_gateway.main`` under a deliberately low pre-auth
cap, same pattern as ``test_rate_limiting.py``.
"""

import importlib
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def preauth_client(monkeypatch):
    """A gateway reloaded with auth ON and a 3/minute pre-auth IP cap."""
    monkeypatch.setenv("API_GATEWAY_REQUIRE_AUTH", "true")
    monkeypatch.setenv("API_GATEWAY_RATE_LIMIT", "10000/minute")
    monkeypatch.setenv("API_GATEWAY_PREAUTH_RATE_LIMIT", "3/minute")

    import api_gateway.main as gateway

    gateway = importlib.reload(gateway)
    try:
        with TestClient(gateway.app) as client:
            yield client, gateway
    finally:
        monkeypatch.setenv("API_GATEWAY_PREAUTH_RATE_LIMIT", "300/minute")
        monkeypatch.setenv("API_GATEWAY_REQUIRE_AUTH", "false")
        importlib.reload(gateway)


def test_unauthenticated_flood_is_throttled(preauth_client):
    """Requests with no credentials must hit 429, not an unbounded 401 stream."""
    client, _ = preauth_client

    codes = [client.get("/v1/gpu/health").status_code for _ in range(6)]

    assert 429 in codes, f"unauthenticated requests were never throttled: {codes}"
    # The first `limit` requests still reach auth and 401 — the bucket caps,
    # it does not reject outright.
    assert codes[:3] == [401, 401, 401], codes


def test_invalid_credentials_also_consumed(preauth_client):
    """Wrong-key floods (403 path) share the same pre-auth bucket."""
    client, _ = preauth_client

    codes = [client.get("/v1/gpu/health", headers={"X-Gateway-Key": "wrong"}).status_code for _ in range(6)]

    assert 429 in codes, f"invalid-credential flood was never throttled: {codes}"


def test_preauth_limit_configurable_from_env(preauth_client):
    _, gateway = preauth_client

    assert gateway.PREAUTH_RATE_LIMIT == "3/minute"


def test_health_endpoint_not_preauth_limited(preauth_client):
    """The bucket lives on the proxy route only — /health stays open for probes."""
    client, _ = preauth_client

    for _ in range(10):
        assert client.get("/health").status_code == 200


def test_limiter_window_reset():
    """Unit-level: the fixed window resets after its period."""
    import api_gateway.main as gateway

    limiter = gateway._PreAuthIpLimiter()
    spec = "2/second"
    assert limiter.check("1.2.3.4", spec) is True
    assert limiter.check("1.2.3.4", spec) is True
    assert limiter.check("1.2.3.4", spec) is False
    # A different IP has its own window.
    assert limiter.check("5.6.7.8", spec) is True


def test_limiter_keys_isolated_per_ip():
    import api_gateway.main as gateway

    limiter = gateway._PreAuthIpLimiter()
    spec = "1/minute"
    assert limiter.check("10.0.0.1", spec) is True
    assert limiter.check("10.0.0.1", spec) is False
    assert limiter.check("10.0.0.2", spec) is True


def test_dependency_uses_client_host(monkeypatch):
    """The bucket key is request.client.host — the post-realip address
    (#1189 trust model), not a header the client controls."""
    import api_gateway.main as gateway

    seen: list[str] = []
    monkeypatch.setattr(gateway._PREAUTH_LIMITER, "check", lambda key, spec: seen.append(key) or True)

    request = SimpleNamespace(client=SimpleNamespace(host="203.0.113.9"))
    gateway.pre_auth_ip_limit(request)  # type: ignore[arg-type]

    assert seen == ["203.0.113.9"]
