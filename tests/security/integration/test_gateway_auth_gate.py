"""Security pins — api-gateway auth gate (#1189-adjacent edge trust boundary).

The gateway is the public edge for ``/api/*``: every request must carry the
shared ``X-Gateway-Key`` (or legacy Bearer alias) before any proxying
happens. These pins lock the gate itself — missing credentials → 401, wrong
credential → 403, correct key → request proceeds past auth (upstream is
unreachable in tests, so success is asserted as "not an auth rejection").

``API_GATEWAY_REQUIRE_AUTH`` defaults to ``true`` and is not overridden here;
``API_GATEWAY_KEY`` is pinned in conftest.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import api_gateway.main as gw


@pytest.fixture
def gateway_client():
    return TestClient(gw.app)


def test_missing_credentials_get_401(gateway_client):
    resp = gateway_client.get("/api/v1/health")
    assert resp.status_code == 401


def test_wrong_gateway_key_gets_403(gateway_client):
    resp = gateway_client.get("/api/v1/health", headers={"X-Gateway-Key": "wrong-key"})
    assert resp.status_code == 403


def test_correct_key_passes_auth_gate(gateway_client):
    """Right key must get PAST auth — upstream is unreachable in tests, so
    any non-401/403 status proves the gate opened."""
    resp = gateway_client.get("/api/v1/health", headers={"X-Gateway-Key": "test-gateway-key-not-a-secret"})
    assert resp.status_code not in (401, 403)


def test_bearer_alias_with_gateway_key_accepted(gateway_client):
    resp = gateway_client.get(
        "/api/v1/health",
        headers={"Authorization": "Bearer test-gateway-key-not-a-secret"},
    )
    assert resp.status_code not in (401, 403)


def test_empty_key_never_authenticates(gateway_client):
    resp = gateway_client.get("/api/v1/health", headers={"X-Gateway-Key": ""})
    assert resp.status_code in (401, 403)
