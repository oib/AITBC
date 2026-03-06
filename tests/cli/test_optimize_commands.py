"""Tests for autonomous optimization commands"""

import pytest
import json
from unittest.mock import Mock, patch
from click.testing import CliRunner
from aitbc_cli.commands.optimize import optimize, self_opt, predict, tune


class TestSelfOptCommands:
    """Test self-optimization operations commands"""
    
    def setup_method(self):
        """Setup test environment"""
        self.runner = CliRunner()
        self.config = {
            'coordinator_url': 'http://test:8000',
            'api_key': 'test_key'
        }
    
    @patch('aitbc_cli.commands.optimize.httpx.Client')
    def test_self_opt_enable_success(self, mock_client):
        """Test successful self-optimization enable"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'agent_id': 'agent_123',
            'optimization_enabled': True,
            'mode': 'auto-tune',
            'scope': 'full'
        }
        mock_client.return_value.__enter__.return_value.post.return_value = mock_response
        
        result = self.runner.invoke(self_opt, [
            'enable',
            'agent_123',
            '--mode', 'auto-tune',
            '--scope', 'full',
            '--aggressiveness', 'moderate'
        ], obj={'config': self.config, 'output_format': 'json'})
        
        assert result.exit_code == 0
        assert 'optimization_enabled' in result.output
    
    @patch('aitbc_cli.commands.optimize.httpx.Client')
    def test_self_opt_status_success(self, mock_client):
        """Test successful optimization status retrieval"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'agent_id': 'agent_123',
            'status': 'optimizing',
            'progress': 65,
            'metrics': {
                'performance': 0.85,
                'cost': 0.45
            }
        }
        mock_client.return_value.__enter__.return_value.get.return_value = mock_response
        
        result = self.runner.invoke(self_opt, [
            'status',
            'agent_123',
            '--metrics', 'performance,cost'
        ], obj={'config': self.config, 'output_format': 'json'})
        
        assert result.exit_code == 0
        assert '65' in result.output
        assert '0.85' in result.output
    
    @patch('aitbc_cli.commands.optimize.httpx.Client')
    def test_self_opt_objectives_success(self, mock_client):
        """Test successful optimization objectives setting"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'agent_id': 'agent_123',
            'objectives_set': True,
            'targets': {
                'latency': '100ms',
                'cost': '0.5'
            }
        }
        mock_client.return_value.__enter__.return_value.post.return_value = mock_response
        
        result = self.runner.invoke(self_opt, [
            'objectives',
            'agent_123',
            '--targets', 'latency:100ms,cost:0.5',
            '--priority', 'balanced'
        ], obj={'config': self.config, 'output_format': 'json'})
        
        assert result.exit_code == 0
        assert 'objectives_set' in result.output
    
    @patch('aitbc_cli.commands.optimize.httpx.Client')
    def test_self_opt_recommendations_success(self, mock_client):
        """Test successful recommendations retrieval"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'recommendations': [
                {
                    'id': 'rec_1',
                    'priority': 'high',
                    'category': 'performance',
                    'description': 'Increase GPU memory allocation'
                },
                {
                    'id': 'rec_2',
                    'priority': 'medium',
                    'category': 'cost',
                    'description': 'Optimize batch size'
                }
            ]
        }
        mock_client.return_value.__enter__.return_value.get.return_value = mock_response
        
        result = self.runner.invoke(self_opt, [
            'recommendations',
            'agent_123',
            '--priority', 'high',
            '--category', 'performance'
        ], obj={'config': self.config, 'output_format': 'json'})
        
        assert result.exit_code == 0
        assert 'rec_1' in result.output
        assert 'high' in result.output


