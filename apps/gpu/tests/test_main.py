"""
Test GPU service main application
"""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Add the gpu src directory to the path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from gpu_service.main import app  # noqa: E402


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
    response = client.get("/v1/gpu/status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "operational"
    assert data["service"] == "gpu-service"


def test_get_consumer_gpu_profiles(client):
    """Test get consumer GPU profiles endpoint"""
    response = client.get(
        "/v1/marketplace/edge-gpu/profiles",
        params={"architecture": "ampere", "edge_optimized": True, "min_memory_gb": 8},
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    # Check that at least one profile is returned
    assert len(data) > 0
    # Check that profile has required fields (matches ConsumerGPUProfile model)
    profile = data[0]
    assert "id" in profile
    assert "gpu_model" in profile
    assert "architecture" in profile
