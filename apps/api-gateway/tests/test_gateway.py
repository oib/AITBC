"""
Test API Gateway routing
"""

import pytest
from fastapi.testclient import TestClient

from api_gateway.main import app


@pytest.fixture
def client():
    """Create test client for API Gateway"""
    return TestClient(app)


def test_gateway_health_check(client):
    """Test gateway health check endpoint"""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "api-gateway"


def test_service_registry(client):
    """Test service registry endpoint"""
    response = client.get("/services")
    assert response.status_code == 200
    data = response.json()
    assert "services" in data
    services = data["services"]
    assert isinstance(services, list)
    # Check that GPU service is registered
    gpu_service = next((s for s in services if s["name"] == "gpu"), None)
    assert gpu_service is not None
    assert gpu_service["url"] == "http://localhost:8101"
    assert "/gpu/*" in gpu_service["routes"]


def test_gpu_route_proxy(client):
    """Test that gateway proxies requests to GPU service"""
    # This test requires GPU service to be running
    # In CI, this would be mocked or services would be started
    response = client.get("/gpu/health")
    # May fail if service not running, but tests routing logic
    assert response.status_code in [200, 503]  # 503 if service down


def test_marketplace_route_proxy(client):
    """Test that gateway proxies requests to Marketplace service"""
    response = client.get("/marketplace/health")
    assert response.status_code in [200, 503]


def test_trading_route_proxy(client):
    """Test that gateway proxies requests to Trading service"""
    response = client.get("/trading/health")
    assert response.status_code in [200, 503]


def test_governance_route_proxy(client):
    """Test that gateway proxies requests to Governance service"""
    response = client.get("/governance/health")
    assert response.status_code in [200, 503]


def test_unknown_route(client):
    """Test that unknown routes return 404"""
    response = client.get("/unknown/path")
    assert response.status_code == 404