class TestPredictCommands:
    """Test predictive operations commands"""
    
    def setup_method(self):
        """Setup test environment"""
        self.runner = CliRunner()
        self.config = {
            'coordinator_url': 'http://test:8000',
            'api_key': 'test_key'
        }
    
    @patch('aitbc_cli.commands.optimize.httpx.Client')
    def test_predict_resources_success(self, mock_client):
        """Test successful resource prediction"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'agent_id': 'agent_123',
            'predictions': {
                'gpu': {'predicted': 2, 'confidence': 0.92},
                'memory': {'predicted': '16GB', 'confidence': 0.88}
            },
            'horizon_hours': 24
        }
        mock_client.return_value.__enter__.return_value.post.return_value = mock_response
        
        result = self.runner.invoke(predict, [
            'predict',
            'agent_123',
            '--horizon', '24',
            '--resources', 'gpu,memory',
            '--confidence', '0.8'
        ], obj={'config': self.config, 'output_format': 'json'})
        
        assert result.exit_code == 0
        assert '2' in result.output
        assert '0.92' in result.output
    
    @patch('aitbc_cli.commands.optimize.httpx.Client')
    def test_autoscale_success(self, mock_client):
        """Test successful auto-scaling configuration"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'agent_id': 'agent_123',
            'autoscale_configured': True,
            'policy': 'cost-efficiency',
            'min_instances': 1,
            'max_instances': 10
        }
        mock_client.return_value.__enter__.return_value.post.return_value = mock_response
        
        result = self.runner.invoke(predict, [
            'autoscale',
            'agent_123',
            '--policy', 'cost-efficiency',
            '--min-instances', '1',
            '--max-instances', '10'
        ], obj={'config': self.config, 'output_format': 'json'})
        
        assert result.exit_code == 0
        assert 'autoscale_configured' in result.output
    
    @patch('aitbc_cli.commands.optimize.httpx.Client')
    def test_forecast_success(self, mock_client):
        """Test successful performance forecasting"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'agent_id': 'agent_123',
            'metric': 'throughput',
            'forecast': [
                {'timestamp': '2026-02-25T00:00:00Z', 'value': 1000, 'confidence': 0.95},
                {'timestamp': '2026-02-26T00:00:00Z', 'value': 1050, 'confidence': 0.92}
            ],
            'period_days': 7
        }
        mock_client.return_value.__enter__.return_value.post.return_value = mock_response
        
        result = self.runner.invoke(predict, [
            'forecast',
            'agent_123',
            '--metric', 'throughput',
            '--period', '7',
            '--granularity', 'day'
        ], obj={'config': self.config, 'output_format': 'json'})
        
        assert result.exit_code == 0
        assert '1000' in result.output
        assert '0.95' in result.output


class TestTuneCommands:
    """Test auto-tuning operations commands"""
    
    def setup_method(self):
        """Setup test environment"""
        self.runner = CliRunner()
        self.config = {
            'coordinator_url': 'http://test:8000',
            'api_key': 'test_key'
        }
    
    @patch('aitbc_cli.commands.optimize.httpx.Client')
    def test_tune_auto_success(self, mock_client):
        """Test successful auto-tuning start"""
        mock_response = Mock()
        mock_response.status_code = 202
        mock_response.json.return_value = {
            'id': 'tuning_123',
            'agent_id': 'agent_123',
            'status': 'started',
            'iterations': 100
        }
        mock_client.return_value.__enter__.return_value.post.return_value = mock_response
        
        result = self.runner.invoke(tune, [
            'auto',
            'agent_123',
            '--parameters', 'learning_rate,batch_size',
            '--objective', 'performance',
            '--iterations', '100'
        ], obj={'config': self.config, 'output_format': 'json'})
        
        assert result.exit_code == 0
        assert 'tuning_123' in result.output
    
    @patch('aitbc_cli.commands.optimize.httpx.Client')
    def test_tune_status_success(self, mock_client):
        """Test successful tuning status retrieval"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'id': 'tuning_123',
            'status': 'running',
            'progress': 45,
            'current_iteration': 45,
            'total_iterations': 100,
            'best_score': 0.87
        }
        mock_client.return_value.__enter__.return_value.get.return_value = mock_response
        
        result = self.runner.invoke(tune, [
            'status',
            'tuning_123'
        ], obj={'config': self.config, 'output_format': 'json'})
        
        assert result.exit_code == 0
        assert '45' in result.output
        assert '0.87' in result.output
    
    @patch('aitbc_cli.commands.optimize.httpx.Client')
    def test_tune_results_success(self, mock_client):
        """Test successful tuning results retrieval"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'tuning_id': 'tuning_123',
            'status': 'completed',
            'best_parameters': {
                'learning_rate': 0.001,
                'batch_size': 32
            },
            'best_score': 0.92,
            'iterations_completed': 100
        }
        mock_client.return_value.__enter__.return_value.get.return_value = mock_response
        
        result = self.runner.invoke(tune, [
            'results',
            'tuning_123'
        ], obj={'config': self.config, 'output_format': 'json'})
        
        assert result.exit_code == 0
        assert '0.92' in result.output
        assert '0.001' in result.output


class TestOptimizeUtilities:
    """Test optimization utility commands"""
    
    def setup_method(self):
        """Setup test environment"""
        self.runner = CliRunner()
        self.config = {
            'coordinator_url': 'http://test:8000',
            'api_key': 'test_key'
        }
    
    @patch('aitbc_cli.commands.optimize.httpx.Client')
    def test_optimize_disable_success(self, mock_client):
        """Test successful optimization disable"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'agent_id': 'agent_123',
            'optimization_disabled': True,
            'status': 'disabled'
        }
        mock_client.return_value.__enter__.return_value.post.return_value = mock_response
        
        result = self.runner.invoke(optimize, [
            'disable',
            'agent_123'
        ], obj={'config': self.config, 'output_format': 'json'})
        
        assert result.exit_code == 0
        assert 'optimization_disabled' in result.output
    
    @patch('aitbc_cli.commands.optimize.httpx.Client')
    def test_self_opt_apply_success(self, mock_client):
        """Test successful recommendation application"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'agent_id': 'agent_123',
            'recommendation_id': 'rec_1',
            'applied': True,
            'status': 'applied'
        }
        mock_client.return_value.__enter__.return_value.post.return_value = mock_response
        
        result = self.runner.invoke(self_opt, [
            'apply',
            'agent_123',
            '--recommendation-id', 'rec_1',
            '--confirm'
        ], obj={'config': self.config, 'output_format': 'json'})
        
        assert result.exit_code == 0
        assert 'applied' in result.output
