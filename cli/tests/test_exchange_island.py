"""
Unit tests for Exchange Island CLI commands
"""

import pytest
import json
import os
from pathlib import Path
from click.testing import CliRunner
from unittest.mock import patch, MagicMock


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
        "members": [],
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


@pytest.fixture
def mock_keystore(tmp_path):
    """Create a temporary keystore for testing"""
    keystore = {
        "test_key_id": {
            "public_key_pem": "-----BEGIN PUBLIC KEY-----\ntest_public_key_data\n-----END PUBLIC KEY-----"
        }
    }
    
    keystore_path = tmp_path / "validator_keys.json"
    with open(keystore_path, 'w') as f:
        json.dump(keystore, f)
    
    # Monkey patch keystore path
    import aitbc_cli.commands.exchange_island as ei_module
    original_path = ei_module.__dict__.get('keystore_path')
    
    yield str(keystore_path)
    
    # Restore
    if original_path:
        ei_module.keystore_path = original_path


@pytest.fixture
def runner():
    """Create a Click CLI runner"""
    return CliRunner()


def test_exchange_buy_command(mock_credentials_file, mock_keystore, runner):
    """Test exchange buy command"""
    from aitbc_cli.commands.exchange_island import exchange_island
    
    with patch('aitbc_cli.commands.exchange_island.httpx.Client') as mock_client:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"transaction_id": "test_tx_id"}
        mock_client.return_value.__enter__.return_value.post.return_value = mock_response
        
        result = runner.invoke(exchange_island, ['buy', '100', 'BTC', '--max-price', '0.00001'])
        
        assert result.exit_code == 0
        assert "Buy order created successfully" in result.output


def test_exchange_buy_command_invalid_amount(mock_credentials_file, runner):
    """Test exchange buy command with invalid amount"""
    from aitbc_cli.commands.exchange_island import exchange_island
    
    result = runner.invoke(exchange_island, ['buy', '-10', 'BTC'])
    
    assert result.exit_code != 0
    assert "must be greater than 0" in result.output


def test_exchange_sell_command(mock_credentials_file, mock_keystore, runner):
    """Test exchange sell command"""
    from aitbc_cli.commands.exchange_island import exchange_island
    
    with patch('aitbc_cli.commands.exchange_island.httpx.Client') as mock_client:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"transaction_id": "test_tx_id"}
        mock_client.return_value.__enter__.return_value.post.return_value = mock_response
        
        result = runner.invoke(exchange_island, ['sell', '100', 'ETH', '--min-price', '0.0005'])
        
        assert result.exit_code == 0
        assert "Sell order created successfully" in result.output


def test_exchange_sell_command_invalid_amount(mock_credentials_file, runner):
    """Test exchange sell command with invalid amount"""
    from aitbc_cli.commands.exchange_island import exchange_island
    
    result = runner.invoke(exchange_island, ['sell', '-10', 'ETH'])
    
    assert result.exit_code != 0
    assert "must be greater than 0" in result.output


def test_exchange_orderbook_command(mock_credentials_file, runner):
    """Test exchange orderbook command"""
    from aitbc_cli.commands.exchange_island import exchange_island
    
    with patch('aitbc_cli.commands.exchange_island.httpx.Client') as mock_client:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "action": "buy",
                "order_id": "exchange_buy_test",
                "user_id": "test_user",
                "pair": "AIT/BTC",
                "side": "buy",
                "amount": 100.0,
                "max_price": 0.00001,
                "status": "open",
                "created_at": "2024-01-01T00:00:00"
            },
            {
                "action": "sell",
                "order_id": "exchange_sell_test",
                "user_id": "test_user2",
                "pair": "AIT/BTC",
                "side": "sell",
                "amount": 100.0,
                "min_price": 0.000009,
                "status": "open",
                "created_at": "2024-01-01T00:00:00"
            }
        ]
        mock_client.return_value.__enter__.return_value.get.return_value = mock_response
        
        result = runner.invoke(exchange_island, ['orderbook', 'AIT/BTC'])
        
        assert result.exit_code == 0


def test_exchange_rates_command(mock_credentials_file, runner):
    """Test exchange rates command"""
    from aitbc_cli.commands.exchange_island import exchange_island
    
    with patch('aitbc_cli.commands.exchange_island.httpx.Client') as mock_client:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_client.return_value.__enter__.return_value.get.return_value = mock_response
        
        result = runner.invoke(exchange_island, ['rates'])
        
        assert result.exit_code == 0


def test_exchange_orders_command(mock_credentials_file, runner):
    """Test exchange orders command"""
    from aitbc_cli.commands.exchange_island import exchange_island
    
    with patch('aitbc_cli.commands.exchange_island.httpx.Client') as mock_client:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "action": "buy",
                "order_id": "exchange_buy_test",
                "user_id": "test_user",
                "pair": "AIT/BTC",
                "side": "buy",
                "amount": 100.0,
                "max_price": 0.00001,
                "status": "open",
                "created_at": "2024-01-01T00:00:00"
            }
        ]
        mock_client.return_value.__enter__.return_value.get.return_value = mock_response
        
        result = runner.invoke(exchange_island, ['orders'])
        
        assert result.exit_code == 0


def test_exchange_cancel_command(mock_credentials_file, mock_keystore, runner):
    """Test exchange cancel command"""
    from aitbc_cli.commands.exchange_island import exchange_island
    
    with patch('aitbc_cli.commands.exchange_island.httpx.Client') as mock_client:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client.return_value.__enter__.return_value.post.return_value = mock_response
        
        result = runner.invoke(exchange_island, ['cancel', 'exchange_buy_test123'])
        
        assert result.exit_code == 0
        assert "cancelled successfully" in result.output


def test_exchange_orderbook_invalid_pair(mock_credentials_file, runner):
    """Test exchange orderbook command with invalid pair"""
    from aitbc_cli.commands.exchange_island import exchange_island
    
    result = runner.invoke(exchange_island, ['orderbook', 'INVALID/PAIR'])
    
    assert result.exit_code != 0


def test_exchange_buy_invalid_currency(mock_credentials_file, runner):
    """Test exchange buy command with invalid currency"""
    from aitbc_cli.commands.exchange_island import exchange_island
    
    result = runner.invoke(exchange_island, ['buy', '100', 'INVALID'])
    
    assert result.exit_code != 0


def test_exchange_sell_invalid_currency(mock_credentials_file, runner):
    """Test exchange sell command with invalid currency"""
    from aitbc_cli.commands.exchange_island import exchange_island
    
    result = runner.invoke(exchange_island, ['sell', '100', 'INVALID'])
    
    assert result.exit_code != 0


if __name__ == "__main__":
    pytest.main([__file__])
