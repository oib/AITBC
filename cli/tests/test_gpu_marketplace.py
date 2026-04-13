"""
Unit tests for GPU marketplace CLI commands
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
    import aitbc_cli.commands.gpu_marketplace as gm_module
    original_path = gm_module.__dict__.get('keystore_path')
    
    yield str(keystore_path)
    
    # Restore
    if original_path:
        gm_module.keystore_path = original_path


@pytest.fixture
def runner():
    """Create a Click CLI runner"""
    return CliRunner()


def test_gpu_offer_command(mock_credentials_file, mock_keystore, runner):
    """Test GPU offer command"""
    from aitbc_cli.commands.gpu_marketplace import gpu
    
    with patch('aitbc_cli.commands.gpu_marketplace.httpx.Client') as mock_client:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"transaction_id": "test_tx_id"}
        mock_client.return_value.__enter__.return_value.post.return_value = mock_response
        
        result = runner.invoke(gpu, ['offer', '2', '0.5', '24'])
        
        assert result.exit_code == 0
        assert "GPU offer created successfully" in result.output


def test_gpu_bid_command(mock_credentials_file, mock_keystore, runner):
    """Test GPU bid command"""
    from aitbc_cli.commands.gpu_marketplace import gpu
    
    with patch('aitbc_cli.commands.gpu_marketplace.httpx.Client') as mock_client:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"transaction_id": "test_tx_id"}
        mock_client.return_value.__enter__.return_value.post.return_value = mock_response
        
        result = runner.invoke(gpu, ['bid', '2', '1.0', '24'])
        
        assert result.exit_code == 0
        assert "GPU bid created successfully" in result.output


def test_gpu_list_command(mock_credentials_file, runner):
    """Test GPU list command"""
    from aitbc_cli.commands.gpu_marketplace import gpu
    
    with patch('aitbc_cli.commands.gpu_marketplace.httpx.Client') as mock_client:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "action": "offer",
                "offer_id": "gpu_offer_test",
                "gpu_count": 2,
                "price_per_gpu": 0.5,
                "duration_hours": 24,
                "total_price": 24.0,
                "status": "active",
                "provider_node_id": "test_provider",
                "created_at": "2024-01-01T00:00:00"
            }
        ]
        mock_client.return_value.__enter__.return_value.get.return_value = mock_response
        
        result = runner.invoke(gpu, ['list'])
        
        assert result.exit_code == 0


def test_gpu_cancel_command(mock_credentials_file, mock_keystore, runner):
    """Test GPU cancel command"""
    from aitbc_cli.commands.gpu_marketplace import gpu
    
    with patch('aitbc_cli.commands.gpu_marketplace.httpx.Client') as mock_client:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client.return_value.__enter__.return_value.post.return_value = mock_response
        
        result = runner.invoke(gpu, ['cancel', 'gpu_offer_test123'])
        
        assert result.exit_code == 0
        assert "cancelled successfully" in result.output


def test_gpu_accept_command(mock_credentials_file, mock_keystore, runner):
    """Test GPU accept command"""
    from aitbc_cli.commands.gpu_marketplace import gpu
    
    with patch('aitbc_cli.commands.gpu_marketplace.httpx.Client') as mock_client:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client.return_value.__enter__.return_value.post.return_value = mock_response
        
        result = runner.invoke(gpu, ['accept', 'gpu_bid_test123'])
        
        assert result.exit_code == 0
        assert "accepted successfully" in result.output


def test_gpu_status_command(mock_credentials_file, runner):
    """Test GPU status command"""
    from aitbc_cli.commands.gpu_marketplace import gpu
    
    with patch('aitbc_cli.commands.gpu_marketplace.httpx.Client') as mock_client:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "action": "offer",
                "offer_id": "gpu_offer_test",
                "gpu_count": 2,
                "price_per_gpu": 0.5,
                "duration_hours": 24,
                "total_price": 24.0,
                "status": "active",
                "provider_node_id": "test_provider",
                "created_at": "2024-01-01T00:00:00"
            }
        ]
        mock_client.return_value.__enter__.return_value.get.return_value = mock_response
        
        result = runner.invoke(gpu, ['status', 'gpu_offer_test'])
        
        assert result.exit_code == 0


def test_gpu_match_command(mock_credentials_file, runner):
    """Test GPU match command"""
    from aitbc_cli.commands.gpu_marketplace import gpu
    
    with patch('aitbc_cli.commands.gpu_marketplace.httpx.Client') as mock_client:
        # Mock the GET request for transactions
        mock_get_response = MagicMock()
        mock_get_response.status_code = 200
        mock_get_response.json.return_value = [
            {
                "action": "offer",
                "offer_id": "gpu_offer_test",
                "gpu_count": 2,
                "price_per_gpu": 0.5,
                "duration_hours": 24,
                "total_price": 24.0,
                "status": "active",
                "provider_node_id": "test_provider"
            },
            {
                "action": "bid",
                "bid_id": "gpu_bid_test",
                "gpu_count": 2,
                "max_price_per_gpu": 1.0,
                "duration_hours": 24,
                "max_total_price": 48.0,
                "status": "pending",
                "bidder_node_id": "test_bidder"
            }
        ]
        
        # Mock the POST request for match transaction
        mock_post_response = MagicMock()
        mock_post_response.status_code = 200
        
        mock_client.return_value.__enter__.return_value.get.return_value = mock_get_response
        mock_client.return_value.__enter__.return_value.post.return_value = mock_post_response
        
        result = runner.invoke(gpu, ['match'])
        
        assert result.exit_code == 0


def test_gpu_providers_command(mock_credentials_file, runner):
    """Test GPU providers command"""
    from aitbc_cli.commands.gpu_marketplace import gpu
    
    result = runner.invoke(gpu, ['providers'])
    
    assert result.exit_code == 0


if __name__ == "__main__":
    pytest.main([__file__])
