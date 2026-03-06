"""Tests for deployment commands"""

import pytest
import json
import asyncio
from click.testing import CliRunner
from unittest.mock import Mock, patch, AsyncMock
from aitbc_cli.main import cli


@pytest.fixture
def runner():
    """Create CLI runner"""
    return CliRunner()


@pytest.fixture
def mock_config():
    """Mock configuration for testing"""
    return {
        'coordinator_url': 'http://localhost:8000',
        'api_key': 'test-key',
        'wallet_name': 'test-wallet'
    }


class TestDeployCommands:
    """Test suite for deployment operations"""
    
    def test_deploy_create_success(self, runner, mock_config):
        """Test successful deployment configuration creation"""
        with patch('aitbc_cli.config.get_config') as mock_get_config:
            mock_get_config.return_value = mock_config
            with patch('aitbc_cli.commands.deployment.ProductionDeployment') as mock_deployment_class:
                mock_deployment = Mock()
                mock_deployment.create_deployment = AsyncMock(return_value='deploy_123')
                mock_deployment_class.return_value = mock_deployment
                
                result = runner.invoke(cli, [
                    'deploy', 'create',
                    'test-app', 'production', 'us-west-1', 't3.medium',
                    '2', '5', '3', '8080', 'app.example.com',
                    '--db-host', 'db.example.com',
                    '--db-port', '5432',
                    '--db-name', 'aitbc_prod'
                ])
                
                assert result.exit_code == 0
                assert 'deployment configuration created' in result.output.lower()
                assert 'deploy_123' in result.output
                mock_deployment.create_deployment.assert_called_once()
                
    def test_deploy_create_failure(self, runner, mock_config):
        """Test deployment configuration creation failure"""
        with patch('aitbc_cli.config.get_config') as mock_get_config:
            mock_get_config.return_value = mock_config
            with patch('aitbc_cli.commands.deployment.ProductionDeployment') as mock_deployment_class:
                mock_deployment = Mock()
                mock_deployment.create_deployment = AsyncMock(return_value=None)
                mock_deployment_class.return_value = mock_deployment
                
                result = runner.invoke(cli, [
                    'deploy', 'create',
                    'test-app', 'production', 'us-west-1', 't3.medium',
                    '2', '5', '3', '8080', 'app.example.com'
                ])
                
                assert result.exit_code == 1
                assert 'failed to create deployment' in result.output.lower()
                
    def test_deploy_create_exception(self, runner, mock_config):
        """Test deployment configuration creation with exception"""
        with patch('aitbc_cli.config.get_config') as mock_get_config:
            mock_get_config.return_value = mock_config
            with patch('aitbc_cli.commands.deployment.ProductionDeployment') as mock_deployment_class:
                mock_deployment = Mock()
                mock_deployment.create_deployment = AsyncMock(side_effect=Exception("Network error"))
                mock_deployment_class.return_value = mock_deployment
                
                result = runner.invoke(cli, [
                    'deploy', 'create',
                    'test-app', 'production', 'us-west-1', 't3.medium',
                    '2', '5', '3', '8080', 'app.example.com'
                ])
                
                assert result.exit_code == 1
                assert 'error creating deployment' in result.output.lower()
                
    def test_deploy_start_success(self, runner, mock_config):
        """Test successful deployment start"""
        with patch('aitbc_cli.config.get_config') as mock_get_config:
            mock_get_config.return_value = mock_config
            with patch('aitbc_cli.commands.deployment.ProductionDeployment') as mock_deployment_class:
                mock_deployment = Mock()
                mock_deployment.deploy_application = AsyncMock(return_value=True)
                mock_deployment_class.return_value = mock_deployment
                
                result = runner.invoke(cli, [
                    'deploy', 'start',
                    'deploy_123'
                ])
                
                assert result.exit_code == 0
                assert 'deploy_123 started successfully' in result.output.lower()
                mock_deployment.deploy_application.assert_called_once_with('deploy_123')
                
    def test_deploy_start_failure(self, runner, mock_config):
        """Test deployment start failure"""
        with patch('aitbc_cli.config.get_config') as mock_get_config:
            mock_get_config.return_value = mock_config
            with patch('aitbc_cli.commands.deployment.ProductionDeployment') as mock_deployment_class:
                mock_deployment = Mock()
                mock_deployment.deploy_application = AsyncMock(return_value=False)
                mock_deployment_class.return_value = mock_deployment
                
                result = runner.invoke(cli, [
                    'deploy', 'start',
                    'deploy_123'
                ])
                
                assert result.exit_code == 1
                assert 'failed to start deployment' in result.output.lower()
                
    def test_deploy_scale_success(self, runner, mock_config):
        """Test successful deployment scaling"""
        with patch('aitbc_cli.config.get_config') as mock_get_config:
            mock_get_config.return_value = mock_config
            with patch('aitbc_cli.commands.deployment.ProductionDeployment') as mock_deployment_class:
                mock_deployment = Mock()
                mock_deployment.scale_deployment = AsyncMock(return_value=True)
                mock_deployment_class.return_value = mock_deployment
                
                result = runner.invoke(cli, [
                    'deploy', 'scale',
                    'deploy_123', '5',
                    '--reason', 'high_traffic'
                ])
                
                assert result.exit_code == 0
                assert 'deploy_123 scaled to 5 instances' in result.output.lower()
                mock_deployment.scale_deployment.assert_called_once_with('deploy_123', 5, 'high_traffic')
                
    def test_deploy_scale_failure(self, runner, mock_config):
        """Test deployment scaling failure"""
        with patch('aitbc_cli.config.get_config') as mock_get_config:
            mock_get_config.return_value = mock_config
            with patch('aitbc_cli.commands.deployment.ProductionDeployment') as mock_deployment_class:
                mock_deployment = Mock()
                mock_deployment.scale_deployment = AsyncMock(return_value=False)
                mock_deployment_class.return_value = mock_deployment
                
                result = runner.invoke(cli, [
                    'deploy', 'scale',
                    'deploy_123', '5'
                ])
                
                assert result.exit_code == 1
                assert 'failed to scale deployment' in result.output.lower()
                
    def test_deploy_status_success(self, runner, mock_config):
        """Test successful deployment status retrieval"""
        with patch('aitbc_cli.config.get_config') as mock_get_config:
            mock_get_config.return_value = mock_config
            with patch('aitbc_cli.commands.deployment.asyncio.run') as mock_run:
                mock_run.return_value = {
                    'deployment_id': 'deploy_123',
                    'status': 'running',
                    'instances': 3,
                    'healthy_instances': 3,
                    'cpu_usage': 45.2,
                    'memory_usage': 67.8,
                    'last_updated': '2023-01-01T12:00:00Z'
                }
                
                result = runner.invoke(cli, [
                    'deploy', 'status',
                    'deploy_123'
                ])
                
                assert result.exit_code == 0
                assert 'deploy_123' in result.output
                assert 'running' in result.output
                
    def test_deploy_status_not_found(self, runner, mock_config):
        """Test deployment status for non-existent deployment"""
        with patch('aitbc_cli.config.get_config') as mock_get_config:
            mock_get_config.return_value = mock_config
            with patch('aitbc_cli.commands.deployment.asyncio.run') as mock_run:
                mock_run.return_value = None
                
                result = runner.invoke(cli, [
                    'deploy', 'status',
                    'non_existent'
                ])
                
                assert result.exit_code == 1
                assert 'deployment not found' in result.output.lower()
                
    def test_deploy_overview_success(self, runner, mock_config):
        """Test successful deployment overview retrieval"""
        with patch('aitbc_cli.config.get_config') as mock_get_config:
            mock_get_config.return_value = mock_config
            with patch('aitbc_cli.commands.deployment.asyncio.run') as mock_run:
                mock_run.return_value = {
                    'total_deployments': 5,
                    'running_deployments': 3,
                    'failed_deployments': 0,
                    'total_instances': 15,
                    'active_regions': ['us-west-1', 'us-east-1'],
                    'cluster_health': 'healthy',
                    'last_updated': '2023-01-01T12:00:00Z'
                }
                
                result = runner.invoke(cli, [
                    'deploy', 'overview',
                    '--format', 'json'
                ])
                
                assert result.exit_code == 0
                assert '5' in result.output  # Total deployments
                assert 'healthy' in result.output.lower()
                
    def test_deploy_overview_table_format(self, runner, mock_config):
        """Test deployment overview in table format"""
        with patch('aitbc_cli.config.get_config') as mock_get_config:
            mock_get_config.return_value = mock_config
            with patch('aitbc_cli.commands.deployment.asyncio.run') as mock_run:
                mock_run.return_value = {
                    'total_deployments': 5,
                    'running_deployments': 3,
                    'failed_deployments': 0,
                    'total_instances': 15,
                    'active_regions': ['us-west-1', 'us-east-1'],
                    'cluster_health': 'healthy',
                    'last_updated': '2023-01-01T12:00:00Z'
                }
                
                result = runner.invoke(cli, [
                    'deploy', 'overview'
                ])
                
                assert result.exit_code == 0
                assert 'total_deployments' in result.output.lower()
                assert '5' in result.output
                
    def test_deploy_monitor_success(self, runner, mock_config):
        """Test successful deployment monitoring"""
        with patch('aitbc_cli.config.get_config') as mock_get_config:
            mock_get_config.return_value = mock_config
            with patch('aitbc_cli.commands.deployment.asyncio.run') as mock_run:
                mock_run.return_value = {
                    'deployment_id': 'deploy_123',
                    'status': 'running',
                    'instances': [
                        {'id': 'i-123', 'status': 'healthy', 'cpu': 45.2, 'memory': 67.8},
                        {'id': 'i-456', 'status': 'healthy', 'cpu': 38.1, 'memory': 52.3},
                        {'id': 'i-789', 'status': 'healthy', 'cpu': 52.7, 'memory': 71.4}
                    ],
                    'alerts': [],
                    'last_updated': '2023-01-01T12:00:00Z'
                }
                
                # Mock the monitoring loop to run only once
                with patch('time.sleep', side_effect=KeyboardInterrupt):
                    result = runner.invoke(cli, [
                        'deploy', 'monitor',
                        'deploy_123',
                        '--interval', '1'
                    ])
                
                assert result.exit_code == 0
                assert 'deploy_123' in result.output
                
    def test_deploy_auto_scale_success(self, runner, mock_config):
        """Test successful auto-scaling evaluation"""
        with patch('aitbc_cli.config.get_config') as mock_get_config:
            mock_get_config.return_value = mock_config
            with patch('aitbc_cli.commands.deployment.asyncio.run') as mock_run:
                mock_run.return_value = {
                    'deployment_id': 'deploy_123',
                    'evaluation': 'scale_up',
                    'current_instances': 3,
                    'recommended_instances': 5,
                    'reason': 'High CPU usage detected',
                    'metrics': {
                        'avg_cpu': 85.2,
                        'avg_memory': 72.1,
                        'request_rate': 1500
                    }
                }
                
                result = runner.invoke(cli, [
                    'deploy', 'auto-scale',
                    'deploy_123'
                ])
                
                assert result.exit_code == 0
                assert 'auto-scaling evaluation completed' in result.output.lower()
                assert 'scale_up' in result.output
                
    def test_deploy_auto_scale_no_action(self, runner, mock_config):
        """Test auto-scaling evaluation with no action needed"""
        with patch('aitbc_cli.config.get_config') as mock_get_config:
            mock_get_config.return_value = mock_config
            with patch('aitbc_cli.commands.deployment.asyncio.run') as mock_run:
                mock_run.return_value = {
                    'deployment_id': 'deploy_123',
                    'evaluation': 'no_action',
                    'current_instances': 3,
                    'recommended_instances': 3,
                    'reason': 'Metrics within normal range',
                    'metrics': {
                        'avg_cpu': 45.2,
                        'avg_memory': 52.1,
                        'request_rate': 500
                    }
                }
                
                result = runner.invoke(cli, [
                    'deploy', 'auto-scale',
                    'deploy_123'
                ])
                
                assert result.exit_code == 0
                assert 'no scaling action needed' in result.output.lower()
                
    def test_deploy_list_deployments_success(self, runner, mock_config):
        """Test successful deployment listing"""
        with patch('aitbc_cli.config.get_config') as mock_get_config:
            mock_get_config.return_value = mock_config
            with patch('aitbc_cli.commands.deployment.asyncio.run') as mock_run:
                mock_run.return_value = [
                    {
                        'deployment_id': 'deploy_123',
                        'name': 'web-app',
                        'environment': 'production',
                        'status': 'running',
                        'instances': 3,
                        'region': 'us-west-1'
                    },
                    {
                        'deployment_id': 'deploy_456',
                        'name': 'api-service',
                        'environment': 'staging',
                        'status': 'stopped',
                        'instances': 0,
                        'region': 'us-east-1'
                    }
                ]
                
                result = runner.invoke(cli, [
                    'deploy', 'list-deployments',
                    '--format', 'table'
                ])
                
                assert result.exit_code == 0
                assert 'deploy_123' in result.output
                assert 'web-app' in result.output
                assert 'deploy_456' in result.output
                assert 'api-service' in result.output
                
    def test_deploy_list_deployments_empty(self, runner, mock_config):
        """Test deployment listing with no deployments"""
        with patch('aitbc_cli.config.get_config') as mock_get_config:
            mock_get_config.return_value = mock_config
            with patch('aitbc_cli.commands.deployment.asyncio.run') as mock_run:
                mock_run.return_value = []
                
                result = runner.invoke(cli, [
                    'deploy', 'list-deployments'
                ])
                
                assert result.exit_code == 0
                assert 'no deployments found' in result.output.lower()
                
    def test_deploy_list_deployments_json_format(self, runner, mock_config):
        """Test deployment listing in JSON format"""
        with patch('aitbc_cli.config.get_config') as mock_get_config:
            mock_get_config.return_value = mock_config
            with patch('aitbc_cli.commands.deployment.asyncio.run') as mock_run:
                mock_run.return_value = [
                    {
                        'deployment_id': 'deploy_123',
                        'name': 'web-app',
                        'environment': 'production',
                        'status': 'running',
                        'instances': 3,
                        'region': 'us-west-1'
                    }
                ]
                
                result = runner.invoke(cli, [
                    'deploy', 'list-deployments',
                    '--format', 'json'
                ])
                
                assert result.exit_code == 0
                # Should be valid JSON
                json_data = json.loads(result.output)
                assert len(json_data) == 1
                assert json_data[0]['deployment_id'] == 'deploy_123'
