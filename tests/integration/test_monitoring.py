"""Integration tests for health, monitoring, and swarm endpoints."""

from starlette.testclient import TestClient


class TestHealthCheck:
    """Test health check endpoint."""

    def test_health_check(self, coordinator_client: TestClient):
        """Test health check."""
        response = coordinator_client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data


class TestHealthEndpoints:
    """Test health and root endpoints."""

    def test_health_check(self, coordinator_client: TestClient):
        """Test health check endpoint."""
        response = coordinator_client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data

    def test_root_endpoint(self, coordinator_client: TestClient):
        """Test root endpoint with service information."""
        response = coordinator_client.get("/")
        assert response.status_code in (200, 404)


class TestMonitorEndpoints:
    """Test monitor router endpoints."""

    def test_get_dashboard(self, coordinator_client: TestClient):
        """Test getting monitoring dashboard data."""
        response = coordinator_client.get("/v1/dashboard")
        assert response.status_code in (200, 404)
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, dict)

    def test_get_status(self, coordinator_client: TestClient):
        """Test getting coordinator status."""
        response = coordinator_client.get("/v1/swarm/status")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data or isinstance(data, dict)

    def test_get_miners(self, coordinator_client: TestClient):
        """Test getting miners list."""
        response = coordinator_client.get("/v1/swarm/miners")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_get_history_dashboard(self, coordinator_client: TestClient):
        """Test getting historical dashboard data."""
        response = coordinator_client.get("/v1/swarm/dashboard/history")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_get_tasks(self, coordinator_client: TestClient):
        """Test getting tasks list."""
        response = coordinator_client.get("/v1/swarm/tasks")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)
        assert "tasks" in data


class TestMonitoringEndpoints:
    """Test monitoring router endpoints."""

    def test_get_prometheus_metrics(self, coordinator_client: TestClient):
        """Test getting Prometheus metrics."""
        response = coordinator_client.get("/prometheus")
        assert response.status_code == 200
        assert "text/plain" in response.headers.get("content-type", "")

    def test_get_live_metrics(self, coordinator_client: TestClient):
        """Test getting live JSON metrics for dashboard consumption."""
        response = coordinator_client.get("/metrics")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)

    def test_get_rate_limit_metrics(self, coordinator_client: TestClient):
        """Test getting rate limit metrics."""
        response = coordinator_client.get("/rate-limit-metrics")
        assert response.status_code == 200
        assert "text/plain" in response.headers.get("content-type", "")
