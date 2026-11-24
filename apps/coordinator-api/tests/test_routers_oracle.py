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


@pytest.mark.unit
class TestSetPriceConfidenceValidation:
    """#2819: out-of-range/non-finite confidence must 422 at the edge."""

    def _admin(self):
        from aitbc.auth import create_access_token

        return {"Authorization": f"Bearer {create_access_token('admin-oracle', 'admin')}"}

    @pytest.mark.parametrize("bad", [2.0, -0.5, 1.0001])
    def test_set_price_rejects_out_of_range_confidence(self, client: TestClient, bad):
        resp = client.post(
            "/v1/oracle/price",
            json={"pair": "ETH/USD", "price": "3000", "confidence": bad},
            headers=self._admin(),
        )
        assert resp.status_code == 422
