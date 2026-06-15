"""
Tests for island credentials utility functions
"""

import json
import sys
from pathlib import Path
from unittest.mock import mock_open, patch

# Add CLI path for imports
cli_path = Path("/opt/aitbc/cli")
if str(cli_path) not in sys.path:
    sys.path.insert(0, str(cli_path))

import pytest  # noqa: E402
from aitbc_cli.utils.island_credentials import (  # noqa: E402
    CREDENTIALS_PATH,
    get_chain_id,
    get_genesis_address,
    get_genesis_block_hash,
    get_island_id,
    get_island_name,
    get_p2p_port,
    get_rpc_endpoint,
    load_island_credentials,
    validate_credentials,
)


class TestLoadIslandCredentials:
    """Test load_island_credentials function"""

    @patch("builtins.open", new_callable=mock_open)
    @patch("aitbc_cli.utils.island_credentials.Path")
    def test_load_credentials_success(self, mock_path, mock_file):
        """Test successful credentials loading"""
        mock_path.return_value.exists.return_value = True
        credentials_data = {
            "island_id": "island123",
            "island_name": "Test Island",
            "island_chain_id": "ait-mainnet",
            "credentials": {"rpc_endpoint": "http://localhost:8006"},
        }
        mock_file.return_value.read.return_value = json.dumps(credentials_data)

        result = load_island_credentials()

        assert result["island_id"] == "island123"
        assert result["island_name"] == "Test Island"

    @patch("aitbc_cli.utils.island_credentials.Path")
    def test_load_credentials_file_not_found(self, mock_path):
        """Test loading credentials when file doesn't exist"""
        mock_path.return_value.exists.return_value = False

        with pytest.raises(FileNotFoundError) as exc_info:
            load_island_credentials()

        assert "Island credentials not found" in str(exc_info.value)

    @patch("builtins.open", new_callable=mock_open)
    @patch("aitbc_cli.utils.island_credentials.Path")
    def test_load_credentials_invalid_json(self, mock_path, mock_file):
        """Test loading credentials with invalid JSON"""
        mock_path.return_value.exists.return_value = True
        mock_file.return_value.read.return_value = "invalid json"

        with pytest.raises(json.JSONDecodeError):
            load_island_credentials()

    @patch("builtins.open", new_callable=mock_open)
    @patch("aitbc_cli.utils.island_credentials.Path")
    def test_load_credentials_missing_field(self, mock_path, mock_file):
        """Test loading credentials with missing required field"""
        mock_path.return_value.exists.return_value = True
        credentials_data = {
            "island_id": "island123",
            "island_name": "Test Island",
            # Missing island_chain_id and credentials
        }
        mock_file.return_value.read.return_value = json.dumps(credentials_data)

        with pytest.raises(ValueError) as exc_info:
            load_island_credentials()

        assert "missing required field" in str(exc_info.value)


class TestGetRpcEndpoint:
    """Test get_rpc_endpoint function"""

    @patch("aitbc_cli.utils.island_credentials.load_island_credentials")
    def test_get_rpc_endpoint_success(self, mock_load):
        """Test getting RPC endpoint successfully"""
        mock_load.return_value = {"credentials": {"rpc_endpoint": "http://localhost:8006"}}

        result = get_rpc_endpoint()

        assert result == "http://localhost:8006"

    @patch("aitbc_cli.utils.island_credentials.load_island_credentials")
    def test_get_rpc_endpoint_missing(self, mock_load):
        """Test getting RPC endpoint when missing"""
        mock_load.return_value = {"credentials": {}}

        with pytest.raises(ValueError) as exc_info:
            get_rpc_endpoint()

        assert "RPC endpoint not found" in str(exc_info.value)


class TestGetChainId:
    """Test get_chain_id function"""

    @patch("aitbc_cli.utils.island_credentials.load_island_credentials")
    def test_get_chain_id_success(self, mock_load):
        """Test getting chain ID successfully"""
        mock_load.return_value = {"island_chain_id": "ait-mainnet"}

        result = get_chain_id()

        assert result == "ait-mainnet"

    @patch("aitbc_cli.utils.island_credentials.load_island_credentials")
    def test_get_chain_id_missing(self, mock_load):
        """Test getting chain ID when missing"""
        mock_load.return_value = {}

        with pytest.raises(ValueError) as exc_info:
            get_chain_id()

        assert "Chain ID not found" in str(exc_info.value)


class TestGetIslandId:
    """Test get_island_id function"""

    @patch("aitbc_cli.utils.island_credentials.load_island_credentials")
    def test_get_island_id_success(self, mock_load):
        """Test getting island ID successfully"""
        mock_load.return_value = {"island_id": "island123"}

        result = get_island_id()

        assert result == "island123"

    @patch("aitbc_cli.utils.island_credentials.load_island_credentials")
    def test_get_island_id_missing(self, mock_load):
        """Test getting island ID when missing"""
        mock_load.return_value = {}

        with pytest.raises(ValueError) as exc_info:
            get_island_id()

        assert "Island ID not found" in str(exc_info.value)


