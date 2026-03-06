"""Tests for agent commands using AITBC CLI"""

import pytest
import json
from unittest.mock import Mock, patch
from click.testing import CliRunner
from aitbc_cli.main import cli


class TestAgentCommands:
    """Test agent workflow and execution management commands"""
    
    @pytest.fixture
    def runner(self):
        """Create CLI runner"""
        return CliRunner()
    
    @pytest.fixture
    def mock_config(self):
        """Mock configuration for CLI"""
        config = {
            'coordinator_url': 'http://test:8000',
            'api_key': 'test_key',
            'output_format': 'json',
            'log_level': 'INFO'
        }
        return config
    
    @patch('aitbc_cli.commands.agent.httpx.Client')
    def test_agent_create_success(self, mock_client, runner, mock_config):
        """Test successful agent creation"""
        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            'id': 'agent_123',
            'name': 'Test Agent',
            'status': 'created'
        }
        mock_client.return_value.__enter__.return_value.post.return_value = mock_response
        
        result = runner.invoke(cli, [
            '--url', 'http://test:8000',
            '--api-key', 'test_key',
            '--output', 'json',
            'agent',
            'create',
            '--name', 'Test Agent',
            '--description', 'Test Description',
            '--verification', 'full'
        ])
        
        assert result.exit_code == 0
        assert 'agent_123' in result.output
    
    @patch('aitbc_cli.commands.agent.httpx.Client')
    def test_agent_list_success(self, mock_client, runner, mock_config):
        """Test successful agent listing"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {'id': 'agent_1', 'name': 'Agent 1'},
            {'id': 'agent_2', 'name': 'Agent 2'}
        ]
        mock_client.return_value.__enter__.return_value.get.return_value = mock_response
        
        result = runner.invoke(cli, [
            '--url', 'http://test:8000',
            '--api-key', 'test_key',
            '--output', 'json',
            'agent',
            'list'
        ])
        
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 2
        assert data[0]['id'] == 'agent_1'
    
    @patch('aitbc_cli.commands.agent.httpx.Client')
    def test_agent_execute_success(self, mock_client, runner, mock_config):
        """Test successful agent execution"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'execution_id': 'exec_123',
            'agent_id': 'agent_123',
            'status': 'running',
            'started_at': '2026-03-02T10:00:00Z'
        }
        mock_client.return_value.__enter__.return_value.post.return_value = mock_response
        
        result = runner.invoke(cli, [
            '--url', 'http://test:8000',
            '--api-key', 'test_key',
            '--output', 'json',
            'agent',
            'execute',
            '--agent-id', 'agent_123',
            '--workflow', 'test_workflow'
        ])
        
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data['execution_id'] == 'exec_123'
        assert data['status'] == 'running'
    
    @patch('aitbc_cli.commands.agent.httpx.Client')
    def test_agent_status_success(self, mock_client, runner, mock_config):
        """Test successful agent status check"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'agent_id': 'agent_123',
            'status': 'idle',
            'last_execution': '2026-03-02T09:00:00Z',
            'total_executions': 5,
            'success_rate': 0.8
        }
        mock_client.return_value.__enter__.return_value.get.return_value = mock_response
        
        result = runner.invoke(cli, [
            '--url', 'http://test:8000',
            '--api-key', 'test_key',
            '--output', 'json',
            'agent',
            'status',
            '--agent-id', 'agent_123'
        ])
        
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data['agent_id'] == 'agent_123'
        assert data['status'] == 'idle'
    
    @patch('aitbc_cli.commands.agent.httpx.Client')
    def test_agent_stop_success(self, mock_client, runner, mock_config):
        """Test successful agent stop"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'agent_id': 'agent_123',
            'status': 'stopped',
            'stopped_at': '2026-03-02T10:30:00Z'
        }
        mock_client.return_value.__enter__.return_value.post.return_value = mock_response
        
        result = runner.invoke(cli, [
            '--url', 'http://test:8000',
            '--api-key', 'test_key',
            '--output', 'json',
            'agent',
            'stop',
            '--agent-id', 'agent_123'
        ])
        
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data['status'] == 'stopped'
    
    def test_agent_create_missing_name(self, runner, mock_config):
        """Test agent creation with missing required name parameter"""
        result = runner.invoke(cli, [
            '--url', 'http://test:8000',
            '--api-key', 'test_key',
            '--output', 'json',
            'agent',
            'create'
        ])
        
        assert result.exit_code != 0
        assert 'Missing option' in result.output or 'name' in result.output
    
    @patch('aitbc_cli.commands.agent.httpx.Client')
    def test_agent_create_with_workflow_file(self, mock_client, runner, mock_config, tmp_path):
        """Test agent creation with workflow file"""
        # Create temporary workflow file
        workflow_file = tmp_path / "workflow.json"
        workflow_data = {
            "steps": [
                {"name": "step1", "action": "process", "params": {"input": "data"}},
                {"name": "step2", "action": "validate", "params": {"rules": ["rule1", "rule2"]}}
            ],
            "timeout": 1800
        }
        workflow_file.write_text(json.dumps(workflow_data))
        
        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            'id': 'agent_456',
            'name': 'Workflow Agent',
            'status': 'created'
        }
        mock_client.return_value.__enter__.return_value.post.return_value = mock_response
        
        result = runner.invoke(cli, [
            '--url', 'http://test:8000',
            '--api-key', 'test_key',
            '--output', 'json',
            'agent',
            'create',
            '--name', 'Workflow Agent',
            '--workflow-file', str(workflow_file)
        ])
        
        assert result.exit_code == 0
        assert 'agent_456' in result.output


class TestAgentCommandIntegration:
    """Integration tests for agent commands"""
    
    @pytest.fixture
    def runner(self):
        return CliRunner()
    
    def test_agent_help_command(self, runner):
        """Test agent help command"""
        result = runner.invoke(cli, ['agent', '--help'])
        assert result.exit_code == 0
        assert 'agent workflow' in result.output.lower()
        assert 'create' in result.output
        assert 'execute' in result.output
        assert 'list' in result.output
    
    def test_agent_create_help(self, runner):
        """Test agent create help command"""
        result = runner.invoke(cli, ['agent', 'create', '--help'])
        assert result.exit_code == 0
        assert '--name' in result.output
        assert '--description' in result.output
        assert '--verification' in result.output
