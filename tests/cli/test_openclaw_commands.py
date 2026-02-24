"""Tests for OpenClaw integration commands"""

import pytest
import json
from unittest.mock import Mock, patch
from click.testing import CliRunner
from aitbc_cli.commands.openclaw import openclaw, deploy, monitor, edge, routing, ecosystem


class TestDeployCommands:
    """Test agent deployment operations commands"""
    
    def setup_method(self):
        """Setup test environment"""
        self.runner = CliRunner()
        self.config = {
            'coordinator_url': 'http://test:8000',
            'api_key': 'test_key'
        }
    
    @patch('aitbc_cli.commands.openclaw.httpx.Client')
    def test_deploy_success(self, mock_client):
        """Test successful agent deployment"""
        mock_response = Mock()
        mock_response.status_code = 202
        mock_response.json.return_value = {
            'id': 'deployment_123',
            'agent_id': 'agent_123',
            'region': 'us-west',
            'status': 'deploying'
        }
        mock_client.return_value.__enter__.return_value.post.return_value = mock_response
        
        result = self.runner.invoke(deploy, [
            'deploy',
            'agent_123',
            '--region', 'us-west',
            '--instances', '3',
            '--instance-type', 'standard',
            '--auto-scale'
        ], obj={'config': self.config, 'output_format': 'json'})
        
        assert result.exit_code == 0
        assert 'deployment_123' in result.output
    
    @patch('aitbc_cli.commands.openclaw.httpx.Client')
    def test_scale_success(self, mock_client):
        """Test successful deployment scaling"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'deployment_id': 'deployment_123',
            'instances': 5,
            'auto_scale': True,
            'status': 'scaled'
        }
        mock_client.return_value.__enter__.return_value.post.return_value = mock_response
        
        result = self.runner.invoke(deploy, [
            'scale',
            'deployment_123',
            '--instances', '5',
            '--auto-scale',
            '--min-instances', '2',
            '--max-instances', '10'
        ], obj={'config': self.config, 'output_format': 'json'})
        
        assert result.exit_code == 0
        assert 'scaled' in result.output
    
    @patch('aitbc_cli.commands.openclaw.httpx.Client')
    def test_deploy_optimize_success(self, mock_client):
        """Test successful deployment optimization"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'deployment_id': 'deployment_123',
            'optimization_completed': True,
            'objective': 'cost',
            'improvements': {'cost_reduction': 15, 'performance_impact': 2}
        }
        mock_client.return_value.__enter__.return_value.post.return_value = mock_response
        
        result = self.runner.invoke(deploy, [
            'optimize',
            'deployment_123',
            '--objective', 'cost'
        ], obj={'config': self.config, 'output_format': 'json'})
        
        assert result.exit_code == 0
        assert 'optimization_completed' in result.output


class TestMonitorCommands:
    """Test OpenClaw monitoring operations commands"""
    
    def setup_method(self):
        """Setup test environment"""
        self.runner = CliRunner()
        self.config = {
            'coordinator_url': 'http://test:8000',
            'api_key': 'test_key'
        }
    
    @patch('aitbc_cli.commands.openclaw.httpx.Client')
    def test_monitor_success(self, mock_client):
        """Test successful deployment monitoring"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'deployment_id': 'deployment_123',
            'status': 'running',
            'instances': 3,
            'metrics': {
                'latency': 85,
                'cost': 0.45,
                'throughput': 1200
            }
        }
        mock_client.return_value.__enter__.return_value.get.return_value = mock_response
        
        result = self.runner.invoke(monitor, [
            'monitor',
            'deployment_123',
            '--metrics', 'latency,cost'
        ], obj={'config': self.config, 'output_format': 'json'})
        
        assert result.exit_code == 0
        assert '85' in result.output
        assert '0.45' in result.output
    
    @patch('aitbc_cli.commands.openclaw.httpx.Client')
    def test_status_success(self, mock_client):
        """Test successful deployment status retrieval"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'deployment_id': 'deployment_123',
            'status': 'healthy',
            'uptime': '99.9%',
            'last_health_check': '2026-02-24T10:30:00Z'
        }
        mock_client.return_value.__enter__.return_value.get.return_value = mock_response
        
        result = self.runner.invoke(monitor, [
            'status',
            'deployment_123'
        ], obj={'config': self.config, 'output_format': 'json'})
        
        assert result.exit_code == 0
        assert 'healthy' in result.output