class TestGetIslandName:
    """Test get_island_name function"""

    @patch("aitbc_cli.utils.island_credentials.load_island_credentials")
    def test_get_island_name_success(self, mock_load):
        """Test getting island name successfully"""
        mock_load.return_value = {"island_name": "Test Island"}

        result = get_island_name()

        assert result == "Test Island"

    @patch("aitbc_cli.utils.island_credentials.load_island_credentials")
    def test_get_island_name_missing(self, mock_load):
        """Test getting island name when missing"""
        mock_load.return_value = {}

        with pytest.raises(ValueError) as exc_info:
            get_island_name()

        assert "Island name not found" in str(exc_info.value)


class TestGetGenesisBlockHash:
    """Test get_genesis_block_hash function"""

    @patch("aitbc_cli.utils.island_credentials.load_island_credentials")
    def test_get_genesis_block_hash_success(self, mock_load):
        """Test getting genesis block hash successfully"""
        mock_load.return_value = {"credentials": {"genesis_block_hash": "0xabc123"}}

        result = get_genesis_block_hash()

        assert result == "0xabc123"

    @patch("aitbc_cli.utils.island_credentials.load_island_credentials")
    def test_get_genesis_block_hash_missing(self, mock_load):
        """Test getting genesis block hash when missing"""
        mock_load.return_value = {"credentials": {}}

        result = get_genesis_block_hash()

        assert result is None

    @patch("aitbc_cli.utils.island_credentials.load_island_credentials")
    def test_get_genesis_block_hash_error(self, mock_load):
        """Test getting genesis block hash on error"""
        mock_load.side_effect = FileNotFoundError("File not found")

        result = get_genesis_block_hash()

        assert result is None


class TestGetGenesisAddress:
    """Test get_genesis_address function"""

    @patch("aitbc_cli.utils.island_credentials.load_island_credentials")
    def test_get_genesis_address_success(self, mock_load):
        """Test getting genesis address successfully"""
        mock_load.return_value = {"credentials": {"genesis_address": "ait123"}}

        result = get_genesis_address()

        assert result == "ait123"

    @patch("aitbc_cli.utils.island_credentials.load_island_credentials")
    def test_get_genesis_address_missing(self, mock_load):
        """Test getting genesis address when missing"""
        mock_load.return_value = {"credentials": {}}

        result = get_genesis_address()

        assert result is None

    @patch("aitbc_cli.utils.island_credentials.load_island_credentials")
    def test_get_genesis_address_error(self, mock_load):
        """Test getting genesis address on error"""
        mock_load.side_effect = ValueError("Invalid credentials")

        result = get_genesis_address()

        assert result is None


class TestValidateCredentials:
    """Test validate_credentials function"""

    @patch("aitbc_cli.utils.island_credentials.load_island_credentials")
    def test_validate_credentials_valid(self, mock_load):
        """Test validation of valid credentials"""
        mock_load.return_value = {
            "island_id": "island123",
            "island_name": "Test Island",
            "island_chain_id": "ait-mainnet",
            "credentials": {},
        }

        result = validate_credentials()

        assert result is True

    @patch("aitbc_cli.utils.island_credentials.load_island_credentials")
    def test_validate_credentials_missing_field(self, mock_load):
        """Test validation with missing field"""
        mock_load.return_value = {
            "island_id": "island123",
            "island_name": "Test Island",
            # Missing island_chain_id and credentials
        }

        result = validate_credentials()

        assert result is False

    @patch("aitbc_cli.utils.island_credentials.load_island_credentials")
    def test_validate_credentials_file_not_found(self, mock_load):
        """Test validation when file not found"""
        mock_load.side_effect = FileNotFoundError("File not found")

        result = validate_credentials()

        assert result is False

    @patch("aitbc_cli.utils.island_credentials.load_island_credentials")
    def test_validate_credentials_invalid_json(self, mock_load):
        """Test validation with invalid JSON"""
        mock_load.side_effect = json.JSONDecodeError("Invalid JSON", "", 0)

        result = validate_credentials()

        assert result is False


class TestGetP2PPort:
    """Test get_p2p_port function"""

    @patch("aitbc_cli.utils.island_credentials.load_island_credentials")
    def test_get_p2p_port_success(self, mock_load):
        """Test getting P2P port successfully"""
        mock_load.return_value = {"credentials": {"p2p_port": 30333}}

        result = get_p2p_port()

        assert result == 30333

    @patch("aitbc_cli.utils.island_credentials.load_island_credentials")
    def test_get_p2p_port_missing(self, mock_load):
        """Test getting P2P port when missing"""
        mock_load.return_value = {"credentials": {}}

        result = get_p2p_port()

        assert result is None

    @patch("aitbc_cli.utils.island_credentials.load_island_credentials")
    def test_get_p2p_port_error(self, mock_load):
        """Test getting P2P port on error"""
        mock_load.side_effect = ValueError("Invalid credentials")

        result = get_p2p_port()

        assert result is None


class TestCredentialsPath:
    """Test CREDENTIALS_PATH constant"""

    def test_credentials_path_constant(self):
        """Test that CREDENTIALS_PATH is defined"""
        assert CREDENTIALS_PATH == "/var/lib/aitbc/island_credentials.json"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
