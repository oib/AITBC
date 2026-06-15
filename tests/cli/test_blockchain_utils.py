"""
Tests for blockchain utility functions
"""

from unittest.mock import Mock, patch

import pytest
from aitbc_cli.utils.blockchain import (
    get_blockchain_analytics,
    get_chain_info,
    get_network_status,
)

from aitbc import NetworkError


class TestGetChainInfo:
    """Test get_chain_info function"""

    @patch("aitbc_cli.utils.blockchain.AITBCHTTPClient")
    def test_get_chain_info_success(self, mock_client_class):
        """Test successful chain info retrieval"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        mock_client.get.side_effect = [
            {"supported_chains": ["ait-mainnet", "ait-testnet"], "proposer_id": "node1"},
            {"height": 1000, "hash": "0xabc123", "timestamp": "2024-01-01T00:00:00Z", "tx_count": 50},
        ]

        result = get_chain_info("http://localhost:8202")

        assert result is not None
        assert result["chain_id"] == "ait-mainnet"
        assert result["supported_chains"] == "ait-mainnet, ait-testnet"
        assert result["height"] == 1000
        assert result["hash"] == "0xabc123"
        assert result["tx_count"] == 50

    @patch("aitbc_cli.utils.blockchain.AITBCHTTPClient")
    def test_get_chain_info_empty_chains(self, mock_client_class):
        """Test chain info with empty chains list"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        mock_client.get.side_effect = [
            {"supported_chains": [], "proposer_id": ""},
            {"height": 0, "hash": "", "timestamp": "N/A", "tx_count": 0},
        ]

        result = get_chain_info("http://localhost:8202")

        assert result is not None
        assert result["chain_id"] == "ait-mainnet"
        assert result["supported_chains"] == "ait-mainnet"

    @patch("aitbc_cli.utils.blockchain.AITBCHTTPClient")
    def test_get_chain_info_network_error(self, mock_client_class):
        """Test chain info with network error"""
        mock_client_class.side_effect = NetworkError("Connection failed")

        result = get_chain_info("http://localhost:8202")

        assert result is None

    @patch("aitbc_cli.utils.blockchain.AITBCHTTPClient")
    def test_get_chain_info_generic_error(self, mock_client_class):
        """Test chain info with generic error"""
        mock_client_class.side_effect = Exception("Unexpected error")

        result = get_chain_info("http://localhost:8202")

        assert result is None


class TestGetNetworkStatus:
    """Test get_network_status function"""

    @patch("aitbc_cli.utils.blockchain.AITBCHTTPClient")
    def test_get_network_status_success(self, mock_client_class):
        """Test successful network status retrieval"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        mock_client.get.return_value = {"height": 1000, "hash": "0xabc123", "timestamp": "2024-01-01T00:00:00Z"}

        result = get_network_status("http://localhost:8202")

        assert result is not None
        assert result["height"] == 1000
        assert result["hash"] == "0xabc123"

    @patch("aitbc_cli.utils.blockchain.AITBCHTTPClient")
    def test_get_network_status_network_error(self, mock_client_class):
        """Test network status with network error"""
        mock_client_class.side_effect = NetworkError("Connection failed")

        result = get_network_status("http://localhost:8202")

        assert result is None

    @patch("aitbc_cli.utils.blockchain.AITBCHTTPClient")
    def test_get_network_status_generic_error(self, mock_client_class):
        """Test network status with generic error"""
        mock_client_class.side_effect = Exception("Unexpected error")

        result = get_network_status("http://localhost:8202")

        assert result is None


class TestGetBlockchainAnalytics:
    """Test get_blockchain_analytics function"""

    @patch("aitbc_cli.utils.blockchain.AITBCHTTPClient")
    def test_analytics_blocks_type(self, mock_client_class):
        """Test blocks analytics type"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        mock_client.get.return_value = {
            "height": 1000,
            "hash": "0xabc123",
            "timestamp": "2024-01-01T00:00:00Z",
            "tx_count": 50,
        }

        result = get_blockchain_analytics("blocks")

        assert result is not None
        assert result["type"] == "blocks"
        assert result["current_height"] == 1000
        assert result["status"] == "Active"

    def test_analytics_supply_type(self):
        """Test supply analytics type"""
        result = get_blockchain_analytics("supply")

        assert result is not None
        assert result["type"] == "supply"
        assert result["total_supply"] == "1000000000"
        assert result["status"] == "Available"

    def test_analytics_accounts_type(self):
        """Test accounts analytics type"""
        result = get_blockchain_analytics("accounts")

        assert result is not None
        assert result["type"] == "accounts"
        assert result["total_accounts"] == 3
        assert result["active_accounts"] == 2
        assert result["status"] == "Healthy"

    def test_analytics_unimplemented_type(self):
        """Test unimplemented analytics type"""
        result = get_blockchain_analytics("unknown_type")

        assert result is not None
        assert result["type"] == "unknown_type"
        assert result["status"] == "Not implemented yet"

    @patch("aitbc_cli.utils.blockchain.AITBCHTTPClient")
    def test_analytics_with_limit(self, mock_client_class):
        """Test analytics with custom limit"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        mock_client.get.return_value = {
            "height": 1000,
            "hash": "0xabc123",
            "timestamp": "2024-01-01T00:00:00Z",
            "tx_count": 50,
        }

        result = get_blockchain_analytics("blocks", limit=20)

        assert result is not None
        # Limit parameter is accepted but not used in current implementation


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
