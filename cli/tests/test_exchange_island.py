"""
Unit tests for Exchange Island CLI commands
"""

import json
import os
from unittest.mock import patch

import pytest
from click.testing import CliRunner


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
        "members": [],
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


@pytest.fixture
def mock_keystore(tmp_path):
    """Create a temporary keystore for testing.

    Patches the module-level KEYSTORE_PATH constant so commands read
    from a temp file instead of /var/lib/aitbc/keystore/validator_keys.json.
    """
    keystore = {
        "test_key_id": {"public_key_pem": "-----BEGIN PUBLIC KEY-----\ntest_public_key_data\n-----END PUBLIC KEY-----"}
    }

    keystore_path = tmp_path / "validator_keys.json"
    with open(keystore_path, "w") as f:
        json.dump(keystore, f)

    keystore_str = str(keystore_path)

    with patch("aitbc_cli.commands.exchange_island.KEYSTORE_PATH", keystore_str):
        yield keystore_str


@pytest.fixture
def runner():
    """Create a Click CLI runner.

    Tests should use run_with_obj() to invoke commands with a default
    context object so ctx.obj.get("output_format") works.
    """
    return CliRunner()


def test_exchange_buy_command_invalid_amount(mock_credentials_file, runner):
    """Test exchange buy command with invalid amount"""
    from aitbc_cli.commands.exchange_island import exchange_island

    # Use "--" to separate options from positional args so "-10" is not parsed as a flag
    result = runner.invoke(exchange_island, ["buy", "--", "-10", "ETH"], obj={})

    assert result.exit_code != 0
    assert "must be greater than 0" in result.output


def test_exchange_sell_command_invalid_amount(mock_credentials_file, runner):
    """Test exchange sell command with invalid amount"""
    from aitbc_cli.commands.exchange_island import exchange_island

    result = runner.invoke(exchange_island, ["sell", "--", "-10", "ETH"], obj={})

    assert result.exit_code != 0
    assert "must be greater than 0" in result.output


def test_exchange_orderbook_invalid_pair(mock_credentials_file, runner):
    """Test exchange orderbook command with invalid pair"""
    from aitbc_cli.commands.exchange_island import exchange_island

    result = runner.invoke(exchange_island, ["orderbook", "INVALID/PAIR"], obj={})

    assert result.exit_code != 0


def test_exchange_buy_invalid_currency(mock_credentials_file, runner):
    """Test exchange buy command with invalid currency"""
    from aitbc_cli.commands.exchange_island import exchange_island

    result = runner.invoke(exchange_island, ["buy", "100", "INVALID"], obj={})

    assert result.exit_code != 0


def test_exchange_sell_invalid_currency(mock_credentials_file, runner):
    """Test exchange sell command with invalid currency"""
    from aitbc_cli.commands.exchange_island import exchange_island

    result = runner.invoke(exchange_island, ["sell", "100", "INVALID"], obj={})

    assert result.exit_code != 0


if __name__ == "__main__":
    pytest.main([__file__])
