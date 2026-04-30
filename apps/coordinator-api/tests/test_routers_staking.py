"""
Tests for staking router
"""

import pytest
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient


@pytest.mark.unit
class TestStakingRouter:
    """Test staking router endpoints"""

    @patch('app.routers.staking.AITBCHTTPClient')
    def test_staking_info(self, mock_client_class):
        """Test getting staking information"""
        # Setup mock
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.get.return_value = {
            "total_staked": 1000000.0,
            "apy": 0.15,
            "validators": 100
        }

        # Import and test
        from app.routers.staking import router
        from app.main import create_app
        
        app = create_app()
        app.include_router(router)
        client = TestClient(app)
        
        response = client.get("/staking/info")
        assert response.status_code == 200
        data = response.json()
        assert data["total_staked"] == 1000000.0
        assert data["apy"] == 0.15

    @patch('app.routers.staking.AITBCHTTPClient')
    def test_staking_stake(self, mock_client_class):
        """Test staking tokens"""
        # Setup mock
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.post.return_value = {
            "stake_id": "stake1",
            "amount": 1000.0,
            "status": "staked"
        }

        # Import and test
        from app.routers.staking import router
        from app.main import create_app
        
        app = create_app()
        app.include_router(router)
        client = TestClient(app)
        
        response = client.post("/staking/stake", json={
            "amount": 1000.0,
            "validator": "validator1"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "staked"
