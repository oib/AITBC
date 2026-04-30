"""
Tests for blockchain service
"""

import pytest
from unittest.mock import Mock, patch


@pytest.mark.unit
class TestBlockchainService:
    """Test blockchain service"""

    @patch('app.services.blockchain.AITBCHTTPClient')
    def test_get_block_height(self, mock_client_class):
        """Test getting current block height"""
        # Setup mock
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.get.return_value = {"height": 1000}

        # Import and test
        from app.services.blockchain import get_block_height
        
        result = get_block_height()
        assert result == 1000

    @patch('app.services.blockchain.AITBCHTTPClient')
    def test_get_block_by_hash(self, mock_client_class):
        """Test getting block by hash"""
        # Setup mock
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.get.return_value = {
            "hash": "0xabc123",
            "height": 1000,
            "timestamp": "2024-01-01T00:00:00Z"
        }

        # Import and test
        from app.services.blockchain import get_block_by_hash
        
        result = get_block_by_hash("0xabc123")
        assert result["hash"] == "0xabc123"
        assert result["height"] == 1000
