"""Tests for client CLI commands"""

import pytest
import json
from click.testing import CliRunner
from unittest.mock import Mock, patch
from aitbc_cli.commands.client import client


@pytest.fixture
def runner():
    """Create CLI runner"""
    return CliRunner()


@pytest.fixture
def mock_config():
    """Mock configuration"""
    config = Mock()
    config.coordinator_url = "http://test:8000"
    config.api_key = "test_key"
    return config


class TestClientCommands:
    """Test client command group"""
    
    @patch('aitbc_cli.commands.client.httpx.Client')
    def test_submit_job_success(self, mock_client_class, runner, mock_config):
        """Test successful job submission"""
        # Setup mock
        mock_client = Mock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"job_id": "test_job_123"}
        mock_client.post.return_value = mock_response
        
        # Run command
        result = runner.invoke(client, [
            'submit',
            '--type', 'inference',
            '--prompt', 'Test prompt',
            '--model', 'test_model'
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        # Assertions
        assert result.exit_code == 0
        assert 'job_id' in result.output
        
        # Verify API call
        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        assert '/v1/jobs' in call_args[0][0]
        assert call_args[1]['json']['payload']['type'] == 'inference'
        assert call_args[1]['json']['payload']['prompt'] == 'Test prompt'
    
    @patch('aitbc_cli.commands.client.httpx.Client')
    def test_submit_job_from_file(self, mock_client_class, runner, mock_config, tmp_path):
        """Test job submission from file"""
        # Create test job file
        job_file = tmp_path / "test_job.json"
        job_data = {
            "type": "training",
            "model": "gpt-3",
            "dataset": "test_data"
        }
        job_file.write_text(json.dumps(job_data))
        
        # Setup mock
        mock_client = Mock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"job_id": "test_job_456"}
        mock_client.post.return_value = mock_response
        
        # Run command
        result = runner.invoke(client, [
            'submit',
            '--file', str(job_file)
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        # Assertions
        assert result.exit_code == 0
        assert 'job_id' in result.output
        
        # Verify API call used file data
        call_args = mock_client.post.call_args
        assert call_args[1]['json']['payload']['type'] == 'training'
        assert call_args[1]['json']['payload']['model'] == 'gpt-3'
    
    @patch('aitbc_cli.commands.client.httpx.Client')
    def test_status_success(self, mock_client_class, runner, mock_config):
        """Test successful job status check"""
        # Setup mock
        mock_client = Mock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "job_id": "test_job_123",
            "state": "completed",
            "result": "Test result"
        }
        mock_client.get.return_value = mock_response
        
        # Run command
        result = runner.invoke(client, [
            'status',
            'test_job_123'
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        # Assertions
        assert result.exit_code == 0
        assert 'completed' in result.output
        assert 'test_job_123' in result.output
        
        # Verify API call
        mock_client.get.assert_called_once_with(
            'http://test:8000/v1/jobs/test_job_123',
            headers={"X-Api-Key": "test_key"}
        )
    
    @patch('aitbc_cli.commands.client.httpx.Client')
    def test_cancel_job_success(self, mock_client_class, runner, mock_config):
        """Test successful job cancellation"""
        # Setup mock
        mock_client = Mock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_response = Mock()
        mock_response.status_code = 200
        mock_client.post.return_value = mock_response
        
        # Run command
        result = runner.invoke(client, [
            'cancel',
            'test_job_123'
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        # Assertions
        assert result.exit_code == 0
        
        # Verify API call
        mock_client.post.assert_called_once_with(
            'http://test:8000/v1/jobs/test_job_123/cancel',
            headers={"X-Api-Key": "test_key"}
        )
    
    @patch('aitbc_cli.commands.client.httpx.Client')
    def test_blocks_success(self, mock_client_class, runner, mock_config):
        """Test successful blocks listing"""
        # Setup mock
        mock_client = Mock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "items": [
                {"height": 100, "hash": "0x123"},
                {"height": 101, "hash": "0x456"}
            ]
        }
        mock_client.get.return_value = mock_response
        
        # Run command
        result = runner.invoke(client, [
            'blocks',
            '--limit', '2'
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        # Assertions
        assert result.exit_code == 0
        assert 'items' in result.output
        
        # Verify API call
        mock_client.get.assert_called_once()
        call_args = mock_client.get.call_args
        assert '/v1/explorer/blocks' in call_args[0][0]
        assert call_args[1]['params']['limit'] == 2
    
    @patch('aitbc_cli.commands.client.httpx.Client')
    def test_history_with_filters(self, mock_client_class, runner, mock_config):
        """Test job history with filters"""
        # Setup mock
        mock_client = Mock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "jobs": [
                {"id": "job1", "status": "completed"},
                {"id": "job2", "status": "failed"}
            ]
        }
        mock_client.get.return_value = mock_response
        
        # Run command with filters
        result = runner.invoke(client, [
            'history',
            '--status', 'completed',
            '--type', 'inference',
            '--limit', '10'
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        # Assertions
        assert result.exit_code == 0
        
        # Verify API call with filters
        mock_client.get.assert_called_once()
        call_args = mock_client.get.call_args
        assert call_args[1]['params']['status'] == 'completed'
        assert call_args[1]['params']['type'] == 'inference'
        assert call_args[1]['params']['limit'] == 10
    
    @patch('aitbc_cli.commands.client.httpx.Client')
    def test_api_error_handling(self, mock_client_class, runner, mock_config):
        """Test API error handling"""
        # Setup mock for error response
        mock_client = Mock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_client.get.return_value = mock_response
        
        # Run command
        result = runner.invoke(client, [
            'status',
            'test_job_123'
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        # Assertions
        assert result.exit_code != 0
        assert 'Error' in result.output
    
    def test_submit_missing_required_args(self, runner, mock_config):
        """Test submit command with missing required arguments"""
        result = runner.invoke(client, [
            'submit'
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        assert result.exit_code != 0
        assert 'Error' in result.output
