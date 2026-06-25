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
        # Set a price first so it's available
        client.post("/v1/oracle/price", json={"pair": "ETH", "price": 3000.0, "source": "manual"})

        response = client.get("/v1/oracle/price/ETH")
        assert response.status_code == 200
        data = response.json()
        assert data["pair"] == "ETH"
        assert "price" in data
        assert "timestamp" in data
        assert data["source"] == "manual"

    def test_get_price_btc(self, client: TestClient):
        """Test getting BTC price"""
        # Set a price first
        client.post("/v1/oracle/price", json={"pair": "BTC", "price": 60000.0, "source": "manual"})

        response = client.get("/v1/oracle/price/BTC")
        assert response.status_code == 200
        data = response.json()
        assert data["pair"] == "BTC"
        assert "price" in data

    def test_get_price_aic_token(self, client: TestClient):
        """Test getting AIC token price"""
        # Set a price first
        client.post("/v1/oracle/price", json={"pair": "AIC", "price": 1.5, "source": "manual"})

        response = client.get("/v1/oracle/price/AIC")
        assert response.status_code == 200
        data = response.json()
        assert data["pair"] == "AIC"
        assert "price" in data

    def test_set_price(self, client: TestClient):
        """Test setting price (admin function)"""
        price_data = {"pair": "TEST", "price": 123.45, "source": "manual"}

        response = client.post("/v1/oracle/price", json=price_data)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["pair"] == "TEST"
        assert data["price"] == 123.45

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


@pytest.mark.integration
class TestOracleIntegration:
    """Integration tests for oracle feeds"""

    def test_price_update_and_retrieval(self, client: TestClient):
        """Test setting price and then retrieving it"""
        # Set a custom price
        client.post("/v1/oracle/price", json={"pair": "CUSTOM", "price": 999.99, "source": "test"})

        # Retrieve it
        response = client.get("/v1/oracle/price/CUSTOM")
        data = response.json()
        assert data["price"] == 999.99
