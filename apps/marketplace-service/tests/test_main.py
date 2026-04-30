"""
Test Marketplace service main application
"""

import pytest
from fastapi.testclient import TestClient

from marketplace_service.main import app


@pytest.fixture
def client():
    """Create test client for Marketplace service"""
    return TestClient(app)


def test_health_check(client):
    """Test health check endpoint"""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "marketplace-service"


def test_marketplace_status(client):
    """Test marketplace status endpoint"""
    response = client.get("/marketplace/status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "operational"
    assert data["service"] == "marketplace-service"


def test_get_marketplace_offers(client):
    """Test get marketplace offers endpoint"""
    response = client.get("/v1/marketplace/offers")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_get_marketplace_bids(client):
    """Test get marketplace bids endpoint"""
    response = client.get("/v1/marketplace/bids")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_get_marketplace_analytics(client):
    """Test get marketplace analytics endpoint"""
    response = client.get("/v1/marketplace/analytics")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)
