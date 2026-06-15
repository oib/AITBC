"""
Blockchain Utils Advanced Tests
Tests for blockchain utility functions
"""

import sys
from pathlib import Path
from unittest.mock import Mock, patch

# Add CLI path for imports
cli_path = Path("/opt/aitbc/cli")
if str(cli_path) not in sys.path:
    sys.path.insert(0, str(cli_path))

import pytest  # noqa: E402


class TestGetChainInfo:
    """Test get_chain_info function"""

    @patch("aitbc_cli.utils.blockchain.AITBCHTTPClient")
    def test_get_chain_info_success(self, mock_client_class):
        """Test successful chain info retrieval"""
        from aitbc_cli.utils.blockchain import get_chain_info

        mock_client = Mock()
        mock_client_class.return_value = mock_client

        mock_health = {"supported_chains": ["ait-mainnet", "ait-testnet"], "proposer_id": "proposer_123"}
        mock_head = {"height": 1000, "hash": "0xabc123", "timestamp": "2024-01-01T00:00:00Z", "tx_count": 50}

        mock_client.get.side_effect = [mock_health, mock_head]

        result = get_chain_info("http://localhost:8202")

        assert result is not None
        assert result["chain_id"] == "ait-mainnet"
        assert result["height"] == 1000
        assert result["tx_count"] == 50

    @patch("aitbc_cli.utils.blockchain.AITBCHTTPClient")
    def test_get_chain_info_no_chains(self, mock_client_class):
        """Test chain info with no supported chains"""
        from aitbc_cli.utils.blockchain import get_chain_info

        mock_client = Mock()
        mock_client_class.return_value = mock_client

        mock_health = {"supported_chains": [], "proposer_id": ""}
        mock_head = {"height": 0, "hash": "", "timestamp": "N/A", "tx_count": 0}

        mock_client.get.side_effect = [mock_health, mock_head]

        result = get_chain_info("http://localhost:8202")

        assert result is not None
        assert result["chain_id"] == "ait-mainnet"

    @patch("aitbc_cli.utils.blockchain.AITBCHTTPClient")
    def test_get_chain_info_network_error(self, mock_client_class):
        """Test chain info with network error"""
        from aitbc_cli.utils.blockchain import get_chain_info

        from aitbc import NetworkError

        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.get.side_effect = NetworkError("Connection failed")

        result = get_chain_info("http://localhost:8202")

        assert result is None


class TestGetNetworkStatus:
    """Test get_network_status function"""

    @patch("aitbc_cli.utils.blockchain.AITBCHTTPClient")
    def test_get_network_status_success(self, mock_client_class):
        """Test successful network status retrieval"""
        from aitbc_cli.utils.blockchain import get_network_status

        mock_client = Mock()
        mock_client_class.return_value = mock_client

        mock_head = {"height": 1000, "hash": "0xabc123", "timestamp": "2024-01-01T00:00:00Z", "tx_count": 50}

        mock_client.get.return_value = mock_head

        result = get_network_status("http://localhost:8202")

        assert result is not None
        assert result["height"] == 1000

    @patch("aitbc_cli.utils.blockchain.AITBCHTTPClient")
    def test_get_network_status_error(self, mock_client_class):
        """Test network status with error"""
        from aitbc_cli.utils.blockchain import get_network_status

        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.get.side_effect = Exception("Error")

        result = get_network_status("http://localhost:8202")

        assert result is None


class TestGetBlockchainAnalytics:
    """Test get_blockchain_analytics function"""

    @patch("aitbc_cli.utils.blockchain.AITBCHTTPClient")
    def test_get_analytics_blocks(self, mock_client_class):
        """Test analytics for blocks type"""
        from aitbc_cli.utils.blockchain import get_blockchain_analytics

        mock_client = Mock()
        mock_client_class.return_value = mock_client

        mock_head = {"height": 1000, "hash": "0xabc123", "timestamp": "2024-01-01T00:00:00Z", "tx_count": 50}

        mock_client.get.return_value = mock_head

        result = get_blockchain_analytics("blocks", 10, "http://localhost:8202")

        assert result is not None
        assert result["type"] == "blocks"
        assert result["current_height"] == 1000

    def test_get_analytics_supply(self):
        """Test analytics for supply type"""
        from aitbc_cli.utils.blockchain import get_blockchain_analytics

        result = get_blockchain_analytics("supply", 10, "http://localhost:8202")

        assert result is not None
        assert result["type"] == "supply"
        assert result["total_supply"] == "1000000000"

    def test_get_analytics_accounts(self):
        """Test analytics for accounts type"""
        from aitbc_cli.utils.blockchain import get_blockchain_analytics

        result = get_blockchain_analytics("accounts", 10, "http://localhost:8202")

        assert result is not None
        assert result["type"] == "accounts"
        assert result["total_accounts"] == 3

    def test_get_analytics_unknown_type(self):
        """Test analytics for unknown type"""
        from aitbc_cli.utils.blockchain import get_blockchain_analytics

        result = get_blockchain_analytics("unknown", 10, "http://localhost:8202")

        assert result is not None
        assert result["type"] == "unknown"
        assert result["status"] == "Not implemented yet"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
