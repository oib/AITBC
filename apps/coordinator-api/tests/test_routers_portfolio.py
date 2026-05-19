"""
Tests for portfolio router (cross-wallet aggregation)
"""

import pytest
from fastapi.testclient import TestClient


@pytest.mark.unit
class TestPortfolioRouter:
    """Test portfolio router endpoints"""

    def test_get_portfolio_by_user(self, client: TestClient):
        """Test getting portfolio by user ID"""
        response = client.get("/portfolio/user/test-user-001")
        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == "test-user-001"
        assert "wallets" in data
        assert "total_balance_usd" in data
        assert "chains" in data

    def test_get_portfolio_by_wallet(self, client: TestClient):
        """Test getting portfolio by wallet address"""
        response = client.get("/portfolio/wallet/0x1234567890123456789012345678901234567890")
        assert response.status_code == 200
        data = response.json()
        assert "wallet_address" in data
        assert "balance" in data
        assert "tokens" in data

    def test_get_portfolio_breakdown(self, client: TestClient):
        """Test getting detailed portfolio breakdown"""
        response = client.get("/portfolio/breakdown/test-user-001")
        assert response.status_code == 200
        data = response.json()
        assert "user_id" in data
        assert "wallet_breakdown" in data
        assert "chain_breakdown" in data
        assert "token_breakdown" in data

    def test_get_supported_chains(self, client: TestClient):
        """Test getting list of supported chains"""
        response = client.get("/portfolio/chains")
        assert response.status_code == 200
        data = response.json()
        assert "chains" in data
        assert "count" in data
        # Should have at least main chain
        assert data["count"] >= 1

    def test_portfolio_health(self, client: TestClient):
        """Test portfolio health endpoint"""
        response = client.get("/portfolio/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "supported_chains" in data


@pytest.mark.integration
class TestPortfolioIntegration:
    """Integration tests for portfolio aggregation"""

    def test_cross_wallet_aggregation(self, client: TestClient):
        """Test that portfolio aggregates multiple wallets correctly"""
        # This would require setting up multiple wallets for a user
        # For now, just verify the structure is correct
        response = client.get("/portfolio/user/multi-wallet-user")
        data = response.json()
        
        # Verify totals are calculated
        assert "total_balance_usd" in data
        assert "total_staked_usd" in data
        assert "total_rewards_usd" in data
        
        # Verify chain breakdown sums match totals
        if data.get("chains"):
            chain_sum = sum(c.get("balance_usd", 0) for c in data["chains"])
            assert abs(chain_sum - data["total_balance_usd"]) < 0.01