class TestEdgeCommands:
    """Test edge computing operations commands"""
    
    def setup_method(self):
        """Setup test environment"""
        self.runner = CliRunner()
        self.config = {
            'coordinator_url': 'http://test:8000',
            'api_key': 'test_key'
        }
    
    @patch('aitbc_cli.commands.openclaw.httpx.Client')
    def test_edge_deploy_success(self, mock_client):
        """Test successful edge deployment"""
        mock_response = Mock()
        mock_response.status_code = 202
        mock_response.json.return_value = {
            'id': 'edge_deployment_123',
            'agent_id': 'agent_123',
            'locations': ['us-west', 'eu-central'],
            'strategy': 'latency',
            'status': 'deploying'
        }
        mock_client.return_value.__enter__.return_value.post.return_value = mock_response
        
        result = self.runner.invoke(edge, [
            'deploy',
            'agent_123',
            '--locations', 'us-west,eu-central',
            '--strategy', 'latency',
            '--replicas', '2'
        ], obj={'config': self.config, 'output_format': 'json'})
        
        assert result.exit_code == 0
        assert 'edge_deployment_123' in result.output
    
    @patch('aitbc_cli.commands.openclaw.httpx.Client')
    def test_edge_resources_success(self, mock_client):
        """Test successful edge resources listing"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'locations': {
                'us-west': {'cpu_usage': 45, 'memory_usage': 60, 'available': True},
                'eu-central': {'cpu_usage': 30, 'memory_usage': 40, 'available': True}
            },
            'total_capacity': {'cpu': 1000, 'memory': '2TB'}
        }
        mock_client.return_value.__enter__.return_value.get.return_value = mock_response
        
        result = self.runner.invoke(edge, [
            'resources',
            '--location', 'us-west'
        ], obj={'config': self.config, 'output_format': 'json'})
        
        assert result.exit_code == 0
        assert '45' in result.output
        assert '60' in result.output
    
    @patch('aitbc_cli.commands.openclaw.httpx.Client')
    def test_edge_optimize_success(self, mock_client):
        """Test successful edge optimization"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'deployment_id': 'edge_deployment_123',
            'optimization_completed': True,
            'latency_target_ms': 100,
            'actual_latency_ms': 85,
            'cost_budget': 1.0,
            'actual_cost': 0.85
        }
        mock_client.return_value.__enter__.return_value.post.return_value = mock_response
        
        result = self.runner.invoke(edge, [
            'optimize',
            'edge_deployment_123',
            '--latency-target', '100',
            '--cost-budget', '1.0'
        ], obj={'config': self.config, 'output_format': 'json'})
        
        assert result.exit_code == 0
        assert '85' in result.output
    
    @patch('aitbc_cli.commands.openclaw.httpx.Client')
    def test_edge_compliance_success(self, mock_client):
        """Test successful edge compliance check"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'deployment_id': 'edge_deployment_123',
            'compliance_status': 'compliant',
            'standards': {
                'gdpr': {'compliant': True, 'score': 95},
                'hipaa': {'compliant': True, 'score': 92}
            },
            'last_check': '2026-02-24T10:00:00Z'
        }
        mock_client.return_value.__enter__.return_value.get.return_value = mock_response
        
        result = self.runner.invoke(edge, [
            'compliance',
            'edge_deployment_123',
            '--standards', 'gdpr,hipaa'
        ], obj={'config': self.config, 'output_format': 'json'})
        
        assert result.exit_code == 0
        assert 'compliant' in result.output
        assert '95' in result.output


class TestRoutingCommands:
    """Test agent skill routing commands"""
    
    def setup_method(self):
        """Setup test environment"""
        self.runner = CliRunner()
        self.config = {
            'coordinator_url': 'http://test:8000',
            'api_key': 'test_key'
        }
    
    @patch('aitbc_cli.commands.openclaw.httpx.Client')
    def test_routing_optimize_success(self, mock_client):
        """Test successful routing optimization"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'deployment_id': 'deployment_123',
            'routing_optimized': True,
            'algorithm': 'skill-based',
            'improvements': {
                'response_time': -20,
                'skill_match_accuracy': 15
            }
        }
        mock_client.return_value.__enter__.return_value.post.return_value = mock_response
        
        result = self.runner.invoke(routing, [
            'optimize',
            'deployment_123',
            '--algorithm', 'skill-based',
            '--weights', '0.5,0.3,0.2'
        ], obj={'config': self.config, 'output_format': 'json'})
        
        assert result.exit_code == 0
        assert 'routing_optimized' in result.output
    
    @patch('aitbc_cli.commands.openclaw.httpx.Client')
    def test_routing_status_success(self, mock_client):
        """Test successful routing status retrieval"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'deployment_id': 'deployment_123',
            'routing_algorithm': 'load-balanced',
            'active_routes': 15,
            'average_response_time': 120,
            'skill_match_rate': 0.87
        }
        mock_client.return_value.__enter__.return_value.get.return_value = mock_response
        
        result = self.runner.invoke(routing, [
            'status',
            'deployment_123'
        ], obj={'config': self.config, 'output_format': 'json'})
        
        assert result.exit_code == 0
        assert '120' in result.output
        assert '0.87' in result.output


class TestEcosystemCommands:
    """Test OpenClaw ecosystem development commands"""
    
    def setup_method(self):
        """Setup test environment"""
        self.runner = CliRunner()
        self.config = {
            'coordinator_url': 'http://test:8000',
            'api_key': 'test_key'
        }
    
    @patch('aitbc_cli.commands.openclaw.httpx.Client')
    def test_ecosystem_create_success(self, mock_client):
        """Test successful ecosystem solution creation"""
        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            'id': 'solution_123',
            'name': 'Test Solution',
            'type': 'agent',
            'status': 'created'
        }
        mock_client.return_value.__enter__.return_value.post.return_value = mock_response
        
        with self.runner.isolated_filesystem():
            with open('package.zip', 'wb') as f:
                f.write(b'fake package data')
            
            result = self.runner.invoke(ecosystem, [
                'create',
                '--name', 'Test Solution',
                '--type', 'agent',
                '--description', 'Test description',
                '--package', 'package.zip'
            ], obj={'config': self.config, 'output_format': 'json'})
        
        assert result.exit_code == 0
        assert 'solution_123' in result.output
    
    @patch('aitbc_cli.commands.openclaw.httpx.Client')
    def test_ecosystem_list_success(self, mock_client):
        """Test successful ecosystem solution listing"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {'id': 'solution_1', 'name': 'Solution 1', 'type': 'agent'},
            {'id': 'solution_2', 'name': 'Solution 2', 'type': 'workflow'}
        ]
        mock_client.return_value.__enter__.return_value.get.return_value = mock_response
        
        result = self.runner.invoke(ecosystem, [
            'list',
            '--type', 'agent',
            '--limit', '10'
        ], obj={'config': self.config, 'output_format': 'json'})
        
        assert result.exit_code == 0
        assert 'solution_1' in result.output
    
    @patch('aitbc_cli.commands.openclaw.httpx.Client')
    def test_ecosystem_install_success(self, mock_client):
        """Test successful ecosystem solution installation"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'solution_id': 'solution_123',
            'installation_completed': True,
            'status': 'installed',
            'installation_path': '/opt/openclaw/solutions/solution_123'
        }
        mock_client.return_value.__enter__.return_value.post.return_value = mock_response
        
        result = self.runner.invoke(ecosystem, [
            'install',
            'solution_123'
        ], obj={'config': self.config, 'output_format': 'json'})
        
        assert result.exit_code == 0
        assert 'installed' in result.output


class TestOpenClawUtilities:
    """Test OpenClaw utility commands"""
    
    def setup_method(self):
        """Setup test environment"""
        self.runner = CliRunner()
        self.config = {
            'coordinator_url': 'http://test:8000',
            'api_key': 'test_key'
        }
    
    @patch('aitbc_cli.commands.openclaw.httpx.Client')
    def test_terminate_success(self, mock_client):
        """Test successful deployment termination"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'deployment_id': 'deployment_123',
            'terminated': True,
            'status': 'terminated',
            'termination_time': '2026-02-24T11:00:00Z'
        }
        mock_client.return_value.__enter__.return_value.delete.return_value = mock_response
        
        result = self.runner.invoke(openclaw, [
            'terminate',
            'deployment_123'
        ], obj={'config': self.config, 'output_format': 'json'})
        
        assert result.exit_code == 0
        assert 'terminated' in result.output
