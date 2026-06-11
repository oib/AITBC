"""
Tests for chain ID utility functions
"""

import sys
from pathlib import Path
from unittest.mock import Mock, patch

# Add CLI path for imports
cli_path = Path("/opt/aitbc/cli")
if str(cli_path) not in sys.path:
    sys.path.insert(0, str(cli_path))

import pytest
from aitbc_cli.utils.chain_id import (
    KNOWN_CHAINS,
    get_chain_id,
    get_chain_id_from_health,
    get_default_chain_id,
    validate_chain_id,
)

from aitbc import NetworkError


class TestGetDefaultChainId:
    """Test get_default_chain_id function"""

    def test_get_default_chain_id(self):
        """Test getting default chain ID"""
        result = get_default_chain_id()
        
        assert result == "ait-mainnet"


class TestValidateChainId:
    """Test validate_chain_id function"""

    def test_validate_known_chain(self):
        """Test validation of known chain IDs"""
        for chain in KNOWN_CHAINS:
            assert validate_chain_id(chain) is True

    def test_validate_unknown_chain(self):
        """Test validation of unknown chain ID"""
        assert validate_chain_id("unknown-chain") is False

    def test_validate_empty_string(self):
        """Test validation of empty string"""
        assert validate_chain_id("") is False

    def test_validate_case_sensitive(self):
        """Test that validation is case-sensitive"""
        assert validate_chain_id("AIT-MAINNET") is False
        assert validate_chain_id("ait-mainnet") is True


class TestGetChainIdFromHealth:
    """Test get_chain_id_from_health function"""

    @patch('aitbc_cli.utils.chain_id.AITBCHTTPClient')
    def test_get_chain_id_from_health_success(self, mock_client_class):
        """Test successful chain ID detection"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        
        mock_client.get.return_value = {
            "supported_chains": ["ait-mainnet", "ait-testnet"]
        }
        
        result = get_chain_id_from_health("http://localhost:8006")
        
        assert result == "ait-mainnet"

    @patch('aitbc_cli.utils.chain_id.AITBCHTTPClient')
    def test_get_chain_id_from_health_empty_chains(self, mock_client_class):
        """Test chain ID detection with empty chains list"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        
        mock_client.get.return_value = {
            "supported_chains": []
        }
        
        result = get_chain_id_from_health("http://localhost:8006")
        
        assert result == "ait-mainnet"  # Fallback to default

    @patch('aitbc_cli.utils.chain_id.AITBCHTTPClient')
    def test_get_chain_id_from_health_no_chains_field(self, mock_client_class):
        """Test chain ID detection with no chains field"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        
        mock_client.get.return_value = {}
        
        result = get_chain_id_from_health("http://localhost:8006")
        
        assert result == "ait-mainnet"  # Fallback to default

    @patch('aitbc_cli.utils.chain_id.AITBCHTTPClient')
    def test_get_chain_id_from_health_network_error(self, mock_client_class):
        """Test chain ID detection with network error"""
        mock_client_class.side_effect = NetworkError("Connection failed")
        
        result = get_chain_id_from_health("http://localhost:8006")
        
        assert result == "ait-mainnet"  # Fallback to default

    @patch('aitbc_cli.utils.chain_id.AITBCHTTPClient')
    def test_get_chain_id_from_health_generic_error(self, mock_client_class):
        """Test chain ID detection with generic error"""
        mock_client_class.side_effect = Exception("Unexpected error")
        
        result = get_chain_id_from_health("http://localhost:8006")
        
        assert result == "ait-mainnet"  # Fallback to default

    @patch('aitbc_cli.utils.chain_id.AITBCHTTPClient')
    def test_get_chain_id_from_health_custom_timeout(self, mock_client_class):
        """Test chain ID detection with custom timeout"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        
        mock_client.get.return_value = {
            "supported_chains": ["ait-testnet"]
        }
        
        result = get_chain_id_from_health("http://localhost:8006", timeout=10)
        
        assert result == "ait-testnet"
        mock_client_class.assert_called_once_with(base_url="http://localhost:8006", timeout=10)


class TestGetChainId:
    """Test get_chain_id function"""

    @patch('aitbc_cli.utils.chain_id.get_chain_id_from_health')
    def test_get_chain_id_with_override_known(self, mock_get_from_health):
        """Test getting chain ID with known override"""
        result = get_chain_id("http://localhost:8006", override="ait-testnet")
        
        assert result == "ait-testnet"
        mock_get_from_health.assert_not_called()

    @patch('aitbc_cli.utils.chain_id.get_chain_id_from_health')
    def test_get_chain_id_with_override_unknown(self, mock_get_from_health):
        """Test getting chain ID with unknown override (still used)"""
        result = get_chain_id("http://localhost:8006", override="new-chain")
        
        assert result == "new-chain"
        mock_get_from_health.assert_not_called()

    @patch('aitbc_cli.utils.chain_id.get_chain_id_from_health')
    def test_get_chain_id_without_override(self, mock_get_from_health):
        """Test getting chain ID without override (uses auto-detection)"""
        mock_get_from_health.return_value = "ait-mainnet"
        
        result = get_chain_id("http://localhost:8006")
        
        assert result == "ait-mainnet"
        mock_get_from_health.assert_called_once_with("http://localhost:8006", 5)

    @patch('aitbc_cli.utils.chain_id.get_chain_id_from_health')
    def test_get_chain_id_with_custom_timeout(self, mock_get_from_health):
        """Test getting chain ID with custom timeout"""
        mock_get_from_health.return_value = "ait-testnet"
        
        result = get_chain_id("http://localhost:8006", timeout=15)
        
        assert result == "ait-testnet"
        mock_get_from_health.assert_called_once_with("http://localhost:8006", 15)

    @patch('aitbc_cli.utils.chain_id.get_chain_id_from_health')
    def test_get_chain_id_override_none(self, mock_get_from_health):
        """Test getting chain ID with override=None"""
        mock_get_from_health.return_value = "ait-mainnet"
        
        result = get_chain_id("http://localhost:8006", override=None)
        
        assert result == "ait-mainnet"
        mock_get_from_health.assert_called_once()


class TestKnownChains:
    """Test KNOWN_CHAINS constant"""

    def test_known_chains_list(self):
        """Test that KNOWN_CHAINS is a list"""
        assert isinstance(KNOWN_CHAINS, list)

    def test_known_chains_not_empty(self):
        """Test that KNOWN_CHAINS is not empty"""
        assert len(KNOWN_CHAINS) > 0

    def test_known_chains_contains_mainnet(self):
        """Test that KNOWN_CHAINS contains mainnet"""
        assert "ait-mainnet" in KNOWN_CHAINS


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
