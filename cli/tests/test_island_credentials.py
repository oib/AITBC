"""
Unit tests for island credential loading utility
"""

import json
import os

import pytest
from aitbc_cli.utils.island_credentials import (
    load_island_credentials,
    validate_credentials,
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
            "rpc_endpoint": "http://localhost:8202",
            "p2p_port": 8001,
        },
        "joined_at": "2024-01-01T00:00:00",
    }

    # Monkey patch the credentials path
    import aitbc_cli.utils.island_credentials as ic_module

    original_path = ic_module.CREDENTIALS_PATH
    ic_module.CREDENTIALS_PATH = str(tmp_path / "island_credentials.json")

    # Write credentials to temp file
    with open(ic_module.CREDENTIALS_PATH, "w") as f:
        json.dump(credentials, f)

    yield credentials

    # Cleanup
    if os.path.exists(ic_module.CREDENTIALS_PATH):
        os.remove(ic_module.CREDENTIALS_PATH)
    ic_module.CREDENTIALS_PATH = original_path


def test_load_island_credentials_file_not_found():
    """Test loading credentials when file doesn't exist"""
    import aitbc_cli.utils.island_credentials as ic_module

    original_path = ic_module.CREDENTIALS_PATH
    ic_module.CREDENTIALS_PATH = "/nonexistent/path/credentials.json"

    with pytest.raises(FileNotFoundError):
        load_island_credentials()

    ic_module.CREDENTIALS_PATH = original_path


def test_validate_credentials_invalid_file(tmp_path):
    """Test validating credentials when file doesn't exist"""
    import aitbc_cli.utils.island_credentials as ic_module

    original_path = ic_module.CREDENTIALS_PATH
    ic_module.CREDENTIALS_PATH = "/nonexistent/path/credentials.json"

    is_valid = validate_credentials()

    assert is_valid is False

    ic_module.CREDENTIALS_PATH = original_path


if __name__ == "__main__":
    pytest.main([__file__])
