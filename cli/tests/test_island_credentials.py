"""
Unit tests for island credential loading utility
"""

import json
import os

import pytest
from aitbc_cli.utils.island_credentials import (
    get_rpc_endpoint,
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


def _stub_config(monkeypatch, rpc_url):
    """Point get_config at a fixed blockchain_rpc_url for get_rpc_endpoint tests."""
    import types

    import aitbc_cli.utils.island_credentials as ic_module

    monkeypatch.setattr(ic_module, "get_config", lambda: types.SimpleNamespace(blockchain_rpc_url=rpc_url))


def test_get_rpc_endpoint_missing_credentials_falls_back_to_config(monkeypatch, tmp_path):
    """#2258: no island credentials file -> configured blockchain_rpc_url + /rpc."""
    import aitbc_cli.utils.island_credentials as ic_module

    monkeypatch.setattr(ic_module, "CREDENTIALS_PATH", str(tmp_path / "absent.json"))
    _stub_config(monkeypatch, "http://127.0.0.1:8202")

    assert get_rpc_endpoint() == "http://127.0.0.1:8202/rpc"


def _write_creds(creds_path, credentials):
    creds_path.write_text(json.dumps(credentials))
    os.chmod(creds_path, 0o600)


def test_get_rpc_endpoint_credentials_rpc_endpoint_wins(monkeypatch, tmp_path):
    """Credentials file with rpc_endpoint still wins over the config fallback."""
    import aitbc_cli.utils.island_credentials as ic_module

    creds_path = tmp_path / "island_credentials.json"
    _write_creds(
        creds_path,
        {
            "island_id": "island-1",
            "island_name": "island",
            "island_chain_id": "ait-test",
            "credentials": {"rpc_endpoint": "http://island:9999/rpc"},
        },
    )
    monkeypatch.setattr(ic_module, "CREDENTIALS_PATH", str(creds_path))
    _stub_config(monkeypatch, "http://127.0.0.1:8202")

    assert get_rpc_endpoint() == "http://island:9999/rpc"


def test_get_rpc_endpoint_empty_credentials_rpc_falls_back(monkeypatch, tmp_path):
    """Credentials file present but rpc_endpoint empty keeps the old fallback."""
    import aitbc_cli.utils.island_credentials as ic_module

    creds_path = tmp_path / "island_credentials.json"
    _write_creds(
        creds_path,
        {
            "island_id": "island-1",
            "island_name": "island",
            "island_chain_id": "ait-test",
            "credentials": {"genesis_block_hash": "0xabc"},
        },
    )
    monkeypatch.setattr(ic_module, "CREDENTIALS_PATH", str(creds_path))
    _stub_config(monkeypatch, "http://hub.example:8202/")

    assert get_rpc_endpoint() == "http://hub.example:8202/rpc"
