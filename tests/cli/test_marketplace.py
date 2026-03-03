"""Tests for marketplace commands using AITBC CLI"""

import pytest
import json
from click.testing import CliRunner
from unittest.mock import Mock, patch
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


class TestMarketplaceCommands:
    """Test suite for marketplace commands"""
    
    def test_marketplace_help(self, runner):
        """Test marketplace help command"""
        result = runner.invoke(cli, ['marketplace', '--help'])
        assert result.exit_code == 0
        assert 'marketplace' in result.output.lower()
    
    def test_marketplace_list(self, runner, mock_config):
        """Test marketplace listing command"""
        with patch('aitbc_cli.config.get_config') as mock_get_config:
            mock_get_config.return_value = mock_config
            with patch('httpx.Client.get') as mock_get:
                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.json.return_value = {
                    'offers': [
                        {'id': 1, 'price': 0.1, 'gpu_type': 'RTX 3080'},
                        {'id': 2, 'price': 0.15, 'gpu_type': 'RTX 3090'}
                    ]
                }
                mock_get.return_value = mock_response
                
                result = runner.invoke(cli, ['marketplace', 'offers', 'list'])
                assert result.exit_code == 0
                assert 'offers' in result.output.lower() or 'gpu' in result.output.lower()
    
    def test_marketplace_gpu_pricing(self, runner, mock_config):
        """Test marketplace GPU pricing command"""
        with patch('aitbc_cli.config.get_config') as mock_get_config:
            mock_get_config.return_value = mock_config
            with patch('httpx.Client.get') as mock_get:
                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.json.return_value = {
                    'gpu_model': 'RTX 3080',
                    'avg_price': 0.12,
                    'price_range': {'min': 0.08, 'max': 0.15}
                }
                mock_get.return_value = mock_response
                
                result = runner.invoke(cli, ['marketplace', 'pricing', 'RTX 3080'])
                assert result.exit_code == 0
                assert 'price' in result.output.lower() or 'rtx' in result.output.lower()