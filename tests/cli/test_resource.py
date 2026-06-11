"""Integration tests for resource CLI commands

These tests require coordinator-api running and validate resource allocation,
utilization tracking, and API interactions with actual service calls.
"""

import json
from unittest.mock import MagicMock, Mock, patch

import httpx
import pytest
from aitbc_cli.commands.resource import resource
from click.testing import CliRunner

from aitbc import AITBCHTTPClient
from aitbc_cli.utils.http_client import NetworkError


@pytest.fixture
def runner():
    """Create CLI runner"""
    return CliRunner()


@pytest.fixture
def mock_config():
    """Mock configuration"""
    config = Mock()
    config.coordinator_url = "http://127.0.0.1:18000"
    config.api_key = "test_api_key"
    return config


@pytest.fixture
def mock_http_client():
    """Mock HTTP client for coordinator-api"""
    client = MagicMock(spec=AITBCHTTPClient)
    return client


class TestResourceCommands:
    """Integration tests for resource commands with coordinator-api"""

    @pytest.fixture
    def coordinator_available(self):
        """Skip test if coordinator-api is not running"""
        try:
            response = httpx.get("http://127.0.0.1:18000/health", timeout=2)
            if response.status_code == 200:
                return True
        except Exception:
            pytest.skip("coordinator-api not running at http://127.0.0.1:18000")

    @patch('aitbc_cli.commands.resource.get_config')
    @patch('aitbc_cli.commands.resource.AITBCHTTPClient')
    def test_resource_status_all(self, mock_http_client_class, mock_get_config, runner):
        """Test getting status of all resources"""
        # Setup mocks
        mock_config = Mock()
        mock_config.coordinator_url = "http://127.0.0.1:18000"
        mock_get_config.return_value = mock_config

        mock_client = MagicMock()
        mock_http_client_class.return_value = mock_client
        mock_client.get.return_value = {
            "resources": [
                {"id": "res_1", "type": "gpu", "status": "allocated"},
                {"id": "res_2", "type": "cpu", "status": "available"}
            ]
        }

        result = runner.invoke(resource, [
            'status'
        ], obj={'config': mock_config, 'output': 'json'})

        assert result.exit_code == 0
        mock_client.get.assert_called_once_with("/api/v1/resources/status")

    @patch('aitbc_cli.commands.resource.get_config')
    @patch('aitbc_cli.commands.resource.AITBCHTTPClient')
    def test_resource_status_specific(self, mock_http_client_class, mock_get_config, runner):
        """Test getting status of specific resource"""
        # Setup mocks
        mock_config = Mock()
        mock_config.coordinator_url = "http://127.0.0.1:18000"
        mock_get_config.return_value = mock_config

        mock_client = MagicMock()
        mock_http_client_class.return_value = mock_client
        mock_client.get.return_value = {
            "id": "res_123",
            "type": "gpu",
            "status": "allocated",
            "efficiency": "85.5%"
        }

        result = runner.invoke(resource, [
            'status',
            '--resource-id', 'res_123'
        ], obj={'config': mock_config, 'output': 'json'})

        assert result.exit_code == 0
        mock_client.get.assert_called_once_with("/api/v1/resources/res_123/status")

    @patch('aitbc_cli.commands.resource.get_config')
    @patch('aitbc_cli.commands.resource.AITBCHTTPClient')
    def test_resource_deallocate(self, mock_http_client_class, mock_get_config, runner):
        """Test deallocating a resource"""
        # Setup mocks
        mock_config = Mock()
        mock_config.coordinator_url = "http://127.0.0.1:18000"
        mock_get_config.return_value = mock_config

        mock_client = MagicMock()
        mock_http_client_class.return_value = mock_client
        mock_client.post.return_value = {
            "resource_id": "res_123",
            "status": "deallocated",
            "timestamp": "2026-05-27T08:30:00Z"
        }

        result = runner.invoke(resource, [
            'deallocate', 'res_123'
        ], obj={'config': mock_config, 'output': 'json'})

        assert result.exit_code == 0
        mock_client.post.assert_called_once_with("/api/v1/resources/res_123/deallocate")

    @patch('aitbc_cli.commands.resource.get_config')
    @patch('aitbc_cli.commands.resource.AITBCHTTPClient')
    def test_resource_deallocate_force(self, mock_http_client_class, mock_get_config, runner):
        """Test force deallocating a resource without confirmation"""
        # Setup mocks
        mock_config = Mock()
        mock_config.coordinator_url = "http://127.0.0.1:18000"
        mock_get_config.return_value = mock_config

        mock_client = MagicMock()
        mock_http_client_class.return_value = mock_client
        mock_client.post.return_value = {
            "resource_id": "res_123",
            "status": "deallocated"
        }

        result = runner.invoke(resource, [
            'deallocate', 'res_123',
            '--force'
        ], obj={'config': mock_config, 'output': 'json'})

        assert result.exit_code == 0
        mock_client.post.assert_called_once_with("/api/v1/resources/res_123/deallocate")

    @patch('aitbc_cli.commands.resource.get_config')
    @patch('aitbc_cli.commands.resource.AITBCHTTPClient')
    def test_resource_status_network_error(self, mock_http_client_class, mock_get_config, runner):
        """Test resource status with network error"""
        # Setup mocks
        mock_config = Mock()
        mock_config.coordinator_url = "http://127.0.0.1:18000"
        mock_get_config.return_value = mock_config

        mock_client = MagicMock()
        mock_http_client_class.return_value = mock_client
        mock_client.get.side_effect = NetworkError("Connection refused")

        result = runner.invoke(resource, [
            'status'
        ], obj={'config': mock_config, 'output': 'json'})

        assert result.exit_code != 0
        assert "Network error" in result.output

    @patch('aitbc_cli.commands.resource.get_config')
    @patch('aitbc_cli.commands.resource.AITBCHTTPClient')
    def test_resource_deallocate_network_error(self, mock_http_client_class, mock_get_config, runner):
        """Test resource deallocation with network error"""
        # Setup mocks
        mock_config = Mock()
        mock_config.coordinator_url = "http://127.0.0.1:18000"
        mock_get_config.return_value = mock_config

        mock_client = MagicMock()
        mock_http_client_class.return_value = mock_client
        mock_client.post.side_effect = NetworkError("Connection refused")

        result = runner.invoke(resource, [
            'deallocate', '--force', 'res_123'
        ], obj={'config': mock_config, 'output': 'json'})

        assert result.exit_code != 0
        assert "Network error" in result.output

    def test_resource_allocate_experimental_warning(self, runner, mock_config):
        """Test that allocate command shows experimental warning without --mock"""
        result = runner.invoke(resource, [
            'allocate',
            '--resource-type', 'gpu',
            '--quantity', '4'
        ], obj={'config': mock_config, 'output': 'table'})

        # Should fail with experimental warning
        assert result.exit_code != 0
        assert "EXPERIMENTAL" in result.output
        assert "--mock" in result.output

    def test_resource_list_experimental_warning(self, runner, mock_config):
        """Test that list command shows experimental warning without --mock"""
        result = runner.invoke(resource, [
            'list'
        ], obj={'config': mock_config, 'output': 'table'})

        # Should fail with experimental warning
        assert result.exit_code != 0
        assert "EXPERIMENTAL" in result.output
        assert "--mock" in result.output

    def test_resource_release_experimental_warning(self, runner, mock_config):
        """Test that release command shows experimental warning without --mock"""
        result = runner.invoke(resource, [
            'release', 'res_123'
        ], obj={'config': mock_config, 'output': 'table'})

        # Should fail with experimental warning
        assert result.exit_code != 0
        assert "EXPERIMENTAL" in result.output
        assert "--mock" in result.output

    def test_resource_utilization_experimental_warning(self, runner, mock_config):
        """Test that utilization command shows experimental warning without --mock"""
        result = runner.invoke(resource, [
            'utilization'
        ], obj={'config': mock_config, 'output': 'table'})

        # Should fail with experimental warning
        assert result.exit_code != 0
        assert "EXPERIMENTAL" in result.output
        assert "--mock" in result.output

    def test_resource_optimize_experimental_warning(self, runner, mock_config):
        """Test that optimize command shows experimental warning without --mock"""
        result = runner.invoke(resource, [
            'optimize'
        ], obj={'config': mock_config, 'output': 'table'})

        # Should fail with experimental warning
        assert result.exit_code != 0
        assert "EXPERIMENTAL" in result.output
        assert "--mock" in result.output

    @patch('aitbc_cli.commands.resource.get_config')
    @patch('aitbc_cli.commands.resource.AITBCHTTPClient')
    def test_resource_status_table_format(self, mock_http_client_class, mock_get_config, runner):
        """Test resource status in table format"""
        # Setup mocks
        mock_config = Mock()
        mock_config.coordinator_url = "http://127.0.0.1:18000"
        mock_get_config.return_value = mock_config

        mock_client = MagicMock()
        mock_http_client_class.return_value = mock_client
        mock_client.get.return_value = {
            "resources": [
                {"id": "res_1", "type": "gpu", "status": "allocated"}
            ]
        }

        result = runner.invoke(resource, [
            'status'
        ], obj={'config': mock_config, 'output': 'table'})

        assert result.exit_code == 0
        assert "Resource Status" in result.output

    @patch('aitbc_cli.commands.resource.get_config')
    @patch('aitbc_cli.commands.resource.AITBCHTTPClient')
    def test_resource_deallocate_with_confirmation(self, mock_http_client_class, mock_get_config, runner):
        """Test resource deallocation with user confirmation"""
        # Setup mocks
        mock_config = Mock()
        mock_config.coordinator_url = "http://127.0.0.1:18000"
        mock_get_config.return_value = mock_config

        mock_client = MagicMock()
        mock_http_client_class.return_value = mock_client
        mock_client.post.return_value = {
            "resource_id": "res_123",
            "status": "deallocated"
        }

        result = runner.invoke(resource, [
            'deallocate', 'res_123'
        ], obj={'config': mock_config, 'output': 'json'}, input='y\n')

        assert result.exit_code == 0
        mock_client.post.assert_called_once_with("/api/v1/resources/res_123/deallocate")

    @patch('aitbc_cli.commands.resource.get_config')
    @patch('aitbc_cli.commands.resource.AITBCHTTPClient')
    def test_resource_deallocate_cancelled(self, mock_http_client_class, mock_get_config, runner):
        """Test resource deallocation cancelled by user"""
        # Setup mocks
        mock_config = Mock()
        mock_config.coordinator_url = "http://127.0.0.1:18000"
        mock_get_config.return_value = mock_config

        mock_client = MagicMock()
        mock_http_client_class.return_value = mock_client

        result = runner.invoke(resource, [
            'deallocate', 'res_123'
        ], obj={'config': mock_config, 'output': 'json'}, input='n\n')

        assert result.exit_code == 0
        # Should not call post if cancelled
        mock_client.post.assert_not_called()

    @patch('aitbc_cli.commands.resource.get_config')
    @patch('aitbc_cli.commands.resource.AITBCHTTPClient')
    def test_resource_status_empty_response(self, mock_http_client_class, mock_get_config, runner):
        """Test resource status with empty response"""
        # Setup mocks
        mock_config = Mock()
        mock_config.coordinator_url = "http://127.0.0.1:18000"
        mock_get_config.return_value = mock_config

        mock_client = MagicMock()
        mock_http_client_class.return_value = mock_client
        mock_client.get.return_value = {}

        result = runner.invoke(resource, [
            'status'
        ], obj={'config': mock_config, 'output': 'json'})

        assert result.exit_code == 0
        mock_client.get.assert_called_once_with("/api/v1/resources/status")

    def test_resource_status_with_coordinator_api(self, runner, mock_config, coordinator_available):
        """Test resource status with actual coordinator-api call"""
        result = runner.invoke(resource, [
            'status'
        ], obj={'config': mock_config, 'output': 'json'})

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert 'resources' in data or isinstance(data, list)

    def test_resource_deallocate_with_coordinator_api(self, runner, mock_config, coordinator_available):
        """Test resource deallocation with actual coordinator-api call"""
        result = runner.invoke(resource, [
            'deallocate', 'test_res_123',
            '--force'
        ], obj={'config': mock_config, 'output': 'json'})

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert 'resource_id' in data or 'status' in data

    def test_resource_allocate_with_mock(self, runner, mock_config):
        """Test resource allocation with mock flag"""
        result = runner.invoke(resource, [
            'allocate',
            '--resource-type', 'gpu',
            '--quantity', '4',
            '--mock'
        ], obj={'config': mock_config, 'output': 'json'})

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert 'resource_id' in data or 'allocation_id' in data

    def test_resource_list_with_mock(self, runner, mock_config):
        """Test resource listing with mock flag"""
        result = runner.invoke(resource, [
            'list',
            '--mock'
        ], obj={'config': mock_config, 'output': 'json'})

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert 'resources' in data or isinstance(data, list)

    def test_resource_release_with_mock(self, runner, mock_config):
        """Test resource release with mock flag"""
        result = runner.invoke(resource, [
            'release', 'test_res_123',
            '--mock'
        ], obj={'config': mock_config, 'output': 'json'})

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert 'resource_id' in data or 'status' in data

    def test_resource_utilization_with_mock(self, runner, mock_config):
        """Test resource utilization with mock flag"""
        result = runner.invoke(resource, [
            'utilization',
            '--mock'
        ], obj={'config': mock_config, 'output': 'json'})

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert 'utilization' in data or 'metrics' in data

    def test_resource_optimize_with_mock(self, runner, mock_config):
        """Test resource optimization with mock flag"""
        result = runner.invoke(resource, [
            'optimize',
            '--mock'
        ], obj={'config': mock_config, 'output': 'json'})

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert 'optimization' in data or 'recommendations' in data

    def test_resource_allocate_with_parameters(self, runner, mock_config):
        """Test resource allocation with custom parameters"""
        result = runner.invoke(resource, [
            'allocate',
            '--resource-type', 'gpu',
            '--quantity', '8',
            '--min-memory', '32',
            '--mock'
        ], obj={'config': mock_config, 'output': 'json'})

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert 'resource_id' in data or 'allocation_id' in data

    def test_resource_status_filter_by_type(self, runner, mock_config, coordinator_available):
        """Test resource status filtered by resource type"""
        result = runner.invoke(resource, [
            'status',
            '--resource-type', 'gpu'
        ], obj={'config': mock_config, 'output': 'json'})

        assert result.exit_code == 0
        data = json.loads(result.output)
        # Verify filtering was applied
        if 'resources' in data and isinstance(data['resources'], list):
            for res in data['resources']:
                assert res.get('type') == 'gpu' or 'type' not in res

    def test_resource_api_error_handling(self, runner, mock_config):
        """Test resource command handles coordinator-api errors gracefully"""
        # Use invalid coordinator URL to trigger error
        mock_config.coordinator_url = "http://invalid:9999"

        result = runner.invoke(resource, [
            'status'
        ], obj={'config': mock_config, 'output': 'json'})

        # Should either fail gracefully or skip with appropriate message
        assert result.exit_code != 0 or 'error' in result.output.lower() or 'unavailable' in result.output.lower()
