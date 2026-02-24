"""Tests for multi-modal processing commands"""

import pytest
import json
import base64
from unittest.mock import Mock, patch
from click.testing import CliRunner
from aitbc_cli.commands.multimodal import multimodal, convert, search, attention


class TestMultiModalCommands:
    """Test multi-modal agent processing commands"""
    
    def setup_method(self):
        """Setup test environment"""
        self.runner = CliRunner()
        self.config = {
            'coordinator_url': 'http://test:8000',
            'api_key': 'test_key'
        }
    
    @patch('aitbc_cli.commands.multimodal.httpx.Client')
    def test_multimodal_agent_create_success(self, mock_client):
        """Test successful multi-modal agent creation"""
        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            'id': 'multimodal_agent_123',
            'name': 'MultiModal Agent',
            'modalities': ['text', 'image']
        }
        mock_client.return_value.__enter__.return_value.post.return_value = mock_response
        
        result = self.runner.invoke(multimodal, [
            'agent',
            '--name', 'MultiModal Agent',
            '--modalities', 'text,image',
            '--gpu-acceleration'
        ], obj={'config': self.config, 'output_format': 'json'})
        
        assert result.exit_code == 0
        assert 'multimodal_agent_123' in result.output
    
    @patch('aitbc_cli.commands.multimodal.httpx.Client')
    @patch('aitbc_cli.commands.multimodal.Path.exists')
    def test_multimodal_process_success(self, mock_exists, mock_client):
        """Test successful multi-modal processing"""
        mock_exists.return_value = True
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'result': 'processed',
            'modalities_used': ['text', 'image']
        }
        mock_client.return_value.__enter__.return_value.post.return_value = mock_response
        
        with self.runner.isolated_filesystem():
            # Create a dummy image file
            with open('test_image.jpg', 'wb') as f:
                f.write(b'fake image data')
            
            result = self.runner.invoke(multimodal, [
                'process',
                'multimodal_agent_123',
                '--text', 'Test prompt',
                '--image', 'test_image.jpg',
                '--output-format', 'json'
            ], obj={'config': self.config, 'output_format': 'json'})
        
        assert result.exit_code == 0
        assert 'processed' in result.output
    
    @patch('aitbc_cli.commands.multimodal.httpx.Client')
    def test_multimodal_benchmark_success(self, mock_client):
        """Test successful multi-modal benchmarking"""
        mock_response = Mock()
        mock_response.status_code = 202
        mock_response.json.return_value = {
            'id': 'benchmark_123',
            'agent_id': 'multimodal_agent_123',
            'status': 'running'
        }
        mock_client.return_value.__enter__.return_value.post.return_value = mock_response
        
        result = self.runner.invoke(multimodal, [
            'benchmark',
            'multimodal_agent_123',
            '--dataset', 'coco_vqa',
            '--metrics', 'accuracy,latency',
            '--iterations', '50'
        ], obj={'config': self.config, 'output_format': 'json'})
        
        assert result.exit_code == 0
        assert 'benchmark_123' in result.output


class TestConvertCommands:
    """Test cross-modal conversion commands"""
    
    def setup_method(self):
        """Setup test environment"""
        self.runner = CliRunner()
        self.config = {
            'coordinator_url': 'http://test:8000',
            'api_key': 'test_key'
        }
    
    @patch('aitbc_cli.commands.multimodal.httpx.Client')
    @patch('aitbc_cli.commands.multimodal.Path.exists')
    def test_convert_success(self, mock_exists, mock_client):
        """Test successful modality conversion"""
        mock_exists.return_value = True
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'output_data': base64.b64encode(b'converted data').decode(),
            'output_format': 'text'
        }
        mock_client.return_value.__enter__.return_value.post.return_value = mock_response
        
        with self.runner.isolated_filesystem():
            # Create a dummy input file
            with open('input.jpg', 'wb') as f:
                f.write(b'fake image data')
            
            result = self.runner.invoke(convert, [
                'convert',
                '--input', 'input.jpg',
                '--output', 'text',
                '--model', 'blip'
            ], obj={'config': self.config, 'output_format': 'json'})
        
        assert result.exit_code == 0
        assert 'converted data' not in result.output  # Should be base64 encoded


