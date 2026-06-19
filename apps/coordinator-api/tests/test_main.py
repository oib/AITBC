"""Tests for main app endpoints and lifecycle."""


def test_health_endpoint(client):
    """Test health endpoint returns 200."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data


def test_metrics_endpoint_json(client):
    """Test /metrics returns JSON metrics."""
    response = client.get("/metrics")
    assert response.status_code == 200
    data = response.json()
    assert "api_requests" in data


def test_prometheus_endpoint(client):
    """Test /prometheus returns Prometheus format."""
    response = client.get("/prometheus")
    assert response.status_code == 200
    assert "python_gc" in response.text or "# HELP" in response.text


def test_docs_endpoint(client):
    """Test docs endpoint is accessible."""
    response = client.get("/docs")
    assert response.status_code == 200
    assert "swagger" in response.text.lower() or "openapi" in response.text.lower()


def test_openapi_endpoint(client):
    """Test OpenAPI schema endpoint."""
    response = client.get("/openapi.json")
    assert response.status_code == 200
    data = response.json()
    assert "openapi" in data
    assert "paths" in data
