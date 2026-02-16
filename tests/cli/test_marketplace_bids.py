"""Tests for marketplace bid CLI commands"""

import pytest
import json
from click.testing import CliRunner
from unittest.mock import Mock, patch
from aitbc_cli.commands.marketplace import marketplace


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


class TestMarketplaceBidCommands:
    """Test marketplace bid command group"""
    
    @patch('aitbc_cli.commands.marketplace.httpx.Client')
    def test_bid_submit_success(self, mock_client_class, runner, mock_config):
        """Test successful bid submission"""
        # Setup mock
        mock_client = Mock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_response = Mock()
        mock_response.status_code = 202
        mock_response.json.return_value = {
            "id": "bid123",
            "status": "pending"
        }
        mock_client.post.return_value = mock_response
        
        # Run command
        result = runner.invoke(marketplace, [
            'bid',
            'submit',
            '--provider', 'miner123',
            '--capacity', '100',
            '--price', '0.05',
            '--notes', 'Need GPU capacity for AI training'
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        # Assertions
        assert result.exit_code == 0
        # Extract JSON from output (success message + JSON)
        # Remove ANSI escape codes and extract JSON part
        import re
        clean_output = re.sub(r'\x1b\[[0-9;]*m', '', result.output)
        lines = clean_output.strip().split('\n')
        
        # Find JSON part (multiline JSON with ANSI codes removed)
        json_lines = []
        in_json = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith('{'):
                in_json = True
                json_lines.append(stripped)
            elif in_json:
                json_lines.append(stripped)
                if stripped.endswith('}'):
                    break
        
        json_str = '\n'.join(json_lines)
        assert json_str, "No JSON found in output"
        data = json.loads(json_str)
        assert data['id'] == 'bid123'
        
        # Verify API call
        mock_client.post.assert_called_once_with(
            'http://test:8000/v1/marketplace/bids',
            json={
                "provider": "miner123",
                "capacity": 100,
                "price": 0.05,
                "notes": "Need GPU capacity for AI training"
            },
            headers={
                "Content-Type": "application/json",
                "X-Api-Key": "test_api_key"
            }
        )
    
    @patch('aitbc_cli.commands.marketplace.httpx.Client')
    def test_bid_submit_validation_error(self, mock_client_class, runner, mock_config):
        """Test bid submission with invalid capacity"""
        # Run command with invalid capacity
        result = runner.invoke(marketplace, [
            'bid',
            'submit',
            '--provider', 'miner123',
            '--capacity', '0',  # Invalid: must be > 0
            '--price', '0.05'
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        # Assertions
        assert result.exit_code == 0
        assert 'Capacity must be greater than 0' in result.output
        
        # Verify no API call was made
        mock_client_class.assert_not_called()
    
    @patch('aitbc_cli.commands.marketplace.httpx.Client')
    def test_bid_submit_price_validation_error(self, mock_client_class, runner, mock_config):
        """Test bid submission with invalid price"""
        # Run command with invalid price
        result = runner.invoke(marketplace, [
            'bid',
            'submit',
            '--provider', 'miner123',
            '--capacity', '100',
            '--price', '-0.05'  # Invalid: must be > 0
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        # Assertions
        assert result.exit_code == 0
        assert 'Price must be greater than 0' in result.output
        
        # Verify no API call was made
        mock_client_class.assert_not_called()
    
    @patch('aitbc_cli.commands.marketplace.httpx.Client')
    def test_bid_submit_api_error(self, mock_client_class, runner, mock_config):
        """Test bid submission with API error"""
        # Setup mock for error response
        mock_client = Mock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.text = "Invalid provider"
        mock_client.post.return_value = mock_response
        
        # Run command
        result = runner.invoke(marketplace, [
            'bid',
            'submit',
            '--provider', 'invalid_provider',
            '--capacity', '100',
            '--price', '0.05'
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        # Assertions
        assert result.exit_code == 0
        assert 'Failed to submit bid: 400' in result.output
        assert 'Invalid provider' in result.output
    
    @patch('aitbc_cli.commands.marketplace.httpx.Client')
    def test_bid_list_all(self, mock_client_class, runner, mock_config):
        """Test listing all bids"""
        # Setup mock
        mock_client = Mock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "bids": [
                {
                    "id": "bid1",
                    "provider": "miner1",
                    "capacity": 100,
                    "price": 0.05,
                    "status": "pending",
                    "submitted_at": "2024-01-01T00:00:00"
                },
                {
                    "id": "bid2",
                    "provider": "miner2",
                    "capacity": 50,
                    "price": 0.03,
                    "status": "accepted",
                    "submitted_at": "2024-01-01T01:00:00"
                }
            ]
        }
        mock_client.get.return_value = mock_response
        
        # Run command
        result = runner.invoke(marketplace, [
            'bid',
            'list'
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        # Assertions
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data['bids']) == 2
        assert data['bids'][0]['provider'] == 'miner1'
        assert data['bids'][0]['status'] == 'pending'
        
        # Verify API call
        mock_client.get.assert_called_once_with(
            'http://test:8000/v1/marketplace/bids',
            params={"limit": 20},
            headers={"X-Api-Key": "test_api_key"}
        )
    
    @patch('aitbc_cli.commands.marketplace.httpx.Client')
    def test_bid_list_with_filters(self, mock_client_class, runner, mock_config):
        """Test listing bids with filters"""
        # Setup mock
        mock_client = Mock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "bids": [
                {
                    "id": "bid1",
                    "provider": "miner123",
                    "capacity": 100,
                    "price": 0.05,
                    "status": "pending",
                    "submitted_at": "2024-01-01T00:00:00"
                }
            ]
        }
        mock_client.get.return_value = mock_response
        
        # Run command with filters
        result = runner.invoke(marketplace, [
            'bid',
            'list',
            '--status', 'pending',
            '--provider', 'miner123',
            '--limit', '10'
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        # Assertions
        assert result.exit_code == 0
        
        # Verify API call with filters
        mock_client.get.assert_called_once()
        call_args = mock_client.get.call_args
        assert call_args[1]['params']['status'] == 'pending'
        assert call_args[1]['params']['provider'] == 'miner123'
        assert call_args[1]['params']['limit'] == 10
    
    @patch('aitbc_cli.commands.marketplace.httpx.Client')
    def test_bid_details(self, mock_client_class, runner, mock_config):
        """Test getting bid details"""
        # Setup mock
        mock_client = Mock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "bid123",
            "provider": "miner123",
            "capacity": 100,
            "price": 0.05,
            "notes": "Need GPU capacity for AI training",
            "status": "pending",
            "submitted_at": "2024-01-01T00:00:00"
        }
        mock_client.get.return_value = mock_response
        
        # Run command
        result = runner.invoke(marketplace, [
            'bid',
            'details',
            'bid123'
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        # Assertions
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data['id'] == 'bid123'
        assert data['provider'] == 'miner123'
        assert data['capacity'] == 100
        assert data['price'] == 0.05
        assert data['notes'] == 'Need GPU capacity for AI training'
        assert data['status'] == 'pending'
        
        # Verify API call
        mock_client.get.assert_called_once_with(
            'http://test:8000/v1/marketplace/bids/bid123',
            headers={"X-Api-Key": "test_api_key"}
        )
    
    @patch('aitbc_cli.commands.marketplace.httpx.Client')
    def test_bid_details_not_found(self, mock_client_class, runner, mock_config):
        """Test getting details for non-existent bid"""
        # Setup mock for 404 response
        mock_client = Mock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_response = Mock()
        mock_response.status_code = 404
        mock_client.get.return_value = mock_response
        
        # Run command
        result = runner.invoke(marketplace, [
            'bid',
            'details',
            'nonexistent'
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        # Assertions
        assert result.exit_code == 0
        assert 'Bid not found: 404' in result.output


class TestMarketplaceOffersCommands:
    """Test marketplace offers command group"""
    
    @patch('aitbc_cli.commands.marketplace.httpx.Client')
    def test_offers_list_all(self, mock_client_class, runner, mock_config):
        """Test listing all offers"""
        # Setup mock
        mock_client = Mock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "offers": [
                {
                    "id": "offer1",
                    "provider": "miner1",
                    "capacity": 200,
                    "price": 0.10,
                    "status": "open",
                    "gpu_model": "RTX4090",
                    "gpu_memory_gb": 24,
                    "region": "us-west"
                },
                {
                    "id": "offer2", 
                    "provider": "miner2",
                    "capacity": 100,
                    "price": 0.08,
                    "status": "reserved",
                    "gpu_model": "RTX3080",
                    "gpu_memory_gb": 10,
                    "region": "us-east"
                }
            ]
        }
        mock_client.get.return_value = mock_response
        
        # Run command
        result = runner.invoke(marketplace, [
            'offers',
            'list'
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        # Assertions
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data['offers']) == 2
        assert data['offers'][0]['gpu_model'] == 'RTX4090'
        assert data['offers'][0]['status'] == 'open'
        
        # Verify API call
        mock_client.get.assert_called_once_with(
            'http://test:8000/v1/marketplace/offers',
            params={"limit": 20},
            headers={"X-Api-Key": "test_api_key"}
        )
    
    @patch('aitbc_cli.commands.marketplace.httpx.Client')
    def test_offers_list_with_filters(self, mock_client_class, runner, mock_config):
        """Test listing offers with filters"""
        # Setup mock
        mock_client = Mock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "offers": [
                {
                    "id": "offer1",
                    "provider": "miner1",
                    "capacity": 200,
                    "price": 0.10,
                    "status": "open",
                    "gpu_model": "RTX4090",
                    "gpu_memory_gb": 24,
                    "region": "us-west"
                }
            ]
        }
        mock_client.get.return_value = mock_response
        
        # Run command with filters
        result = runner.invoke(marketplace, [
            'offers',
            'list',
            '--status', 'open',
            '--gpu-model', 'RTX4090',
            '--price-max', '0.15',
            '--memory-min', '16',
            '--region', 'us-west',
            '--limit', '10'
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        # Assertions
        assert result.exit_code == 0
        
        # Verify API call with filters
        mock_client.get.assert_called_once()
        call_args = mock_client.get.call_args
        params = call_args[1]['params']
        assert params['status'] == 'open'
        assert params['gpu_model'] == 'RTX4090'
        assert params['price_max'] == 0.15
        assert params['memory_min'] == 16
        assert params['region'] == 'us-west'
        assert params['limit'] == 10


class TestMarketplaceBidIntegration:
    """Test marketplace bid integration workflows"""
    
    @patch('aitbc_cli.commands.marketplace.httpx.Client')
    def test_complete_bid_workflow(self, mock_client_class, runner, mock_config):
        """Test complete workflow: list offers -> submit bid -> track status"""
        mock_client = Mock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        
        # Step 1: List offers
        offers_response = Mock()
        offers_response.status_code = 200
        offers_response.json.return_value = {
            "offers": [
                {
                    "id": "offer1",
                    "provider": "miner1",
                    "capacity": 200,
                    "price": 0.10,
                    "status": "open",
                    "gpu_model": "RTX4090"
                }
            ]
        }
        
        # Step 2: Submit bid
        bid_response = Mock()
        bid_response.status_code = 202
        bid_response.json.return_value = {
            "id": "bid123",
            "status": "pending"
        }
        
        # Step 3: Get bid details
        bid_details_response = Mock()
        bid_details_response.status_code = 200
        bid_details_response.json.return_value = {
            "id": "bid123",
            "provider": "miner123",
            "capacity": 100,
            "price": 0.05,
            "status": "pending",
            "submitted_at": "2024-01-01T00:00:00"
        }
        
        # Configure mock to return different responses for different calls
        mock_client.get.side_effect = [offers_response, bid_details_response]
        mock_client.post.return_value = bid_response
        
        # Execute workflow
        # List offers
        result1 = runner.invoke(marketplace, [
            'offers',
            'list',
            '--status', 'open'
        ], obj={'config': mock_config, 'output_format': 'json'})
        assert result1.exit_code == 0
        
        # Submit bid
        result2 = runner.invoke(marketplace, [
            'bid',
            'submit',
            '--provider', 'miner123',
            '--capacity', '100',
            '--price', '0.05'
        ], obj={'config': mock_config, 'output_format': 'json'})
        assert result2.exit_code == 0
        
        # Check bid details
        result3 = runner.invoke(marketplace, [
            'bid',
            'details',
            'bid123'
        ], obj={'config': mock_config, 'output_format': 'json'})
        assert result3.exit_code == 0
        
        # Verify all API calls were made
        assert mock_client.get.call_count == 2
        assert mock_client.post.call_count == 1
