"""
Island Credentials Tests
Tests for island credential loading utility
"""

import sys
from pathlib import Path
from unittest.mock import patch, Mock
import tempfile
import json

# Add CLI path for imports
cli_path = Path("/opt/aitbc/cli")
if str(cli_path) not in sys.path:
    sys.path.insert(0, str(cli_path))

import pytest


class TestLoadIslandCredentials:
    """Test load_island_credentials function"""

    def test_load_island_credentials_success(self):
        """Test successful credentials loading"""
        from aitbc_cli.utils.island_credentials import load_island_credentials
        
        with tempfile.TemporaryDirectory() as tmpdir:
            credentials_path = Path(tmpdir) / "island_credentials.json"
            credentials_data = {
                "island_id": "island123",
                "island_name": "Test Island",
                "island_chain_id": "ait-devnet",
                "credentials": {
                    "rpc_endpoint": "http://localhost:8202"
                }
            }
            
            with open(credentials_path, 'w') as f:
                json.dump(credentials_data, f)
            
            with patch('aitbc_cli.utils.island_credentials.CREDENTIALS_PATH', str(credentials_path)):
                result = load_island_credentials()
                
                assert result['island_id'] == "island123"
                assert result['island_name'] == "Test Island"
                assert result['island_chain_id'] == "ait-devnet"

    def test_load_island_credentials_file_not_found(self):
        """Test loading credentials when file doesn't exist"""
        from aitbc_cli.utils.island_credentials import load_island_credentials
        
        with patch('aitbc_cli.utils.island_credentials.CREDENTIALS_PATH', '/nonexistent/path.json'):
            with pytest.raises(FileNotFoundError):
                load_island_credentials()

    def test_load_island_credentials_missing_field(self):
        """Test loading credentials with missing required field"""
        from aitbc_cli.utils.island_credentials import load_island_credentials
        
        with tempfile.TemporaryDirectory() as tmpdir:
            credentials_path = Path(tmpdir) / "island_credentials.json"
            credentials_data = {
                "island_id": "island123",
                "island_name": "Test Island",
                # Missing island_chain_id and credentials
            }
            
            with open(credentials_path, 'w') as f:
                json.dump(credentials_data, f)
            
            with patch('aitbc_cli.utils.island_credentials.CREDENTIALS_PATH', str(credentials_path)):
                with pytest.raises(ValueError, match="missing required field"):
                    load_island_credentials()


class TestGetRpcEndpoint:
    """Test get_rpc_endpoint function"""

    def test_get_rpc_endpoint_success(self):
        """Test successful RPC endpoint retrieval"""
        from aitbc_cli.utils.island_credentials import get_rpc_endpoint
        
        with tempfile.TemporaryDirectory() as tmpdir:
            credentials_path = Path(tmpdir) / "island_credentials.json"
            credentials_data = {
                "island_id": "island123",
                "island_name": "Test Island",
                "island_chain_id": "ait-devnet",
                "credentials": {
                    "rpc_endpoint": "http://localhost:8202"
                }
            }
            
            with open(credentials_path, 'w') as f:
                json.dump(credentials_data, f)
            
            with patch('aitbc_cli.utils.island_credentials.CREDENTIALS_PATH', str(credentials_path)):
                result = get_rpc_endpoint()
                
                assert result == "http://localhost:8202"

    def test_get_rpc_endpoint_missing(self):
        """Test RPC endpoint when missing from credentials"""
        from aitbc_cli.utils.island_credentials import get_rpc_endpoint
        
        with tempfile.TemporaryDirectory() as tmpdir:
            credentials_path = Path(tmpdir) / "island_credentials.json"
            credentials_data = {
                "island_id": "island123",
                "island_name": "Test Island",
                "island_chain_id": "ait-devnet",
                "credentials": {}
            }
            
            with open(credentials_path, 'w') as f:
                json.dump(credentials_data, f)
            
            with patch('aitbc_cli.utils.island_credentials.CREDENTIALS_PATH', str(credentials_path)):
                with pytest.raises(ValueError, match="RPC endpoint not found"):
                    get_rpc_endpoint()


class TestGetChainId:
    """Test get_chain_id function"""

    def test_get_chain_id_success(self):
        """Test successful chain ID retrieval"""
        from aitbc_cli.utils.island_credentials import get_chain_id
        
        with tempfile.TemporaryDirectory() as tmpdir:
            credentials_path = Path(tmpdir) / "island_credentials.json"
            credentials_data = {
                "island_id": "island123",
                "island_name": "Test Island",
                "island_chain_id": "ait-devnet",
                "credentials": {}
            }
            
            with open(credentials_path, 'w') as f:
                json.dump(credentials_data, f)
            
            with patch('aitbc_cli.utils.island_credentials.CREDENTIALS_PATH', str(credentials_path)):
                result = get_chain_id()
                
                assert result == "ait-devnet"


class TestGetIslandId:
    """Test get_island_id function"""

    def test_get_island_id_success(self):
        """Test successful island ID retrieval"""
        from aitbc_cli.utils.island_credentials import get_island_id
        
        with tempfile.TemporaryDirectory() as tmpdir:
            credentials_path = Path(tmpdir) / "island_credentials.json"
            credentials_data = {
                "island_id": "island123",
                "island_name": "Test Island",
                "island_chain_id": "ait-devnet",
                "credentials": {}
            }
            
            with open(credentials_path, 'w') as f:
                json.dump(credentials_data, f)
            
            with patch('aitbc_cli.utils.island_credentials.CREDENTIALS_PATH', str(credentials_path)):
                result = get_island_id()
                
                assert result == "island123"


