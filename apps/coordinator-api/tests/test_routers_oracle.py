"""
Tests for oracle router (data feeds)
"""

import pytest
from fastapi.testclient import TestClient


@pytest.mark.unit
class TestOracleRouter:
    """Test oracle router endpoints"""

    def test_get_all_prices(self, client: TestClient):
        """Test getting all tracked prices"""
        response = client.get("/v1/oracle/prices")
        assert response.status_code == 200
        data = response.json()
        assert "prices" in data
        assert "count" in data

    def test_oracle_health(self, client: TestClient):
        """Test oracle health endpoint"""
        response = client.get("/v1/oracle/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "oracle"
