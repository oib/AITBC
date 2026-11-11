"""APIGW-DEPTH-1 (#1581) residual pins: pre-auth env guard + dot segments.

Two latent defects from the index that had no fix on main:

- ``API_GATEWAY_PREAUTH_RATE_LIMIT`` was parsed inside the per-request
  dependency — a malformed value raised ``ValueError`` and 500'd every
  proxied request. The spec is now validated once at startup (bad value →
  error log + '60/minute' fallback) and ``check()`` itself falls back
  rather than raising.
- ``.``/``..`` path segments survived the prefix checks and httpx
  normalized them into a different upstream path than the matched prefix
  implied. ``_resolve_target`` now rejects them with 400.
"""

import importlib

import pytest
from fastapi.testclient import TestClient


def test_malformed_env_falls_back_at_reload(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("API_GATEWAY_PREAUTH_RATE_LIMIT", "banana")
    import api_gateway.main as gateway

    gateway = importlib.reload(gateway)
    try:
        assert gateway.PREAUTH_RATE_LIMIT == "60/minute"
    finally:
        monkeypatch.delenv("API_GATEWAY_PREAUTH_RATE_LIMIT", raising=False)
        importlib.reload(gateway)


def test_nonpositive_env_falls_back_at_reload(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("API_GATEWAY_PREAUTH_RATE_LIMIT", "0/minute")
    import api_gateway.main as gateway

    gateway = importlib.reload(gateway)
    try:
        assert gateway.PREAUTH_RATE_LIMIT == "60/minute"
    finally:
        monkeypatch.delenv("API_GATEWAY_PREAUTH_RATE_LIMIT", raising=False)
        importlib.reload(gateway)


def test_check_never_raises_on_bad_spec() -> None:
    import api_gateway.main as gateway

    limiter = gateway._PreAuthIpLimiter()
    for spec in ("banana", "0/minute", "-5/hour", "", "abc/def"):
        # Must return a bool, not raise — and a bad spec fails closed-ish:
        # the 60/minute fallback still allows the first 60 hits.
        assert limiter.check("10.0.0.1", spec) is True


def test_parse_rejects_nonpositive() -> None:
    import api_gateway.main as gateway

    with pytest.raises(ValueError):
        gateway._PreAuthIpLimiter._parse("0/minute")
    with pytest.raises(ValueError):
        gateway._PreAuthIpLimiter._parse("-3/second")
    assert gateway._PreAuthIpLimiter._parse("300/minute") == (300, 60.0)


def test_dot_segments_rejected_v2() -> None:
    import api_gateway.main as gateway

    for path in ("v2/market/../admin", "v2/market/./health", "v2/../market/health"):
        resolved = gateway._resolve_target(path)
        assert not isinstance(resolved, tuple), path
        assert resolved.status_code == 400, path


def test_dot_segments_rejected_v1() -> None:
    import api_gateway.main as gateway

    resolved = gateway._resolve_target("market/../admin/secret")
    assert not isinstance(resolved, tuple)
    assert resolved.status_code == 400


def test_normal_paths_still_resolve() -> None:
    import api_gateway.main as gateway

    resolved = gateway._resolve_target("v2/market/v1/market/offers")
    assert isinstance(resolved, tuple)
    service, url = resolved
    assert service == "market"
    assert url.endswith("/v1/market/offers")


def test_encoded_dot_segments_rejected_over_http(monkeypatch: pytest.MonkeyPatch) -> None:
    """%2e%2e decodes into the path parameter — the guard must catch it."""
    monkeypatch.setenv("API_GATEWAY_REQUIRE_AUTH", "false")
    import api_gateway.main as gateway

    gateway = importlib.reload(gateway)
    try:
        with TestClient(gateway.app) as client:
            resp = client.get("/v2/market/%2e%2e/admin")
            assert resp.status_code == 400, resp.text
    finally:
        monkeypatch.setenv("API_GATEWAY_REQUIRE_AUTH", "true")
        importlib.reload(gateway)
