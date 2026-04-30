"""
Test Trading service main application
"""

import pytest
from fastapi.testclient import TestClient

from trading_service.main import app


@pytest.fixture
def client():
    """Create test client for Trading service"""
    return TestClient(app)


def test_health_check(client):
    """Test health check endpoint"""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "trading-service"


def test_trading_status(client):
    """Test trading status endpoint"""
    response = client.get("/trading/status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "operational"
    assert data["service"] == "trading-service"


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
