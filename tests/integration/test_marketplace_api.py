"""
Marketplace Service Integration Tests (using TestClient)
Tests the complete API functionality without requiring running services
Note: Some endpoints require database setup and are marked as expected to fail

Note: The marketplace_service package was removed/refactored during the
v0.5.x context migration. These tests are skipped until the marketplace
service is reintroduced in the current architecture.
"""

import os

import pytest
from starlette.testclient import TestClient

pytestmark = pytest.mark.skip(reason="marketplace_service package not available in current architecture")


class TestMarketplaceAPI:
    """Test Marketplace Service API endpoints"""

    @pytest.fixture
    def client(self):
        """Create test client for marketplace service"""
        import sys

        sys.path.insert(0, "/opt/aitbc/apps/marketplace/src")
        # Set required env vars
        os.environ.setdefault("MARKETPLACE_BIND_PORT", "8102")
        from marketplace_service.main import app

        return TestClient(app)

    def test_health_endpoint(self, client: TestClient):
        """Test health check endpoint"""
        response = client.get("/health")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "marketplace-service"

    def test_ready_endpoint(self, client: TestClient):
        """Test readiness check endpoint"""
        response = client.get("/ready")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "ready"

    def test_live_endpoint(self, client: TestClient):
        """Test liveness check endpoint"""
        response = client.get("/live")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "alive"

    def test_metrics_endpoint(self, client: TestClient):
        """Test Prometheus metrics endpoint"""
        response = client.get("/metrics")
        assert response.status_code == 200
        assert "text/plain" in response.headers.get("content-type", "")

    @pytest.mark.skip(reason="Requires database connection")
    def test_offers_list_endpoint(self, client: TestClient):
        """Test offers listing endpoint"""
        response = client.get("/v1/marketplace/offers")
        assert response.status_code == 200

    @pytest.mark.skip(reason="Requires database connection")
    def test_analytics_endpoint(self, client: TestClient):
        """Test analytics endpoint"""
        response = client.get("/v1/marketplace/analytics")
        assert response.status_code == 200

    @pytest.mark.skip(reason="Requires database connection")
    def test_marketplace_info_endpoint(self, client: TestClient):
        """Test marketplace info endpoint"""
        response = client.get("/v1/marketplace")
        assert response.status_code == 200


class TestMarketplaceErrorHandling:
    """Test Marketplace API error handling"""

    @pytest.fixture
    def client(self):
        """Create test client for marketplace service"""
        import sys

        sys.path.insert(0, "/opt/aitbc/apps/marketplace/src")
        os.environ.setdefault("MARKETPLACE_BIND_PORT", "8102")
        from marketplace_service.main import app

        return TestClient(app)

    @pytest.mark.skip(reason="Requires database connection")
    def test_nonexistent_offer(self, client: TestClient):
        """Test requesting nonexistent offer"""
        response = client.get("/v1/marketplace/offers/nonexistent-offer-123")
        assert response.status_code == 404


class TestMarketplacePerformance:
    """Test Marketplace API performance"""

    @pytest.fixture
    def client(self):
        """Create test client for marketplace service"""
        import sys

        sys.path.insert(0, "/opt/aitbc/apps/marketplace/src")
        os.environ.setdefault("MARKETPLACE_BIND_PORT", "8102")
        from marketplace_service.main import app

        return TestClient(app)

    def test_response_times(self, client: TestClient):
        """Test API response times"""
        import time

        endpoints = ["/health", "/ready", "/live", "/metrics"]

        for endpoint in endpoints:
            start_time = time.time()
            response = client.get(endpoint)
            end_time = time.time()

            assert response.status_code == 200
            response_time = end_time - start_time
            assert response_time < 1.0  # Should respond within 1 second


if __name__ == "__main__":
    pytest.main([__file__])
