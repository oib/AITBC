"""
Tests for oracle router (data feeds)
"""

import pytest
from fastapi.testclient import TestClient


@pytest.mark.unit
class TestOracleRouter:
    """Test oracle router endpoints"""

    def test_get_price(self, client: TestClient):
        """Test getting asset price"""
        response = client.get("/oracle/price/ETH")
        assert response.status_code == 200
        data = response.json()
        assert data["asset"] == "ETH"
        assert "price" in data
        assert "timestamp" in data
        assert data["source"] == "chainlink"

    def test_get_price_btc(self, client: TestClient):
        """Test getting BTC price"""
        response = client.get("/oracle/price/BTC")
        assert response.status_code == 200
        data = response.json()
        assert data["asset"] == "BTC"
        assert "price" in data

    def test_get_price_aic_token(self, client: TestClient):
        """Test getting AIC token price"""
        response = client.get("/oracle/price/AIC")
        assert response.status_code == 200
        data = response.json()
        assert data["asset"] == "AIC"
        assert "price" in data

    def test_set_price(self, client: TestClient):
        """Test setting price (admin function)"""
        price_data = {
            "asset": "TEST",
            "price": 123.45,
            "source": "manual"
        }

        response = client.post("/oracle/price", json=price_data)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["asset"] == "TEST"
        assert data["price"] == 123.45

    def test_get_all_prices(self, client: TestClient):
        """Test getting all tracked prices"""
        response = client.get("/oracle/prices")
        assert response.status_code == 200
        data = response.json()
        assert "prices" in data
        assert "count" in data
        # Should have at least the default assets
        assert data["count"] >= 3

    def test_get_price_history(self, client: TestClient):
        """Test getting price history"""
        response = client.get("/oracle/history/ETH?limit=10")
        assert response.status_code == 200
        data = response.json()
        assert data["asset"] == "ETH"
        assert "history" in data
        assert len(data["history"]) <= 10

    def test_oracle_health(self, client: TestClient):
        """Test oracle health endpoint"""
        response = client.get("/oracle/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "tracked_assets" in data


@pytest.mark.integration
class TestOracleIntegration:
    """Integration tests for oracle feeds"""

    def test_price_update_and_retrieval(self, client: TestClient):
        """Test setting price and then retrieving it"""
        # Set a custom price
        client.post("/oracle/price", json={
            "asset": "CUSTOM",
            "price": 999.99,
            "source": "test"
        })

        # Retrieve it
        response = client.get("/oracle/price/CUSTOM")
        data = response.json()
        assert data["price"] == 999.99
