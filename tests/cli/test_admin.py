"""Tests for admin CLI commands"""

import pytest
import json
from click.testing import CliRunner
from unittest.mock import Mock, patch
from aitbc_cli.commands.admin import admin


@pytest.fixture
def runner():
    """Create CLI runner"""
    return CliRunner()


@pytest.fixture
def mock_config():
    """Mock configuration"""
    config = Mock()
    config.coordinator_url = "http://test:8000"
    config.api_key = "test_admin_key"
    return config


class TestAdminCommands:
    """Test admin command group"""
    
    @patch('aitbc_cli.commands.admin.httpx.Client')
    def test_status_success(self, mock_client_class, runner, mock_config):
        """Test successful system status check"""
        # Setup mock
        mock_client = Mock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "healthy",
            "version": "1.0.0",
            "uptime": 3600
        }
        mock_client.get.return_value = mock_response
        
        # Run command
        result = runner.invoke(admin, [
            'status'
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        # Assertions
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data['status'] == 'healthy'
        assert data['version'] == '1.0.0'
        
        # Verify API call
        mock_client.get.assert_called_once_with(
            'http://test:8000/v1/admin/status',
            headers={"X-Api-Key": "test_admin_key"}
        )
    
    @patch('aitbc_cli.commands.admin.httpx.Client')
    def test_jobs_with_filter(self, mock_client_class, runner, mock_config):
        """Test jobs listing with filters"""
        # Setup mock
        mock_client = Mock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "jobs": [
                {"id": "job1", "status": "completed"},
                {"id": "job2", "status": "running"}
            ]
        }
        mock_client.get.return_value = mock_response
        
        # Run command with filters
        result = runner.invoke(admin, [
            'jobs',
            '--status', 'running',
            '--limit', '50'
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        # Assertions
        assert result.exit_code == 0
        
        # Verify API call with filters
        mock_client.get.assert_called_once()
        call_args = mock_client.get.call_args
        assert '/v1/admin/jobs' in call_args[0][0]
        assert call_args[1]['params']['status'] == 'running'
        assert call_args[1]['params']['limit'] == 50
    
    @patch('aitbc_cli.commands.admin.httpx.Client')
    def test_job_details_success(self, mock_client_class, runner, mock_config):
        """Test successful job details retrieval"""
        # Setup mock
        mock_client = Mock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "job123",
            "status": "completed",
            "result": "Test result",
            "created_at": "2024-01-01T00:00:00"
        }
        mock_client.get.return_value = mock_response
        
        # Run command
        result = runner.invoke(admin, [
            'job-details',
            'job123'
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        # Assertions
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data['id'] == 'job123'
        assert data['status'] == 'completed'
        
        # Verify API call
        mock_client.get.assert_called_once_with(
            'http://test:8000/v1/admin/jobs/job123',
            headers={"X-Api-Key": "test_admin_key"}
        )
    
    @patch('aitbc_cli.commands.admin.httpx.Client')
    def test_delete_job_confirmed(self, mock_client_class, runner, mock_config):
        """Test successful job deletion with confirmation"""
        # Setup mock
        mock_client = Mock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_response = Mock()
        mock_response.status_code = 200
        mock_client.delete.return_value = mock_response
        
        # Run command with confirmation
        result = runner.invoke(admin, [
            'delete-job',
            'job123'
        ], obj={'config': mock_config, 'output_format': 'json'}, input='y\n')
        
        # Assertions
        assert result.exit_code == 0
        assert 'deleted' in result.output
        
        # Verify API call
        mock_client.delete.assert_called_once_with(
            'http://test:8000/v1/admin/jobs/job123',
            headers={"X-Api-Key": "test_admin_key"}
        )
    
    def test_delete_job_cancelled(self, runner, mock_config):
        """Test job deletion cancelled by user"""
        # Run command with cancellation
        result = runner.invoke(admin, [
            'delete-job',
            'job123'
        ], obj={'config': mock_config, 'output_format': 'json'}, input='n\n')
        
        # Assertions
        assert result.exit_code == 0
        # No API calls should be made
    
    @patch('aitbc_cli.commands.admin.httpx.Client')
    def test_miners_list(self, mock_client_class, runner, mock_config):
        """Test miners listing"""
        # Setup mock
        mock_client = Mock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "miners": [
                {"id": "miner1", "status": "active", "gpu": "RTX4090"},
                {"id": "miner2", "status": "inactive", "gpu": "RTX3080"}
            ]
        }
        mock_client.get.return_value = mock_response
        
        # Run command
        result = runner.invoke(admin, [
            'miners'
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        # Assertions
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data['miners']) == 2
        
        # Verify API call
        mock_client.get.assert_called_once_with(
            'http://test:8000/v1/admin/miners',
            params={"limit": 50},
            headers={"X-Api-Key": "test_admin_key"}
        )
    
    @patch('aitbc_cli.commands.admin.httpx.Client')
    def test_deactivate_miner(self, mock_client_class, runner, mock_config):
        """Test miner deactivation"""
        # Setup mock
        mock_client = Mock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_response = Mock()
        mock_response.status_code = 200
        mock_client.post.return_value = mock_response
        
        # Run command with confirmation
        result = runner.invoke(admin, [
            'deactivate-miner',
            'miner123'
        ], obj={'config': mock_config, 'output_format': 'json'}, input='y\n')
        
        # Assertions
        assert result.exit_code == 0
        assert 'deactivated' in result.output
        
        # Verify API call
        mock_client.post.assert_called_once_with(
            'http://test:8000/v1/admin/miners/miner123/deactivate',
            headers={"X-Api-Key": "test_admin_key"}
        )
    
    @patch('aitbc_cli.commands.admin.httpx.Client')
    def test_analytics(self, mock_client_class, runner, mock_config):
        """Test system analytics"""
        # Setup mock
        mock_client = Mock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "total_jobs": 1000,
            "completed_jobs": 950,
            "active_miners": 50,
            "average_processing_time": 120
        }
        mock_client.get.return_value = mock_response
        
        # Run command
        result = runner.invoke(admin, [
            'analytics',
            '--days', '7'
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        # Assertions
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data['total_jobs'] == 1000
        assert data['active_miners'] == 50
        
        # Verify API call
        mock_client.get.assert_called_once()
        call_args = mock_client.get.call_args
        assert '/v1/admin/analytics' in call_args[0][0]
        assert call_args[1]['params']['days'] == 7
    
    @patch('aitbc_cli.commands.admin.httpx.Client')
    def test_logs_with_level(self, mock_client_class, runner, mock_config):
        """Test system logs with level filter"""
        # Setup mock
        mock_client = Mock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "logs": [
                {"level": "ERROR", "message": "Test error", "timestamp": "2024-01-01T00:00:00"}
            ]
        }
        mock_client.get.return_value = mock_response
        
        # Run command
        result = runner.invoke(admin, [
            'logs',
            '--level', 'ERROR',
            '--limit', '50'
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        # Assertions
        assert result.exit_code == 0
        
        # Verify API call
        mock_client.get.assert_called_once()
        call_args = mock_client.get.call_args
        assert '/v1/admin/logs' in call_args[0][0]
        assert call_args[1]['params']['level'] == 'ERROR'
        assert call_args[1]['params']['limit'] == 50
    
    @patch('aitbc_cli.commands.admin.httpx.Client')
    def test_prioritize_job(self, mock_client_class, runner, mock_config):
        """Test job prioritization"""
        # Setup mock
        mock_client = Mock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_response = Mock()
        mock_response.status_code = 200
        mock_client.post.return_value = mock_response
        
        # Run command
        result = runner.invoke(admin, [
            'prioritize-job',
            'job123',
            '--reason', 'Urgent request'
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        # Assertions
        assert result.exit_code == 0
        assert 'prioritized' in result.output
        
        # Verify API call
        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        assert '/v1/admin/jobs/job123/prioritize' in call_args[0][0]
        assert call_args[1]['json']['reason'] == 'Urgent request'
    
    @patch('aitbc_cli.commands.admin.httpx.Client')
    def test_execute_custom_action(self, mock_client_class, runner, mock_config):
        """Test custom action execution"""
        # Setup mock
        mock_client = Mock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "success", "result": "Action completed"}
        mock_client.post.return_value = mock_response
        
        # Run command
        result = runner.invoke(admin, [
            'execute',
            '--action', 'custom_command',
            '--target', 'miner123',
            '--data', '{"param": "value"}'
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        # Assertions
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data['status'] == 'success'
        
        # Verify API call
        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        assert '/v1/admin/execute/custom_command' in call_args[0][0]
        assert call_args[1]['json']['target'] == 'miner123'
        assert call_args[1]['json']['param'] == 'value'
    
    @patch('aitbc_cli.commands.admin.httpx.Client')
    def test_maintenance_cleanup(self, mock_client_class, runner, mock_config):
        """Test maintenance cleanup"""
        # Setup mock
        mock_client = Mock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"cleaned_items": 100}
        mock_client.post.return_value = mock_response
        
        # Run command with confirmation
        result = runner.invoke(admin, [
            'maintenance',
            'cleanup'
        ], obj={'config': mock_config, 'output_format': 'json'}, input='y\n')
        
        # Assertions
        assert result.exit_code == 0
        assert 'Cleanup completed' in result.output
        
        # Verify API call
        mock_client.post.assert_called_once_with(
            'http://test:8000/v1/admin/maintenance/cleanup',
            headers={"X-Api-Key": "test_admin_key"}
        )
    
    @patch('aitbc_cli.commands.admin.httpx.Client')
    def test_api_error_handling(self, mock_client_class, runner, mock_config):
        """Test API error handling"""
        # Setup mock for error response
        mock_client = Mock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_response = Mock()
        mock_response.status_code = 403
        mock_client.get.return_value = mock_response
        
        # Run command
        result = runner.invoke(admin, [
            'status'
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        # Assertions
        assert result.exit_code != 0
        assert 'Error' in result.output
