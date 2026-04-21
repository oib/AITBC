"""Tests for blockchain CLI commands"""

import pytest
import json
from click.testing import CliRunner
from unittest.mock import Mock, patch
from aitbc_cli.commands.blockchain import blockchain


@pytest.fixture
def runner():
    """Create CLI runner"""
    return CliRunner()


@pytest.fixture
def mock_config():
    """Mock configuration"""
    config = Mock()
    config.coordinator_url = "http://test:8000"
    config.api_key = "test_api_key"
    return config


class TestBlockchainCommands:
    """Test blockchain command group"""
    
    @patch('aitbc_cli.commands.blockchain.httpx.Client')
    def test_blocks_success(self, mock_client_class, runner, mock_config):
        """Test successful block listing"""
        # Setup mock
        mock_client = Mock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "blocks": [
                {"height": 100, "hash": "0xabc123", "timestamp": "2024-01-01T00:00:00"},
                {"height": 99, "hash": "0xdef456", "timestamp": "2024-01-01T00:01:00"}
            ]
        }
        mock_client.get.return_value = mock_response
        
        # Run command
        result = runner.invoke(blockchain, [
            'blocks',
            '--limit', '2'
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        # Assertions
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data['blocks']) == 2
        assert data['blocks'][0]['height'] == 100
        
        # Verify API call
        mock_client.get.assert_called_once_with(
            'http://test:8000/v1/explorer/blocks',
            params={"limit": 2},
            headers={"X-Api-Key": "test_api_key"}
        )
    
    @patch('aitbc_cli.commands.blockchain.httpx.Client')
    def test_block_details(self, mock_client_class, runner, mock_config):
        """Test getting block details"""
        # Setup mock
        mock_client = Mock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "height": 100,
            "hash": "0xabc123",
            "transactions": ["0xtx1", "0xtx2"],
            "timestamp": "2024-01-01T00:00:00",
            "validator": "validator1"
        }
        mock_client.get.return_value = mock_response
        
        # Run command
        result = runner.invoke(blockchain, [
            'block',
            '100'
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        # Assertions
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data['height'] == 100
        assert data['hash'] == '0xabc123'
        assert len(data['transactions']) == 2
        
        # Verify API call
        mock_client.get.assert_called_once_with(
            'http://test:8000/v1/explorer/blocks/100',
            headers={"X-Api-Key": "test_api_key"}
        )
    
    @patch('aitbc_cli.commands.blockchain.httpx.Client')
    def test_transaction(self, mock_client_class, runner, mock_config):
        """Test getting transaction details"""
        # Setup mock
        mock_client = Mock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "hash": "0xtx123",
            "block": 100,
            "from": "0xabc",
            "to": "0xdef",
            "amount": "1000",
            "fee": "10",
            "status": "confirmed"
        }
        mock_client.get.return_value = mock_response
        
        # Run command
        result = runner.invoke(blockchain, [
            'transaction',
            '0xtx123'
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        # Assertions
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data['hash'] == '0xtx123'
        assert data['block'] == 100
        assert data['status'] == 'confirmed'
        
        # Verify API call
        mock_client.get.assert_called_once_with(
            'http://test:8000/v1/explorer/transactions/0xtx123',
            headers={"X-Api-Key": "test_api_key"}
        )
    
    @patch('aitbc_cli.commands.blockchain.httpx.Client')
    def test_node_status(self, mock_client_class, runner, mock_config):
        """Test getting node status"""
        # Setup mock
        mock_client = Mock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "running",
            "version": "1.0.0",
            "height": 1000,
            "peers": 5,
            "synced": True
        }
        mock_client.get.return_value = mock_response
        
        # Run command
        result = runner.invoke(blockchain, [
            'status',
            '--node', '1'
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        # Assertions
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data['node'] == 1
        assert data['rpc_url'] == 'http://localhost:8082'
        assert data['status']['status'] == 'running'
        
        # Verify API call
        mock_client.get.assert_called_once_with(
            'http://localhost:8082/status',
            timeout=5
        )
    
    @patch('aitbc_cli.commands.blockchain.httpx.Client')
    def test_sync_status(self, mock_client_class, runner, mock_config):
        """Test getting sync status"""
        # Setup mock
        mock_client = Mock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "synced": True,
            "current_height": 1000,
            "target_height": 1000,
            "sync_percentage": 100.0
        }
        mock_client.get.return_value = mock_response
        
        # Run command
        result = runner.invoke(blockchain, [
            'sync-status'
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        # Assertions
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data['synced'] == True
        assert data['sync_percentage'] == 100.0
        
        # Verify API call
        mock_client.get.assert_called_once_with(
            'http://test:8000/v1/blockchain/sync',
            headers={"X-Api-Key": "test_api_key"}
        )
    
    @patch('aitbc_cli.commands.blockchain.httpx.Client')
    def test_peers(self, mock_client_class, runner, mock_config):
        """Test listing peers"""
        # Setup mock
        mock_client = Mock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "peers": [
                {"id": "peer1", "address": "1.2.3.4:8080", "connected": True},
                {"id": "peer2", "address": "5.6.7.8:8080", "connected": False}
            ]
        }
        mock_client.get.return_value = mock_response
        
        # Run command
        result = runner.invoke(blockchain, [
            'peers'
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        # Assertions
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data['peers']) == 2
        assert data['peers'][0]['connected'] == True
        
        # Verify API call
        mock_client.get.assert_called_once_with(
            'http://test:8000/v1/blockchain/peers',
            headers={"X-Api-Key": "test_api_key"}
        )
    
    @patch('aitbc_cli.commands.blockchain.httpx.Client')
    def test_info(self, mock_client_class, runner, mock_config):
        """Test getting blockchain info"""
        # Setup mock
        mock_client = Mock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "network": "aitbc-mainnet",
            "chain_id": "aitbc-1",
            "block_time": 5,
            "min_stake": 1000,
            "total_supply": "1000000000"
        }
        mock_client.get.return_value = mock_response
        
        # Run command
        result = runner.invoke(blockchain, [
            'info'
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        # Assertions
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data['network'] == 'aitbc-mainnet'
        assert data['block_time'] == 5
        
        # Verify API call
        mock_client.get.assert_called_once_with(
            'http://test:8000/v1/blockchain/info',
            headers={"X-Api-Key": "test_api_key"}
        )
    
    @patch('aitbc_cli.commands.blockchain.httpx.Client')
    def test_supply(self, mock_client_class, runner, mock_config):
        """Test getting token supply"""
        # Setup mock
        mock_client = Mock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "total_supply": "1000000000",
            "circulating_supply": "500000000",
            "staked": "300000000",
            "burned": "200000000"
        }
        mock_client.get.return_value = mock_response
        
        # Run command
        result = runner.invoke(blockchain, [
            'supply'
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        # Assertions
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data['total_supply'] == '1000000000'
        assert data['circulating_supply'] == '500000000'
        
        # Verify API call
        mock_client.get.assert_called_once_with(
            'http://test:8000/v1/blockchain/supply',
            headers={"X-Api-Key": "test_api_key"}
        )
    
    @patch('aitbc_cli.commands.blockchain.httpx.Client')
    def test_validators(self, mock_client_class, runner, mock_config):
        """Test listing validators"""
        # Setup mock
        mock_client = Mock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "validators": [
                {"address": "0xval1", "stake": "100000", "status": "active"},
                {"address": "0xval2", "stake": "50000", "status": "active"}
            ]
        }
        mock_client.get.return_value = mock_response
        
        # Run command
        result = runner.invoke(blockchain, [
            'validators'
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        # Assertions
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data['validators']) == 2
        assert data['validators'][0]['stake'] == '100000'
        
        # Verify API call
        mock_client.get.assert_called_once_with(
            'http://test:8000/v1/blockchain/validators',
            headers={"X-Api-Key": "test_api_key"}
        )
    
    @patch('aitbc_cli.commands.blockchain.httpx.Client')
    def test_api_error_handling(self, mock_client_class, runner, mock_config):
        """Test API error handling"""
        # Setup mock for error response
        mock_client = Mock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_response = Mock()
        mock_response.status_code = 404
        mock_client.get.return_value = mock_response
        
        # Run command
        result = runner.invoke(blockchain, [
            'block',
            '999999'
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        # Assertions
        assert result.exit_code == 0  # The command doesn't exit on error
        assert 'not found' in result.output
