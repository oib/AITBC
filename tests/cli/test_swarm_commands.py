"""Tests for swarm intelligence commands"""

import pytest
import json
from unittest.mock import Mock, patch
from click.testing import CliRunner
from aitbc_cli.commands.swarm import swarm


class TestSwarmCommands:
    """Test swarm intelligence and collective optimization commands"""
    
    def setup_method(self):
        """Setup test environment"""
        self.runner = CliRunner()
        self.config = {
            'coordinator_url': 'http://test:8000',
            'api_key': 'test_key'
        }
    
    @patch('aitbc_cli.commands.swarm.httpx.Client')
    def test_swarm_join_success(self, mock_client):
        """Test successful swarm joining"""
        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            'swarm_id': 'swarm_123',
            'role': 'load-balancer',
            'capability': 'resource-optimization',
            'status': 'joined'
        }
        mock_client.return_value.__enter__.return_value.post.return_value = mock_response
        
        result = self.runner.invoke(swarm, [
            'join',
            '--role', 'load-balancer',
            '--capability', 'resource-optimization',
            '--priority', 'high'
        ], obj={'config': self.config, 'output_format': 'json'})
        
        assert result.exit_code == 0
        assert 'swarm_123' in result.output
    
    @patch('aitbc_cli.commands.swarm.httpx.Client')
    def test_swarm_coordinate_success(self, mock_client):
        """Test successful swarm coordination"""
        mock_response = Mock()
        mock_response.status_code = 202
        mock_response.json.return_value = {
            'task_id': 'task_123',
            'task': 'network-optimization',
            'collaborators': 10,
            'status': 'coordinating'
        }
        mock_client.return_value.__enter__.return_value.post.return_value = mock_response
        
        result = self.runner.invoke(swarm, [
            'coordinate',
            '--task', 'network-optimization',
            '--collaborators', '10',
            '--strategy', 'consensus'
        ], obj={'config': self.config, 'output_format': 'json'})
        
        assert result.exit_code == 0
        assert 'task_123' in result.output
    
    @patch('aitbc_cli.commands.swarm.httpx.Client')
    def test_swarm_list_success(self, mock_client):
        """Test successful swarm listing"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                'swarm_id': 'swarm_1',
                'role': 'load-balancer',
                'status': 'active',
                'members': 5
            },
            {
                'swarm_id': 'swarm_2',
                'role': 'resource-optimizer',
                'status': 'active',
                'members': 3
            }
        ]
        mock_client.return_value.__enter__.return_value.get.return_value = mock_response
        
        result = self.runner.invoke(swarm, [
            'list',
            '--status', 'active',
            '--limit', '10'
        ], obj={'config': self.config, 'output_format': 'json'})
        
        assert result.exit_code == 0
        assert 'swarm_1' in result.output
    
    @patch('aitbc_cli.commands.swarm.httpx.Client')
    def test_swarm_status_success(self, mock_client):
        """Test successful swarm task status retrieval"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'task_id': 'task_123',
            'status': 'running',
            'progress': 65,
            'active_collaborators': 8,
            'total_collaborators': 10
        }
        mock_client.return_value.__enter__.return_value.get.return_value = mock_response
        
        result = self.runner.invoke(swarm, [
            'status',
            'task_123'
        ], obj={'config': self.config, 'output_format': 'json'})
        
        assert result.exit_code == 0
        assert '65' in result.output
        assert '8' in result.output
    
    @patch('aitbc_cli.commands.swarm.httpx.Client')
    def test_swarm_consensus_success(self, mock_client):
        """Test successful swarm consensus achievement"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'task_id': 'task_123',
            'consensus_reached': True,
            'consensus_threshold': 0.7,
            'actual_consensus': 0.85
        }
        mock_client.return_value.__enter__.return_value.post.return_value = mock_response
        
        result = self.runner.invoke(swarm, [
            'consensus',
            'task_123',
            '--consensus-threshold', '0.7'
        ], obj={'config': self.config, 'output_format': 'json'})
        
        assert result.exit_code == 0
        assert 'True' in result.output
