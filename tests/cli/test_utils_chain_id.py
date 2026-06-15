"""
Chain ID Utils Tests
Tests for chain ID utilities
"""

import sys
from pathlib import Path
from unittest.mock import Mock, patch

# Add CLI path for imports
cli_path = Path("/opt/aitbc/cli")
if str(cli_path) not in sys.path:
    sys.path.insert(0, str(cli_path))

import pytest  # noqa: E402


class TestGetDefaultChainId:
    """Test get_default_chain_id function"""

    def test_get_default_chain_id(self):
        """Test getting default chain ID"""
        from aitbc_cli.utils.chain_id import get_default_chain_id

        result = get_default_chain_id()

        assert result == "ait-mainnet"


class TestValidateChainId:
    """Test validate_chain_id function"""

    def test_validate_chain_id_known(self):
        """Test validating known chain IDs"""
        from aitbc_cli.utils.chain_id import validate_chain_id

        assert validate_chain_id("ait-mainnet") is True
        assert validate_chain_id("ait-devnet") is True
        assert validate_chain_id("ait-testnet") is True
        assert validate_chain_id("ait-healthchain") is True

    def test_validate_chain_id_unknown(self):
        """Test validating unknown chain IDs"""
        from aitbc_cli.utils.chain_id import validate_chain_id

        assert validate_chain_id("unknown-chain") is False
        assert validate_chain_id("custom-chain") is False


class TestGetChainIdFromHealth:
    """Test get_chain_id_from_health function"""

    @patch("aitbc_cli.utils.chain_id.AITBCHTTPClient")
    def test_get_chain_id_from_health_success(self, mock_client):
        """Test successful chain ID detection from health endpoint"""
        from aitbc_cli.utils.chain_id import get_chain_id_from_health

        mock_http_client = Mock()
        mock_http_client.get.return_value = {"supported_chains": ["ait-devnet", "ait-testnet"]}
        mock_client.return_value = mock_http_client

        result = get_chain_id_from_health("http://localhost:8006")

        assert result == "ait-devnet"

    @patch("aitbc_cli.utils.chain_id.AITBCHTTPClient")
    def test_get_chain_id_from_health_no_chains(self, mock_client):
        """Test health endpoint with no supported chains"""
        from aitbc_cli.utils.chain_id import get_chain_id_from_health

        mock_http_client = Mock()
        mock_http_client.get.return_value = {"supported_chains": []}
        mock_client.return_value = mock_http_client

        result = get_chain_id_from_health("http://localhost:8006")

        assert result == "ait-mainnet"  # Fallback to default

    @patch("aitbc_cli.utils.chain_id.AITBCHTTPClient")
    def test_get_chain_id_from_health_network_error(self, mock_client):
        """Test network error during health check"""
        from aitbc_cli.utils.chain_id import NetworkError, get_chain_id_from_health

        mock_http_client = Mock()
        mock_http_client.get.side_effect = NetworkError("Connection failed")
        mock_client.return_value = mock_http_client

        result = get_chain_id_from_health("http://localhost:8006")

        assert result == "ait-mainnet"  # Fallback to default

    @patch("aitbc_cli.utils.chain_id.AITBCHTTPClient")
    def test_get_chain_id_from_health_generic_error(self, mock_client):
        """Test generic error during health check"""
        from aitbc_cli.utils.chain_id import get_chain_id_from_health

        mock_http_client = Mock()
        mock_http_client.get.side_effect = Exception("Unexpected error")
        mock_client.return_value = mock_http_client

        result = get_chain_id_from_health("http://localhost:8006")

        assert result == "ait-mainnet"  # Fallback to default


class TestGetChainId:
    """Test get_chain_id function"""

    @patch("aitbc_cli.utils.chain_id.get_chain_id_from_health")
    def test_get_chain_id_with_override_known(self, mock_get_from_health):
        """Test get_chain_id with known override"""
        from aitbc_cli.utils.chain_id import get_chain_id

        result = get_chain_id("http://localhost:8006", override="ait-devnet")

        assert result == "ait-devnet"
        mock_get_from_health.assert_not_called()

    @patch("aitbc_cli.utils.chain_id.get_chain_id_from_health")
    def test_get_chain_id_with_override_unknown(self, mock_get_from_health):
        """Test get_chain_id with unknown override (still uses it)"""
        from aitbc_cli.utils.chain_id import get_chain_id

        result = get_chain_id("http://localhost:8006", override="custom-chain")

        assert result == "custom-chain"
        mock_get_from_health.assert_not_called()

    @patch("aitbc_cli.utils.chain_id.get_chain_id_from_health")
    def test_get_chain_id_without_override(self, mock_get_from_health):
        """Test get_chain_id without override (uses auto-detection)"""
        from aitbc_cli.utils.chain_id import get_chain_id

        mock_get_from_health.return_value = "ait-testnet"

        result = get_chain_id("http://localhost:8006")

        assert result == "ait-testnet"
        mock_get_from_health.assert_called_once()

    @patch("aitbc_cli.utils.chain_id.get_chain_id_from_health")
    def test_get_chain_id_with_custom_timeout(self, mock_get_from_health):
        """Test get_chain_id with custom timeout"""
        from aitbc_cli.utils.chain_id import get_chain_id

        mock_get_from_health.return_value = "ait-devnet"

        result = get_chain_id("http://localhost:8006", timeout=10)

        assert result == "ait-devnet"
        mock_get_from_health.assert_called_once_with("http://localhost:8006", 10)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