class TestSearchCommands:
    """Test multi-modal search commands"""
    
    def setup_method(self):
        """Setup test environment"""
        self.runner = CliRunner()
        self.config = {
            'coordinator_url': 'http://test:8000',
            'api_key': 'test_key'
        }
    
    @patch('aitbc_cli.commands.multimodal.httpx.Client')
    def test_search_success(self, mock_client):
        """Test successful multi-modal search"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'results': [
                {'id': 'item_1', 'score': 0.95},
                {'id': 'item_2', 'score': 0.87}
            ],
            'query': 'red car'
        }
        mock_client.return_value.__enter__.return_value.post.return_value = mock_response
        
        result = self.runner.invoke(search, [
            'search',
            'red car',
            '--modalities', 'image,text',
            '--limit', '10',
            '--threshold', '0.8'
        ], obj={'config': self.config, 'output_format': 'json'})
        
        assert result.exit_code == 0
        assert 'item_1' in result.output
        assert '0.95' in result.output


class TestAttentionCommands:
    """Test cross-modal attention analysis commands"""
    
    def setup_method(self):
        """Setup test environment"""
        self.runner = CliRunner()
        self.config = {
            'coordinator_url': 'http://test:8000',
            'api_key': 'test_key'
        }
    
    @patch('aitbc_cli.commands.multimodal.httpx.Client')
    def test_attention_success(self, mock_client):
        """Test successful attention analysis"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'attention_patterns': {
                'text_to_image': [0.8, 0.2],
                'image_to_text': [0.3, 0.7]
            },
            'visualization': base64.b64encode(b'fake viz data').decode()
        }
        mock_client.return_value.__enter__.return_value.post.return_value = mock_response
        
        with self.runner.isolated_filesystem():
            with open('inputs.json', 'w') as f:
                json.dump({'text': 'test', 'image': 'test.jpg'}, f)
            
            result = self.runner.invoke(attention, [
                'attention',
                'multimodal_agent_123',
                '--inputs', 'inputs.json',
                '--visualize'
            ], obj={'config': self.config, 'output_format': 'json'})
        
        assert result.exit_code == 0
        assert 'attention_patterns' in result.output


class TestMultiModalUtilities:
    """Test multi-modal utility commands"""
    
    def setup_method(self):
        """Setup test environment"""
        self.runner = CliRunner()
        self.config = {
            'coordinator_url': 'http://test:8000',
            'api_key': 'test_key'
        }
    
    @patch('aitbc_cli.commands.multimodal.httpx.Client')
    def test_capabilities_success(self, mock_client):
        """Test successful capabilities listing"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'modalities': ['text', 'image', 'audio'],
            'models': ['blip', 'clip', 'whisper'],
            'gpu_acceleration': True
        }
        mock_client.return_value.__enter__.return_value.get.return_value = mock_response
        
        result = self.runner.invoke(multimodal, [
            'capabilities',
            'multimodal_agent_123'
        ], obj={'config': self.config, 'output_format': 'json'})
        
        assert result.exit_code == 0
        assert 'text' in result.output
        assert 'blip' in result.output
    
    @patch('aitbc_cli.commands.multimodal.httpx.Client')
    def test_test_modality_success(self, mock_client):
        """Test successful individual modality testing"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'modality': 'image',
            'test_result': 'passed',
            'performance': {'accuracy': 0.95, 'latency': 150}
        }
        mock_client.return_value.__enter__.return_value.post.return_value = mock_response
        
        result = self.runner.invoke(multimodal, [
            'test',
            'multimodal_agent_123',
            '--modality', 'image'
        ], obj={'config': self.config, 'output_format': 'json'})
        
        assert result.exit_code == 0
        assert 'passed' in result.output
        assert '0.95' in result.output
