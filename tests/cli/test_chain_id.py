"""
Tests for chain ID utility functions
"""

from unittest.mock import Mock, patch

import pytest
from aitbc_cli.utils.chain_id import (
    get_chain_id,
    get_chain_id_from_health,
    get_default_chain_id,
    validate_chain_id,
)

from aitbc.exceptions import NetworkError


class TestGetDefaultChainId:
    """Test get_default_chain_id function"""

    def test_get_default_chain_id_from_env(self):
        """Test getting default chain ID from environment variable"""
        import os
        
        # Set environment variable
        os.environ["CHAIN_ID"] = "ait-hub.aitbc.bubuit.net"
        result = get_default_chain_id()
        
        assert result == "ait-hub.aitbc.bubuit.net"
        
        # Clean up
        del os.environ["CHAIN_ID"]

    def test_get_default_chain_id_no_env(self):
        """Test getting default chain ID when no environment variable set"""
        import os
        
        # Ensure no environment variable
        os.environ.pop("CHAIN_ID", None)
        result = get_default_chain_id()
        
        # Should return empty string when no default available
        assert result == ""


class TestValidateChainId:
    """Test validate_chain_id function"""

    def test_validate_known_chain(self):
        """Test validation of known chain IDs"""
        # Test some common chain ID formats
        known_chains = ["ait-mainnet", "ait-devnet", "ait-hub.aitbc.bubuit.net"]
        for chain in known_chains:
            assert validate_chain_id(chain) is True

    def test_validate_unknown_chain(self):
        """Test validation of unknown chain ID (now valid format)"""
        # With new format validation, any non-empty string is valid
        assert validate_chain_id("unknown-chain") is True

    def test_validate_empty_string(self):
        """Test validation of empty string"""
        assert validate_chain_id("") is False

    def test_validate_case_sensitive(self):
        """Test that validation accepts different cases"""
        # With new format validation, case doesn't matter for format validation
        assert validate_chain_id("AIT-MAINNET") is True
        assert validate_chain_id("ait-mainnet") is True


class TestGetChainIdFromHealth:
    """Test get_chain_id_from_health function"""

    @patch("aitbc_cli.utils.chain_id.AITBCHTTPClient")
    def test_get_chain_id_from_health_success(self, mock_client_class):
        """Test successful chain ID detection"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        mock_client.get.return_value = {"supported_chains": ["ait-mainnet", "ait-hub.aitbc.bubuit.net"]}

        result = get_chain_id_from_health("http://localhost:8202")

        assert result == "ait-mainnet"

    @patch("aitbc_cli.utils.chain_id.AITBCHTTPClient")
    def test_get_chain_id_from_health_empty_chains(self, mock_client_class):
        """Test chain ID detection with empty chains list"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        mock_client.get.return_value = {"supported_chains": []}

        result = get_chain_id_from_health("http://localhost:8202")

        assert result == "ait-mainnet"  # Fallback to default

    @patch("aitbc_cli.utils.chain_id.AITBCHTTPClient")
    def test_get_chain_id_from_health_no_chains_field(self, mock_client_class):
        """Test chain ID detection with no chains field"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        mock_client.get.return_value = {}

        result = get_chain_id_from_health("http://localhost:8202")

        assert result == "ait-mainnet"  # Fallback to default

    @patch("aitbc_cli.utils.chain_id.AITBCHTTPClient")
    def test_get_chain_id_from_health_network_error(self, mock_client_class):
        """Test chain ID detection with network error"""
        mock_client_class.side_effect = NetworkError("Connection failed")

        result = get_chain_id_from_health("http://localhost:8202")

        assert result == "ait-mainnet"  # Fallback to default

    @patch("aitbc_cli.utils.chain_id.AITBCHTTPClient")
    def test_get_chain_id_from_health_generic_error(self, mock_client_class):
        """Test chain ID detection with generic error"""
        mock_client_class.side_effect = Exception("Unexpected error")

        result = get_chain_id_from_health("http://localhost:8202")

        assert result == "ait-mainnet"  # Fallback to default

    @patch("aitbc_cli.utils.chain_id.AITBCHTTPClient")
    def test_get_chain_id_from_health_custom_timeout(self, mock_client_class):
        """Test chain ID detection with custom timeout"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        mock_client.get.return_value = {"supported_chains": ["ait-hub.aitbc.bubuit.net"]}

        result = get_chain_id_from_health("http://localhost:8202", timeout=10)

        assert result == "ait-hub.aitbc.bubuit.net"
        mock_client_class.assert_called_once_with(base_url="http://localhost:8202", timeout=10)


class TestGetChainId:
    """Test get_chain_id function"""

    @patch("aitbc_cli.utils.chain_id.get_chain_id_from_health")
    def test_get_chain_id_with_override_known(self, mock_get_from_health):
        """Test getting chain ID with known override"""
        result = get_chain_id("http://localhost:8202", override="ait-hub.aitbc.bubuit.net")

        assert result == "ait-hub.aitbc.bubuit.net"
        mock_get_from_health.assert_not_called()

    @patch("aitbc_cli.utils.chain_id.get_chain_id_from_health")
    def test_get_chain_id_with_override_unknown(self, mock_get_from_health):
        """Test getting chain ID with unknown override (still used)"""
        result = get_chain_id("http://localhost:8202", override="new-chain")

        assert result == "new-chain"
        mock_get_from_health.assert_not_called()

    @patch("aitbc_cli.utils.chain_id.get_chain_id_from_health")
    def test_get_chain_id_without_override(self, mock_get_from_health):
        """Test getting chain ID without override (uses auto-detection)"""
        mock_get_from_health.return_value = "ait-mainnet"

        result = get_chain_id("http://localhost:8202")

        assert result == "ait-mainnet"
        mock_get_from_health.assert_called_once_with("http://localhost:8202", 5)

    @patch("aitbc_cli.utils.chain_id.get_chain_id_from_health")
    def test_get_chain_id_with_custom_timeout(self, mock_get_from_health):
        """Test getting chain ID with custom timeout"""
        mock_get_from_health.return_value = "ait-hub.aitbc.bubuit.net"

        result = get_chain_id("http://localhost:8202", timeout=15)

        assert result == "ait-hub.aitbc.bubuit.net"
        mock_get_from_health.assert_called_once_with("http://localhost:8202", 15)

    @patch("aitbc_cli.utils.chain_id.get_chain_id_from_health")
    def test_get_chain_id_override_none(self, mock_get_from_health):
        """Test getting chain ID with override=None"""
        mock_get_from_health.return_value = "ait-mainnet"

        result = get_chain_id("http://localhost:8202", override=None)

        assert result == "ait-mainnet"
        mock_get_from_health.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
