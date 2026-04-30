"""
Tests for staking service
"""

import pytest
from unittest.mock import Mock, patch


@pytest.mark.unit
class TestStakingService:
    """Test staking service"""

    @patch('app.services.staking_service.AITBCHTTPClient')
    def test_get_staking_info(self, mock_client_class):
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
        from app.services.staking_service import get_staking_info
        
        result = get_staking_info()
        assert result["total_staked"] == 1000000.0
        assert result["apy"] == 0.15

    @patch('app.services.staking_service.AITBCHTTPClient')
    def test_stake_tokens(self, mock_client_class):
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
        from app.services.staking_service import stake_tokens
        
        result = stake_tokens({"amount": 1000.0, "validator": "validator1"})
        assert result["status"] == "staked"
