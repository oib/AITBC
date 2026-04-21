"""Tests for marketplace CLI commands"""

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


class TestMarketplaceCommands:
    """Test marketplace command group"""
    
    @patch('aitbc_cli.commands.marketplace.httpx.Client')
    def test_gpu_list_all(self, mock_client_class, runner, mock_config):
        """Test listing all GPUs"""
        # Setup mock
        mock_client = Mock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "gpus": [
                {
                    "id": "gpu1",
                    "model": "RTX4090",
                    "memory": "24GB",
                    "price_per_hour": 0.5,
                    "available": True,
                    "provider": "miner1"
                },
                {
                    "id": "gpu2",
                    "model": "RTX3080",
                    "memory": "10GB",
                    "price_per_hour": 0.3,
                    "available": False,
                    "provider": "miner2"
                }
            ]
        }
        mock_client.get.return_value = mock_response
        
        # Run command
        result = runner.invoke(marketplace, [
            'gpu',
            'list'
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        # Assertions
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data['gpus']) == 2
        assert data['gpus'][0]['model'] == 'RTX4090'
        assert data['gpus'][0]['available'] == True
        
        # Verify API call
        mock_client.get.assert_called_once_with(
            'http://test:8000/v1/marketplace/gpu/list',
            params={"limit": 20},
            headers={"X-Api-Key": "test_api_key"}
        )
    
    @patch('aitbc_cli.commands.marketplace.httpx.Client')
    def test_gpu_list_available(self, mock_client_class, runner, mock_config):
        """Test listing only available GPUs"""
        # Setup mock
        mock_client = Mock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "gpus": [
                {
                    "id": "gpu1",
                    "model": "RTX4090",
                    "memory": "24GB",
                    "price_per_hour": 0.5,
                    "available": True,
                    "provider": "miner1"
                }
            ]
        }
        mock_client.get.return_value = mock_response
        
        # Run command
        result = runner.invoke(marketplace, [
            'gpu',
            'list',
            '--available'
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        # Assertions
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data['gpus']) == 1
        assert data['gpus'][0]['available'] == True
        
        # Verify API call
        mock_client.get.assert_called_once_with(
            'http://test:8000/v1/marketplace/gpu/list',
            params={"available": "true", "limit": 20},
            headers={"X-Api-Key": "test_api_key"}
        )
    
    @patch('aitbc_cli.commands.marketplace.httpx.Client')
    def test_gpu_list_with_filters(self, mock_client_class, runner, mock_config):
        """Test listing GPUs with filters"""
        # Setup mock
        mock_client = Mock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "gpus": [
                {
                    "id": "gpu1",
                    "model": "RTX4090",
                    "memory": "24GB",
                    "price_per_hour": 0.5,
                    "available": True,
                    "provider": "miner1"
                }
            ]
        }
        mock_client.get.return_value = mock_response
        
        # Run command with filters
        result = runner.invoke(marketplace, [
            'gpu',
            'list',
            '--model', 'RTX4090',
            '--memory-min', '16',
            '--price-max', '1.0'
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        # Assertions
        assert result.exit_code == 0
        
        # Verify API call with filters
        mock_client.get.assert_called_once()
        call_args = mock_client.get.call_args
        assert call_args[1]['params']['model'] == 'RTX4090'
        assert call_args[1]['params']['memory_min'] == 16
        assert call_args[1]['params']['price_max'] == 1.0
    
    @patch('aitbc_cli.commands.marketplace.httpx.Client')
    def test_gpu_details(self, mock_client_class, runner, mock_config):
        """Test getting GPU details"""
        # Setup mock
        mock_client = Mock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "gpu1",
            "model": "RTX4090",
            "memory": "24GB",
            "price_per_hour": 0.5,
            "available": True,
            "provider": "miner1",
            "specs": {
                "cuda_cores": 16384,
                "tensor_cores": 512,
                "base_clock": 2230
            },
            "location": "us-west",
            "rating": 4.8
        }
        mock_client.get.return_value = mock_response
        
        # Run command
        result = runner.invoke(marketplace, [
            'gpu',
            'details',
            'gpu1'
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        # Assertions
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data['id'] == 'gpu1'
        assert data['model'] == 'RTX4090'
        assert data['specs']['cuda_cores'] == 16384
        assert data['rating'] == 4.8
        
        # Verify API call
        mock_client.get.assert_called_once_with(
            'http://test:8000/v1/marketplace/gpu/gpu1',
            headers={"X-Api-Key": "test_api_key"}
        )
    
    @patch('aitbc_cli.commands.marketplace.httpx.Client')
    def test_gpu_book(self, mock_client_class, runner, mock_config):
        """Test booking a GPU"""
        # Setup mock
        mock_client = Mock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "booking_id": "booking123",
            "gpu_id": "gpu1",
            "duration_hours": 2,
            "total_cost": 1.0,
            "status": "booked"
        }
        mock_client.post.return_value = mock_response
        
        # Run command
        result = runner.invoke(marketplace, [
            'gpu',
            'book',
            'gpu1',
            '--hours', '2'
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        # Assertions
        assert result.exit_code == 0
        # Extract JSON from output (success message + JSON)
        # Remove ANSI escape codes
        import re
        clean_output = re.sub(r'\x1b\[[0-9;]*m', '', result.output)
        lines = clean_output.strip().split('\n')
        
        # Find all lines that contain JSON and join them
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
        assert data['booking_id'] == 'booking123'
        assert data['status'] == 'booked'
        assert data['total_cost'] == 1.0
        
        # Verify API call
        mock_client.post.assert_called_once_with(
            'http://test:8000/v1/marketplace/gpu/gpu1/book',
            json={"gpu_id": "gpu1", "duration_hours": 2.0},
            headers={
                "Content-Type": "application/json",
                "X-Api-Key": "test_api_key"
            }
        )
    
    @patch('aitbc_cli.commands.marketplace.httpx.Client')
    def test_gpu_release(self, mock_client_class, runner, mock_config):
        """Test releasing a GPU"""
        # Setup mock
        mock_client = Mock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "released",
            "gpu_id": "gpu1",
            "refund": 0.5,
            "message": "GPU gpu1 released successfully"
        }
        mock_client.post.return_value = mock_response
        
        # Run command
        result = runner.invoke(marketplace, [
            'gpu',
            'release',
            'gpu1'
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        # Assertions
        assert result.exit_code == 0
        # Extract JSON from output (success message + JSON)
        # Remove ANSI escape codes
        import re
        clean_output = re.sub(r'\x1b\[[0-9;]*m', '', result.output)
        lines = clean_output.strip().split('\n')
        
        # Find all lines that contain JSON and join them
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
        assert data['status'] == 'released'
        assert data['gpu_id'] == 'gpu1'
        
        # Verify API call
        mock_client.post.assert_called_once_with(
            'http://test:8000/v1/marketplace/gpu/gpu1/release',
            headers={"X-Api-Key": "test_api_key"}
        )
    
    @patch('aitbc_cli.commands.marketplace.httpx.Client')
    def test_orders_list(self, mock_client_class, runner, mock_config):
        """Test listing orders"""
        # Setup mock
        mock_client = Mock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
                {
                    "order_id": "order123",
                    "gpu_id": "gpu1",
                    "gpu_model": "RTX 4090",
                    "status": "active",
                    "duration_hours": 2,
                    "total_cost": 1.0,
                    "created_at": "2024-01-01T00:00:00"
                }
            ]
        mock_client.get.return_value = mock_response
        
        # Run command
        result = runner.invoke(marketplace, [
            'orders'
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        # Assertions
        assert result.exit_code == 0
        # Extract JSON from output
        import re
        clean_output = re.sub(r'\x1b\[[0-9;]*m', '', result.output)
        lines = clean_output.strip().split('\n')
        
        # Find all lines that contain JSON and join them
        json_lines = []
        in_json = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith('['):
                in_json = True
                json_lines.append(stripped)
            elif in_json:
                json_lines.append(stripped)
                if stripped.endswith(']'):
                    break
        
        json_str = '\n'.join(json_lines)
        assert json_str, "No JSON found in output"
        data = json.loads(json_str)
        assert len(data) == 1
        assert data[0]['status'] == 'active'
        
        # Verify API call
        mock_client.get.assert_called_once_with(
            'http://test:8000/v1/marketplace/orders',
            params={"limit": 10},
            headers={"X-Api-Key": "test_api_key"}
        )
    
    @patch('aitbc_cli.commands.marketplace.httpx.Client')
    def test_pricing_info(self, mock_client_class, runner, mock_config):
        """Test getting pricing information"""
        # Setup mock
        mock_client = Mock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "average_price": 0.4,
            "price_range": {
                "min": 0.2,
                "max": 0.8
            },
            "price_by_model": {
                "RTX4090": 0.5,
                "RTX3080": 0.3,
                "A100": 1.0
            }
        }
        mock_client.get.return_value = mock_response
        
        # Run command
        result = runner.invoke(marketplace, [
            'pricing',
            'RTX4090'
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        # Assertions
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data['average_price'] == 0.4
        assert data['price_range']['min'] == 0.2
        assert data['price_by_model']['RTX4090'] == 0.5
        
        # Verify API call
        mock_client.get.assert_called_once_with(
            'http://test:8000/v1/marketplace/pricing/RTX4090',
            headers={"X-Api-Key": "test_api_key"}
        )
    
    @patch('aitbc_cli.commands.marketplace.httpx.Client')
    def test_reviews_list(self, mock_client_class, runner, mock_config):
        """Test listing reviews for a GPU"""
        # Setup mock
        mock_client = Mock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "reviews": [
                {
                    "id": "review1",
                    "user": "user1",
                    "rating": 5,
                    "comment": "Excellent performance!",
                    "created_at": "2024-01-01T00:00:00"
                },
                {
                    "id": "review2",
                    "user": "user2",
                    "rating": 4,
                    "comment": "Good value for money",
                    "created_at": "2024-01-02T00:00:00"
                }
            ]
        }
        mock_client.get.return_value = mock_response
        
        # Run command
        result = runner.invoke(marketplace, [
            'reviews',
            'gpu1'
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        # Assertions
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data['reviews']) == 2
        assert data['reviews'][0]['rating'] == 5
        
        # Verify API call
        mock_client.get.assert_called_once_with(
            'http://test:8000/v1/marketplace/gpu/gpu1/reviews',
            params={"limit": 10},
            headers={"X-Api-Key": "test_api_key"}
        )
    
    @patch('aitbc_cli.commands.marketplace.httpx.Client')
    def test_add_review(self, mock_client_class, runner, mock_config):
        """Test adding a review for a GPU"""
        # Setup mock
        mock_client = Mock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "status": "review_added",
            "gpu_id": "gpu1",
            "review_id": "review_1",
            "average_rating": 5.0
        }
        mock_client.post.return_value = mock_response
        
        # Run command
        result = runner.invoke(marketplace, [
            'review',
            'gpu1',
            '--rating', '5',
            '--comment', 'Amazing GPU!'
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        # Assertions
        assert result.exit_code == 0
        # Extract JSON from output (success message + JSON)
        # Remove ANSI escape codes
        import re
        clean_output = re.sub(r'\x1b\[[0-9;]*m', '', result.output)
        lines = clean_output.strip().split('\n')
        
        # Find all lines that contain JSON and join them
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
        assert data['status'] == 'review_added'
        assert data['gpu_id'] == 'gpu1'
        
        # Verify API call
        mock_client.post.assert_called_once_with(
            'http://test:8000/v1/marketplace/gpu/gpu1/reviews',
            json={"rating": 5, "comment": "Amazing GPU!"},
            headers={
                "Content-Type": "application/json",
                "X-Api-Key": "test_api_key"
            }
        )
    
    @patch('aitbc_cli.commands.marketplace.httpx.Client')
    def test_api_error_handling(self, mock_client_class, runner, mock_config):
        """Test API error handling"""
        # Setup mock for error response
        mock_client = Mock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_response = Mock()
        mock_response.status_code = 404
        mock_client.get.return_value = mock_response
        
        # Run command
        result = runner.invoke(marketplace, [
            'gpu',
            'details',
            'nonexistent'
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        # Assertions
        assert result.exit_code == 0  # The command doesn't exit on error
        assert 'not found' in result.output
