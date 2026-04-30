"""
Test GPU service main application
"""

import pytest
from fastapi.testclient import TestClient

from gpu_service.main import app


@pytest.fixture
def client():
    """Create test client for GPU service"""
    return TestClient(app)


def test_health_check(client):
    """Test health check endpoint"""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "gpu-service"


def test_gpu_status(client):
    """Test GPU status endpoint"""
    response = client.get("/gpu/status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "operational"
    assert data["service"] == "gpu-service"


def test_get_consumer_gpu_profiles(client):
    """Test get consumer GPU profiles endpoint"""
    response = client.get("/v1/marketplace/edge-gpu/profiles")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    # Check that at least one profile is returned
    assert len(data) > 0
    # Check that profile has required fields
    profile = data[0]
    assert "profile_id" in profile
    assert "name" in profile
    assert "architecture" in profile
