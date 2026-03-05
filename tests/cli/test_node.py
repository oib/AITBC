"""Tests for node CLI commands"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from click.testing import CliRunner
from aitbc_cli.commands.node import node
from aitbc_cli.core.config import MultiChainConfig

@pytest.fixture
def runner():
    """Create CLI runner"""
    return CliRunner()

@pytest.fixture
def mock_config():
    """Mock configuration loader"""
    with patch('aitbc_cli.commands.node.load_multichain_config') as mock:
        config = MagicMock()
        config.nodes = {"node-1": MagicMock()}
        mock.return_value = config
        yield mock

class TestNodeCommands:
    
    @patch('aitbc_cli.core.config.save_multichain_config')
    @patch('aitbc_cli.commands.node.add_node_config')
    @patch('aitbc_cli.commands.node.get_default_node_config')
    def test_node_add_success(self, mock_get_default, mock_add, mock_save, runner, mock_config):
        """Test successful node addition"""
        # Setup mock
        mock_node_config = MagicMock()
        mock_get_default.return_value = mock_node_config
        
        mock_new_config = MagicMock()
        mock_add.return_value = mock_new_config
        
        # Run command
        result = runner.invoke(node, [
            'add', 'new-node', 'http://localhost:8080'
        ], obj={'output_format': 'json'})
        
        # Assertions
        assert result.exit_code == 0
        assert "added successfully" in result.output
        mock_save.assert_called_once_with(mock_new_config)

    def test_node_add_already_exists(self, runner, mock_config):
        """Test adding an existing node"""
        result = runner.invoke(node, [
            'add', 'node-1', 'http://localhost:8080'
        ], obj={'output_format': 'json'})
        
        assert result.exit_code != 0
        assert "already exists" in result.output

    @patch('aitbc_cli.commands.node.remove_node_config')
    @patch('aitbc_cli.core.config.save_multichain_config')
    def test_node_remove_success(self, mock_save, mock_remove, runner, mock_config):
        """Test successful node removal"""
        # Setup mock
        mock_new_config = MagicMock()
        mock_remove.return_value = mock_new_config
        
        result = runner.invoke(node, [
            'remove', 'node-1', '--force'
        ], obj={'output_format': 'json'})
        
        assert result.exit_code == 0
        assert "removed successfully" in result.output
        mock_save.assert_called_once_with(mock_new_config)

    def test_node_remove_not_found(self, runner, mock_config):
        """Test removing a non-existent node"""
        result = runner.invoke(node, [
            'remove', 'non-existent-node', '--force'
        ], obj={'output_format': 'json'})
        
        assert result.exit_code != 0
        assert "not found" in result.output

