"""
Test Trading service main application
"""

import pytest
from fastapi.testclient import TestClient

from trading_service.dependencies import require_trading_api_key

GATE_KEY = "gate-test-key"


def test_health_check(client):
    """Test health check endpoint"""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "trading"


def test_metrics_endpoint(client):
    """Test Prometheus metrics endpoint"""
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "text/plain" in response.headers.get("content-type", "")


def test_trading_status(client):
    """Test trading status endpoint"""
    response = client.get("/v1/trading/status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "operational"
    assert data["service"] == "trading"


def test_get_trade_requests(client):
    """Test get trade requests endpoint"""
    response = client.get("/v1/trading/requests")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_get_trade_matches(client):
    """Test get trade matches endpoint"""
    response = client.get("/v1/trading/matches")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_get_trade_agreements(client):
    """Test get trade agreements endpoint"""
    response = client.get("/v1/trading/agreements")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_get_trading_analytics(client):
    """Test get trading analytics endpoint"""
    response = client.get("/v1/trading/analytics")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)


@pytest.fixture
def anon_client():
    from trading_service.main import app

    return TestClient(app)


@pytest.fixture
def gate_key(monkeypatch):
    monkeypatch.setattr(require_trading_api_key, "expected_key", GATE_KEY)
    return GATE_KEY


def test_protected_route_rejects_missing_key(anon_client, gate_key):
    response = anon_client.get("/v1/trading/inter-chain", params={"limit": 1})
    assert response.status_code == 401


def test_protected_route_rejects_wrong_key(anon_client, gate_key):
    response = anon_client.get(
        "/v1/trading/inter-chain",
        params={"limit": 1},
        headers={"X-Trading-Api-Key": "wrong-key"},
    )
    assert response.status_code == 401


def test_protected_route_rejects_rpc_key_header(anon_client, gate_key):
    response = anon_client.get(
        "/v1/trading/inter-chain",
        params={"limit": 1},
        headers={"X-API-Key": gate_key},
    )
    assert response.status_code == 401


def test_protected_route_accepts_trading_key(client, gate_key):
    response = client.get(
        "/v1/trading/inter-chain",
        params={"limit": 1},
        headers={"X-Trading-Api-Key": gate_key},
    )
    assert response.status_code == 200


def test_settlement_status_unknown_trade_is_404_not_401(client, gate_key):
    response = client.get(
        "/v1/trading/trades/nonexistent-auth-test/settlement-status",
        headers={"X-Trading-Api-Key": gate_key},
    )
    assert response.status_code == 404


def test_gate_returns_501_when_server_key_unconfigured(anon_client, monkeypatch):
    monkeypatch.setattr(require_trading_api_key, "expected_key", None)
    response = anon_client.get(
        "/v1/trading/inter-chain",
        params={"limit": 1},
        headers={"X-Trading-Api-Key": "anything"},
    )
    assert response.status_code == 501


def test_health_is_public(anon_client):
    response = anon_client.get("/health")
    assert response.status_code == 200


@pytest.mark.parametrize(
    "path",
    [
        "/v1/trading/requests",
        "/v1/transactions",
        "/v1/trading/inter-chain",
        "/v1/trading/offers/sync-status",
        "/v1/trading/offers/subscription-status",
        "/v1/trading/trades/nonexistent-auth-test/settlement-status",
    ],
)
def test_every_protected_router_rejects_missing_key(anon_client, gate_key, path):
    assert anon_client.get(path).status_code == 401
