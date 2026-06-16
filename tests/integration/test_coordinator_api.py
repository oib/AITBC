"""
Coordinator API Integration Tests (using TestClient)
Tests the complete API functionality without requiring running services
Note: Some endpoints require database setup and are marked as expected to fail
"""

import pytest
from starlette.testclient import TestClient
import os


class TestCoordinatorAPI:
    """Test Coordinator API endpoints"""

    @pytest.fixture
    def client(self):
        """Create test client for coordinator API"""
        import sys
        sys.path.insert(0, '/opt/aitbc/apps/coordinator-api/src')
        # Set required env vars
        os.environ.setdefault("COORDINATOR_API_KEY", "test-key")
        os.environ.setdefault("COORDINATOR_API_BIND_HOST", "127.0.0.1")
        os.environ.setdefault("COORDINATOR_API_PORT", "8203")
        os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
        os.environ.setdefault("REDIS_URL", "redis://localhost:6379/1")
        os.environ.setdefault("SECRET_KEY", "test-secret-key-that-is-at-least-32-chars-long")
        os.environ.setdefault("TEST_ADMIN_PASSWORD", "test-admin-password")
        from app.main import app
        return TestClient(app)

    def test_health_endpoint(self, client: TestClient):
        """Test health check endpoint"""
        response = client.get("/health")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "ok"
        assert "env" in data
        assert "python_version" in data

    def test_metrics_endpoint(self, client: TestClient):
        """Test Prometheus metrics endpoint"""
        # /metrics redirects to /metrics/
        response = client.get("/metrics", follow_redirects=True)
        assert response.status_code == 200
        assert "text/plain" in response.headers.get("content-type", "")

    def test_metrics_direct_endpoint(self, client: TestClient):
        """Test Prometheus metrics endpoint directly"""
        response = client.get("/metrics/")
        assert response.status_code == 200
        assert "text/plain" in response.headers.get("content-type", "")


class TestCoordinatorAPIErrorHandling:
    """Test Coordinator API error handling"""

    @pytest.fixture
    def client(self):
        """Create test client for coordinator API"""
        import sys
        sys.path.insert(0, '/opt/aitbc/apps/coordinator-api/src')
        os.environ.setdefault("COORDINATOR_API_KEY", "test-key")
        os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
        os.environ.setdefault("REDIS_URL", "redis://localhost:6379/1")
        os.environ.setdefault("SECRET_KEY", "test-secret-key-that-is-at-least-32-chars-long")
        os.environ.setdefault("TEST_ADMIN_PASSWORD", "test-admin-password")
        from app.main import app
        return TestClient(app)

    def test_nonexistent_endpoint(self, client: TestClient):
        """Test requesting nonexistent endpoint"""
        response = client.get("/v1/agents/nonexistent_agent")
        assert response.status_code == 404

    def test_invalid_root_endpoint(self, client: TestClient):
        """Test root endpoint returns 404"""
        response = client.get("/")
        assert response.status_code == 404


class TestCoordinatorAPIPerformance:
    """Test Coordinator API performance"""

    @pytest.fixture
    def client(self):
        """Create test client for coordinator API"""
        import sys
        sys.path.insert(0, '/opt/aitbc/apps/coordinator-api/src')
        os.environ.setdefault("COORDINATOR_API_KEY", "test-key")
        os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
        os.environ.setdefault("REDIS_URL", "redis://localhost:6379/1")
        os.environ.setdefault("SECRET_KEY", "test-secret-key-that-is-at-least-32-chars-long")
        os.environ.setdefault("TEST_ADMIN_PASSWORD", "test-admin-password")
        from app.main import app
        return TestClient(app)

    def test_healthy_endpoints_response_times(self, client: TestClient):
        """Test API response times for healthy endpoints"""
        import time

        endpoints = [
            "/health",
            "/metrics/"
        ]

        for endpoint in endpoints:
            start_time = time.time()
            response = client.get(endpoint, follow_redirects=True)
            end_time = time.time()
            if response.status_code == 200:
                response_time = end_time - start_time
                assert response_time < 1.0  # Should respond within 1 second


if __name__ == "__main__":
    pytest.main([__file__])