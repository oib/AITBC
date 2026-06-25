"""
Tests for portfolio router (cross-wallet aggregation)
"""

import pytest
from fastapi.testclient import TestClient


@pytest.mark.unit
class TestPortfolioRouter:
    """Test portfolio router endpoints"""

    def test_portfolio_health(self, client: TestClient):
        """Test portfolio health endpoint"""
        response = client.get("/v1/portfolio/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ["healthy", "degraded"]
        assert "services" in data
        assert "timestamp" in data
