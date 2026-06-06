"""
Blockchain Utils Tests
Tests for blockchain utility functions
"""

import sys
from pathlib import Path
from unittest.mock import patch, Mock

# Add CLI path for imports
cli_path = Path("/opt/aitbc/cli")
if str(cli_path) not in sys.path:
    sys.path.insert(0, str(cli_path))

import pytest


class TestGetChainInfo:
    """Test get_chain_info function"""

    @patch('aitbc_cli.utils.blockchain.AITBCHTTPClient')
    def test_get_chain_info_success(self, mock_client):
        """Test successful chain info retrieval"""
        from aitbc_cli.utils.blockchain import get_chain_info
        
        mock_http_client = Mock()
        mock_http_client.get.side_effect = [
            {"supported_chains": ["ait-devnet", "ait-testnet"], "proposer_id": "node1"},
            {"height": 1000, "hash": "0xabc123", "timestamp": "2024-01-01T00:00:00", "tx_count": 50}
        ]
        mock_client.return_value = mock_http_client
        
        result = get_chain_info("http://localhost:8202")
        
        assert result is not None
        assert result['chain_id'] == "ait-devnet"
        assert result['height'] == 1000
        assert result['hash'] == "0xabc123"
        assert result['tx_count'] == 50

    @patch('aitbc_cli.utils.blockchain.AITBCHTTPClient')
    def test_get_chain_info_no_chains(self, mock_client):
        """Test chain info with no supported chains"""
        from aitbc_cli.utils.blockchain import get_chain_info
        
        mock_http_client = Mock()
        mock_http_client.get.side_effect = [
            {"supported_chains": [], "proposer_id": ""},
            {"height": 0, "hash": "", "timestamp": "N/A", "tx_count": 0}
        ]
        mock_client.return_value = mock_http_client
        
        result = get_chain_info("http://localhost:8202")
        
        assert result is not None
        assert result['chain_id'] == "ait-mainnet"  # Default fallback

    @patch('aitbc_cli.utils.blockchain.AITBCHTTPClient')
    def test_get_chain_info_network_error(self, mock_client):
        """Test chain info with network error"""
        from aitbc_cli.utils.blockchain import get_chain_info, NetworkError
        
        mock_http_client = Mock()
        mock_http_client.get.side_effect = NetworkError("Connection failed")
        mock_client.return_value = mock_http_client
        
        result = get_chain_info("http://localhost:8202")
        
        assert result is None

    @patch('aitbc_cli.utils.blockchain.AITBCHTTPClient')
    def test_get_chain_info_generic_error(self, mock_client):
        """Test chain info with generic error"""
        from aitbc_cli.utils.blockchain import get_chain_info
        
        mock_http_client = Mock()
        mock_http_client.get.side_effect = Exception("Unexpected error")
        mock_client.return_value = mock_http_client
        
        result = get_chain_info("http://localhost:8202")
        
        assert result is None


class TestGetNetworkStatus:
    """Test get_network_status function"""

    @patch('aitbc_cli.utils.blockchain.AITBCHTTPClient')
    def test_get_network_status_success(self, mock_client):
        """Test successful network status retrieval"""
        from aitbc_cli.utils.blockchain import get_network_status
        
        mock_http_client = Mock()
        mock_http_client.get.return_value = {
            "height": 1000,
            "hash": "0xabc123",
            "timestamp": "2024-01-01T00:00:00"
        }
        mock_client.return_value = mock_http_client
        
        result = get_network_status("http://localhost:8202")
        
        assert result is not None
        assert result['height'] == 1000
        assert result['hash'] == "0xabc123"

    @patch('aitbc_cli.utils.blockchain.AITBCHTTPClient')
    def test_get_network_status_network_error(self, mock_client):
        """Test network status with network error"""
        from aitbc_cli.utils.blockchain import get_network_status, NetworkError
        
        mock_http_client = Mock()
        mock_http_client.get.side_effect = NetworkError("Connection failed")
        mock_client.return_value = mock_http_client
        
        result = get_network_status("http://localhost:8202")
        
        assert result is None

    @patch('aitbc_cli.utils.blockchain.AITBCHTTPClient')
    def test_get_network_status_generic_error(self, mock_client):
        """Test network status with generic error"""
        from aitbc_cli.utils.blockchain import get_network_status
        
        mock_http_client = Mock()
        mock_http_client.get.side_effect = Exception("Unexpected error")
        mock_client.return_value = mock_http_client
        
        result = get_network_status("http://localhost:8202")
        
        assert result is None


class TestGetBlockchainAnalytics:
    """Test get_blockchain_analytics function"""

    @patch('aitbc_cli.utils.blockchain.AITBCHTTPClient')
    def test_get_analytics_blocks(self, mock_client):
        """Test blocks analytics"""
        from aitbc_cli.utils.blockchain import get_blockchain_analytics
        
        mock_http_client = Mock()
        mock_http_client.get.return_value = {
            "height": 1000,
            "hash": "0xabc123",
            "timestamp": "2024-01-01T00:00:00",
            "tx_count": 50
        }
        mock_client.return_value = mock_http_client
        
        result = get_blockchain_analytics("blocks", rpc_url="http://localhost:8202")
        
        assert result is not None
        assert result['type'] == "blocks"
        assert result['current_height'] == 1000
        assert result['status'] == "Active"

    def test_get_analytics_supply(self):
        """Test supply analytics"""
        from aitbc_cli.utils.blockchain import get_blockchain_analytics
        
        result = get_blockchain_analytics("supply")
        
        assert result is not None
        assert result['type'] == "supply"
        assert result['total_supply'] == "1000000000"
        assert result['status'] == "Available"

    def test_get_analytics_accounts(self):
        """Test accounts analytics"""
        from aitbc_cli.utils.blockchain import get_blockchain_analytics
        
        result = get_blockchain_analytics("accounts")
        
        assert result is not None
        assert result['type'] == "accounts"
        assert result['total_accounts'] == 3
        assert result['status'] == "Healthy"

    def test_get_analytics_unknown_type(self):
        """Test unknown analytics type"""
        from aitbc_cli.utils.blockchain import get_blockchain_analytics
        
        result = get_blockchain_analytics("unknown")
        
        assert result is not None
        assert result['type'] == "unknown"
        assert result['status'] == "Not implemented yet"

    @patch('aitbc_cli.utils.blockchain.AITBCHTTPClient')
    def test_get_analytics_error(self, mock_client):
        """Test analytics with error"""
        from aitbc_cli.utils.blockchain import get_blockchain_analytics
        
        mock_http_client = Mock()
        mock_http_client.get.side_effect = Exception("Unexpected error")
        mock_client.return_value = mock_http_client
        
        result = get_blockchain_analytics("blocks")
        
        assert result is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
