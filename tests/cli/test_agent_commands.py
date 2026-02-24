"""Tests for agent commands"""

import pytest
import json
from unittest.mock import Mock, patch
from click.testing import CliRunner
from aitbc_cli.commands.agent import agent, network, learning


class TestAgentCommands:
    """Test agent workflow and execution management commands"""
    
    def setup_method(self):
        """Setup test environment"""
        self.runner = CliRunner()
        self.config = {
            'coordinator_url': 'http://test:8000',
            'api_key': 'test_key'
        }
    
    @patch('aitbc_cli.commands.agent.httpx.Client')
    def test_agent_create_success(self, mock_client):
        """Test successful agent creation"""
        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            'id': 'agent_123',
            'name': 'Test Agent',
            'status': 'created'
        }
        mock_client.return_value.__enter__.return_value.post.return_value = mock_response
        
        result = self.runner.invoke(agent, [
            'create',
            '--name', 'Test Agent',
            '--description', 'Test Description',
            '--verification', 'full'
        ], obj={'config': self.config, 'output_format': 'json'})
        
        assert result.exit_code == 0
        assert 'agent_123' in result.output
    
    @patch('aitbc_cli.commands.agent.httpx.Client')
    def test_agent_list_success(self, mock_client):
        """Test successful agent listing"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {'id': 'agent_1', 'name': 'Agent 1'},
            {'id': 'agent_2', 'name': 'Agent 2'}
        ]
        mock_client.return_value.__enter__.return_value.get.return_value = mock_response
        
        result = self.runner.invoke(agent, [
            'list',
            '--type', 'multimodal',
            '--limit', '10'
        ], obj={'config': self.config, 'output_format': 'json'})
        
        assert result.exit_code == 0
        assert 'agent_1' in result.output
    
    @patch('aitbc_cli.commands.agent.httpx.Client')
    def test_agent_execute_success(self, mock_client):
        """Test successful agent execution"""
        mock_response = Mock()
        mock_response.status_code = 202
        mock_response.json.return_value = {
            'id': 'exec_123',
            'agent_id': 'agent_123',
            'status': 'running'
        }
        mock_client.return_value.__enter__.return_value.post.return_value = mock_response
        
        with self.runner.isolated_filesystem():
            with open('inputs.json', 'w') as f:
                json.dump({'prompt': 'test prompt'}, f)
            
            result = self.runner.invoke(agent, [
                'execute',
                'agent_123',
                '--inputs', 'inputs.json',
                '--verification', 'basic'
            ], obj={'config': self.config, 'output_format': 'json'})
        
        assert result.exit_code == 0
        assert 'exec_123' in result.output


class TestNetworkCommands:
    """Test multi-agent collaborative network commands"""
    
    def setup_method(self):
        """Setup test environment"""
        self.runner = CliRunner()
        self.config = {
            'coordinator_url': 'http://test:8000',
            'api_key': 'test_key'
        }
    
    @patch('aitbc_cli.commands.agent.httpx.Client')
    def test_network_create_success(self, mock_client):
        """Test successful network creation"""
        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            'id': 'network_123',
            'name': 'Test Network',
            'agents': ['agent_1', 'agent_2']
        }
        mock_client.return_value.__enter__.return_value.post.return_value = mock_response
        
        result = self.runner.invoke(network, [
            'create',
            '--name', 'Test Network',
            '--agents', 'agent_1,agent_2',
            '--coordination', 'decentralized'
        ], obj={'config': self.config, 'output_format': 'json'})
        
        assert result.exit_code == 0
        assert 'network_123' in result.output
    
    @patch('aitbc_cli.commands.agent.httpx.Client')
    def test_network_execute_success(self, mock_client):
        """Test successful network task execution"""
        mock_response = Mock()
        mock_response.status_code = 202
        mock_response.json.return_value = {
            'id': 'net_exec_123',
            'network_id': 'network_123',
            'status': 'running'
        }
        mock_client.return_value.__enter__.return_value.post.return_value = mock_response
        
        with self.runner.isolated_filesystem():
            with open('task.json', 'w') as f:
                json.dump({'task': 'test task'}, f)
            
            result = self.runner.invoke(network, [
                'execute',
                'network_123',
                '--task', 'task.json',
                '--priority', 'high'
            ], obj={'config': self.config, 'output_format': 'json'})
        
        assert result.exit_code == 0
        assert 'net_exec_123' in result.output


class TestLearningCommands:
    """Test agent adaptive learning commands"""
    
    def setup_method(self):
        """Setup test environment"""
        self.runner = CliRunner()
        self.config = {
            'coordinator_url': 'http://test:8000',
            'api_key': 'test_key'
        }
    
    @patch('aitbc_cli.commands.agent.httpx.Client')
    def test_learning_enable_success(self, mock_client):
        """Test successful learning enable"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'agent_id': 'agent_123',
            'learning_enabled': True,
            'mode': 'reinforcement'
        }
        mock_client.return_value.__enter__.return_value.post.return_value = mock_response
        
        result = self.runner.invoke(learning, [
            'enable',
            'agent_123',
            '--mode', 'reinforcement',
            '--learning-rate', '0.001'
        ], obj={'config': self.config, 'output_format': 'json'})
        
        assert result.exit_code == 0
        assert 'learning_enabled' in result.output
    
    @patch('aitbc_cli.commands.agent.httpx.Client')
    def test_learning_train_success(self, mock_client):
        """Test successful learning training"""
        mock_response = Mock()
        mock_response.status_code = 202
        mock_response.json.return_value = {
            'id': 'training_123',
            'agent_id': 'agent_123',
            'status': 'training'
        }
        mock_client.return_value.__enter__.return_value.post.return_value = mock_response
        
        with self.runner.isolated_filesystem():
            with open('feedback.json', 'w') as f:
                json.dump({'feedback': 'positive'}, f)
            
            result = self.runner.invoke(learning, [
                'train',
                'agent_123',
                '--feedback', 'feedback.json',
                '--epochs', '10'
            ], obj={'config': self.config, 'output_format': 'json'})
        
        assert result.exit_code == 0
        assert 'training_123' in result.output
