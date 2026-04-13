"""
Unit tests for island credential loading utility
"""

import pytest
import json
import os
from pathlib import Path
from aitbc_cli.utils.island_credentials import (
    load_island_credentials,
    get_rpc_endpoint,
    get_chain_id,
    get_island_id,
    get_island_name,
    get_genesis_block_hash,
    get_genesis_address,
    validate_credentials,
    get_p2p_port
)


@pytest.fixture
def mock_credentials_file(tmp_path):
    """Create a temporary credentials file for testing"""
    credentials = {
        "island_id": "test-island-id-12345",
        "island_name": "test-island",
        "island_chain_id": "ait-test",
        "credentials": {
            "genesis_block_hash": "0x1234567890abcdef",
            "genesis_address": "0xabcdef1234567890",
            "rpc_endpoint": "http://localhost:8006",
            "p2p_port": 8001
        },
        "joined_at": "2024-01-01T00:00:00"
    }
    
    # Monkey patch the credentials path
    import aitbc_cli.utils.island_credentials as ic_module
    original_path = ic_module.CREDENTIALS_PATH
    ic_module.CREDENTIALS_PATH = str(tmp_path / "island_credentials.json")
    
    # Write credentials to temp file
    with open(ic_module.CREDENTIALS_PATH, 'w') as f:
        json.dump(credentials, f)
    
    yield credentials
    
    # Cleanup
    if os.path.exists(ic_module.CREDENTIALS_PATH):
        os.remove(ic_module.CREDENTIALS_PATH)
    ic_module.CREDENTIALS_PATH = original_path


def test_load_island_credentials(mock_credentials_file):
    """Test loading island credentials"""
    credentials = load_island_credentials()
    
    assert credentials is not None
    assert credentials['island_id'] == "test-island-id-12345"
    assert credentials['island_name'] == "test-island"
    assert credentials['island_chain_id'] == "ait-test"
    assert 'credentials' in credentials


def test_load_island_credentials_file_not_found():
    """Test loading credentials when file doesn't exist"""
    import aitbc_cli.utils.island_credentials as ic_module
    original_path = ic_module.CREDENTIALS_PATH
    ic_module.CREDENTIALS_PATH = "/nonexistent/path/credentials.json"
    
    with pytest.raises(FileNotFoundError):
        load_island_credentials()
    
    ic_module.CREDENTIALS_PATH = original_path


def test_load_island_credentials_invalid_json(tmp_path):
    """Test loading credentials with invalid JSON"""
    import aitbc_cli.utils.island_credentials as ic_module
    original_path = ic_module.CREDENTIALS_PATH
    ic_module.CREDENTIALS_PATH = str(tmp_path / "invalid.json")
    
    with open(ic_module.CREDENTIALS_PATH, 'w') as f:
        f.write("invalid json")
    
    with pytest.raises(json.JSONDecodeError):
        load_island_credentials()
    
    ic_module.CREDENTIALS_PATH = original_path


def test_load_island_credentials_missing_fields(tmp_path):
    """Test loading credentials with missing required fields"""
    import aitbc_cli.utils.island_credentials as ic_module
    original_path = ic_module.CREDENTIALS_PATH
    ic_module.CREDENTIALS_PATH = str(tmp_path / "incomplete.json")
    
    with open(ic_module.CREDENTIALS_PATH, 'w') as f:
        json.dump({"island_id": "test"}, f)
    
    with pytest.raises(ValueError):
        load_island_credentials()
    
    ic_module.CREDENTIALS_PATH = original_path


def test_get_rpc_endpoint(mock_credentials_file):
    """Test getting RPC endpoint from credentials"""
    rpc_endpoint = get_rpc_endpoint()
    
    assert rpc_endpoint == "http://localhost:8006"


def test_get_chain_id(mock_credentials_file):
    """Test getting chain ID from credentials"""
    chain_id = get_chain_id()
    
    assert chain_id == "ait-test"


def test_get_island_id(mock_credentials_file):
    """Test getting island ID from credentials"""
    island_id = get_island_id()
    
    assert island_id == "test-island-id-12345"


def test_get_island_name(mock_credentials_file):
    """Test getting island name from credentials"""
    island_name = get_island_name()
    
    assert island_name == "test-island"


def test_get_genesis_block_hash(mock_credentials_file):
    """Test getting genesis block hash from credentials"""
    genesis_hash = get_genesis_block_hash()
    
    assert genesis_hash == "0x1234567890abcdef"


def test_get_genesis_address(mock_credentials_file):
    """Test getting genesis address from credentials"""
    genesis_address = get_genesis_address()
    
    assert genesis_address == "0xabcdef1234567890"


def test_get_p2p_port(mock_credentials_file):
    """Test getting P2P port from credentials"""
    p2p_port = get_p2p_port()
    
    assert p2p_port == 8001


def test_validate_credentials_valid(mock_credentials_file):
    """Test validating valid credentials"""
    is_valid = validate_credentials()
    
    assert is_valid is True


def test_validate_credentials_invalid_file(tmp_path):
    """Test validating credentials when file doesn't exist"""
    import aitbc_cli.utils.island_credentials as ic_module
    original_path = ic_module.CREDENTIALS_PATH
    ic_module.CREDENTIALS_PATH = "/nonexistent/path/credentials.json"
    
    is_valid = validate_credentials()
    
    assert is_valid is False
    
    ic_module.CREDENTIALS_PATH = original_path


def test_get_genesis_block_hash_missing(tmp_path):
    """Test getting genesis block hash when not present"""
    import aitbc_cli.utils.island_credentials as ic_module
    original_path = ic_module.CREDENTIALS_PATH
    
    credentials = {
        "island_id": "test-island-id",
        "island_name": "test-island",
        "island_chain_id": "ait-test",
        "credentials": {}
    }
    
    ic_module.CREDENTIALS_PATH = str(tmp_path / "no_genesis.json")
    with open(ic_module.CREDENTIALS_PATH, 'w') as f:
        json.dump(credentials, f)
    
    genesis_hash = get_genesis_block_hash()
    
    assert genesis_hash is None
    
    ic_module.CREDENTIALS_PATH = original_path


if __name__ == "__main__":
    pytest.main([__file__])
