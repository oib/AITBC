"""
Chain ID Utils Tests
Tests for chain ID utilities
"""

from unittest.mock import Mock, patch

import pytest


class TestGetDefaultChainId:
    """Test get_default_chain_id function"""

    def test_get_default_chain_id_from_env(self, monkeypatch):
        """Test getting default chain ID from environment variable"""
        from aitbc_cli.utils.chain_id import get_default_chain_id

        monkeypatch.setenv("CHAIN_ID", "ait-hub.aitbc.bubuit.net")
        result = get_default_chain_id()

        assert result == "ait-hub.aitbc.bubuit.net"

    def test_get_default_chain_id_no_env(self, monkeypatch):
        """Test getting default chain ID when no environment variable set"""
        from aitbc_cli.utils.chain_id import get_default_chain_id

        monkeypatch.delenv("CHAIN_ID", raising=False)
        result = get_default_chain_id()

        # Should return empty string when no default available
        assert result == ""


class TestValidateChainId:
    """Test validate_chain_id function"""

    def test_validate_chain_id_known(self):
        """Test validating chain ID formats"""
        from aitbc_cli.utils.chain_id import validate_chain_id

        # Test valid chain ID formats
        assert validate_chain_id("ait-mainnet") is True
        assert validate_chain_id("ait-devnet") is True
        assert validate_chain_id("ait-hub.aitbc.bubuit.net") is True
        assert validate_chain_id("ait-healthchain") is True
        assert validate_chain_id("custom-chain") is True

    def test_validate_chain_id_invalid(self):
        """Test validating invalid chain ID formats"""
        from aitbc_cli.utils.chain_id import validate_chain_id

        # Test invalid chain ID formats
        assert validate_chain_id("") is False
        assert validate_chain_id(None) is False


class TestGetChainIdFromHealth:
    """Test get_chain_id_from_health function"""

    @patch("aitbc_cli.utils.chain_id.AITBCHTTPClient")
    def test_get_chain_id_from_health_success(self, mock_client):
        """Test successful chain ID detection from health endpoint"""
        from aitbc_cli.utils.chain_id import get_chain_id_from_health

        mock_http_client = Mock()
        mock_http_client.get.return_value = {"supported_chains": ["ait-devnet", "ait-hub.aitbc.bubuit.net"]}
        mock_client.return_value = mock_http_client

        result = get_chain_id_from_health("http://localhost:8202")

        assert result == "ait-devnet"

    @patch("aitbc_cli.utils.chain_id.AITBCHTTPClient")
    def test_get_chain_id_from_health_no_chains(self, mock_client, monkeypatch):
        """Test health endpoint with no supported chains"""
        monkeypatch.delenv("CHAIN_ID", raising=False)
        from aitbc_cli.utils.chain_id import get_chain_id_from_health

        mock_http_client = Mock()
        mock_http_client.get.return_value = {"supported_chains": []}
        mock_client.return_value = mock_http_client

        result = get_chain_id_from_health("http://localhost:8202")

        assert result == ""  # Fallback to empty string (no default)

    @patch("aitbc_cli.utils.chain_id.AITBCHTTPClient")
    def test_get_chain_id_from_health_network_error(self, mock_client, monkeypatch):
        """Test network error during health check"""
        monkeypatch.delenv("CHAIN_ID", raising=False)
        from aitbc_cli.utils.chain_id import NetworkError, get_chain_id_from_health

        mock_http_client = Mock()
        mock_http_client.get.side_effect = NetworkError("Connection failed")
        mock_client.return_value = mock_http_client

        result = get_chain_id_from_health("http://localhost:8202")

        assert result == ""  # Fallback to empty string (no default)

    @patch("aitbc_cli.utils.chain_id.AITBCHTTPClient")
    def test_get_chain_id_from_health_generic_error(self, mock_client, monkeypatch):
        """Test generic error during health check"""
        monkeypatch.delenv("CHAIN_ID", raising=False)
        from aitbc_cli.utils.chain_id import get_chain_id_from_health

        mock_http_client = Mock()
        mock_http_client.get.side_effect = Exception("Unexpected error")
        mock_client.return_value = mock_http_client

        result = get_chain_id_from_health("http://localhost:8202")

        assert result == ""  # Fallback to empty string (no default)


class TestGetChainId:
    """Test get_chain_id function"""

    @patch("aitbc_cli.utils.chain_id.get_chain_id_from_health")
    def test_get_chain_id_with_override_known(self, mock_get_from_health):
        """Test get_chain_id with known override"""
        from aitbc_cli.utils.chain_id import get_chain_id

        result = get_chain_id("http://localhost:8202", override="ait-devnet")

        assert result == "ait-devnet"
        mock_get_from_health.assert_not_called()

    @patch("aitbc_cli.utils.chain_id.get_chain_id_from_health")
    def test_get_chain_id_with_override_unknown(self, mock_get_from_health):
        """Test get_chain_id with unknown override (still uses it)"""
        from aitbc_cli.utils.chain_id import get_chain_id

        result = get_chain_id("http://localhost:8202", override="custom-chain")

        assert result == "custom-chain"
        mock_get_from_health.assert_not_called()

    @patch("aitbc_cli.utils.chain_id.get_chain_id_from_health")
    def test_get_chain_id_without_override(self, mock_get_from_health):
        """Test get_chain_id without override (uses auto-detection)"""
        from aitbc_cli.utils.chain_id import get_chain_id

        mock_get_from_health.return_value = "ait-hub.aitbc.bubuit.net"

        result = get_chain_id("http://localhost:8202")

        assert result == "ait-hub.aitbc.bubuit.net"
        mock_get_from_health.assert_called_once()

    @patch("aitbc_cli.utils.chain_id.get_chain_id_from_health")
    def test_get_chain_id_with_custom_timeout(self, mock_get_from_health):
        """Test get_chain_id with custom timeout"""
        from aitbc_cli.utils.chain_id import get_chain_id

        mock_get_from_health.return_value = "ait-devnet"

        result = get_chain_id("http://localhost:8202", timeout=10)

        assert result == "ait-devnet"
        mock_get_from_health.assert_called_once_with("http://localhost:8202", 10)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