class TestGetIslandName:
    """Test get_island_name function"""

    def test_get_island_name_success(self):
        """Test successful island name retrieval"""
        from aitbc_cli.utils.island_credentials import get_island_name
        
        with tempfile.TemporaryDirectory() as tmpdir:
            credentials_path = Path(tmpdir) / "island_credentials.json"
            credentials_data = {
                "island_id": "island123",
                "island_name": "Test Island",
                "island_chain_id": "ait-devnet",
                "credentials": {}
            }
            
            with open(credentials_path, 'w') as f:
                json.dump(credentials_data, f)
            
            with patch('aitbc_cli.utils.island_credentials.CREDENTIALS_PATH', str(credentials_path)):
                result = get_island_name()
                
                assert result == "Test Island"


class TestGetGenesisBlockHash:
    """Test get_genesis_block_hash function"""

    def test_get_genesis_block_hash_success(self):
        """Test successful genesis block hash retrieval"""
        from aitbc_cli.utils.island_credentials import get_genesis_block_hash
        
        with tempfile.TemporaryDirectory() as tmpdir:
            credentials_path = Path(tmpdir) / "island_credentials.json"
            credentials_data = {
                "island_id": "island123",
                "island_name": "Test Island",
                "island_chain_id": "ait-devnet",
                "credentials": {
                    "genesis_block_hash": "0xabc123"
                }
            }
            
            with open(credentials_path, 'w') as f:
                json.dump(credentials_data, f)
            
            with patch('aitbc_cli.utils.island_credentials.CREDENTIALS_PATH', str(credentials_path)):
                result = get_genesis_block_hash()
                
                assert result == "0xabc123"

    def test_get_genesis_block_hash_missing(self):
        """Test genesis block hash when missing"""
        from aitbc_cli.utils.island_credentials import get_genesis_block_hash
        
        with tempfile.TemporaryDirectory() as tmpdir:
            credentials_path = Path(tmpdir) / "island_credentials.json"
            credentials_data = {
                "island_id": "island123",
                "island_name": "Test Island",
                "island_chain_id": "ait-devnet",
                "credentials": {}
            }
            
            with open(credentials_path, 'w') as f:
                json.dump(credentials_data, f)
            
            with patch('aitbc_cli.utils.island_credentials.CREDENTIALS_PATH', str(credentials_path)):
                result = get_genesis_block_hash()
                
                assert result is None


class TestValidateCredentials:
    """Test validate_credentials function"""

    def test_validate_credentials_valid(self):
        """Test validating valid credentials"""
        from aitbc_cli.utils.island_credentials import validate_credentials
        
        with tempfile.TemporaryDirectory() as tmpdir:
            credentials_path = Path(tmpdir) / "island_credentials.json"
            credentials_data = {
                "island_id": "island123",
                "island_name": "Test Island",
                "island_chain_id": "ait-devnet",
                "credentials": {}
            }
            
            with open(credentials_path, 'w') as f:
                json.dump(credentials_data, f)
            
            with patch('aitbc_cli.utils.island_credentials.CREDENTIALS_PATH', str(credentials_path)):
                result = validate_credentials()
                
                assert result is True

    def test_validate_credentials_invalid(self):
        """Test validating invalid credentials"""
        from aitbc_cli.utils.island_credentials import validate_credentials
        
        with patch('aitbc_cli.utils.island_credentials.CREDENTIALS_PATH', '/nonexistent/path.json'):
            result = validate_credentials()
            
            assert result is False


class TestGetP2PPort:
    """Test get_p2p_port function"""

    def test_get_p2p_port_success(self):
        """Test successful P2P port retrieval"""
        from aitbc_cli.utils.island_credentials import get_p2p_port
        
        with tempfile.TemporaryDirectory() as tmpdir:
            credentials_path = Path(tmpdir) / "island_credentials.json"
            credentials_data = {
                "island_id": "island123",
                "island_name": "Test Island",
                "island_chain_id": "ait-devnet",
                "credentials": {
                    "p2p_port": 8100
                }
            }
            
            with open(credentials_path, 'w') as f:
                json.dump(credentials_data, f)
            
            with patch('aitbc_cli.utils.island_credentials.CREDENTIALS_PATH', str(credentials_path)):
                result = get_p2p_port()
                
                assert result == 8100

    def test_get_p2p_port_missing(self):
        """Test P2P port when missing"""
        from aitbc_cli.utils.island_credentials import get_p2p_port
        
        with tempfile.TemporaryDirectory() as tmpdir:
            credentials_path = Path(tmpdir) / "island_credentials.json"
            credentials_data = {
                "island_id": "island123",
                "island_name": "Test Island",
                "island_chain_id": "ait-devnet",
                "credentials": {}
            }
            
            with open(credentials_path, 'w') as f:
                json.dump(credentials_data, f)
            
            with patch('aitbc_cli.utils.island_credentials.CREDENTIALS_PATH', str(credentials_path)):
                result = get_p2p_port()
                
                assert result is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
