"""Tests for multi-chain management CLI commands"""

import pytest
from click.testing import CliRunner
from unittest.mock import Mock, patch
from aitbc_cli.commands.chain import chain

@pytest.fixture
def runner():
    """Create CLI runner"""
    return CliRunner()

@pytest.fixture
def mock_chain_manager():
    """Mock ChainManager"""
    with patch('aitbc_cli.commands.chain.ChainManager') as mock:
        yield mock.return_value

@pytest.fixture
def mock_config():
    """Mock configuration loader"""
    with patch('aitbc_cli.commands.chain.load_multichain_config') as mock:
        yield mock

class TestChainAddCommand:
    """Test chain add command"""
    
    def test_add_chain_success(self, runner, mock_config, mock_chain_manager):
        """Test successful addition of a chain to a node"""
        # Setup mock
        mock_chain_manager.add_chain_to_node.return_value = True
        
        # Run command
        result = runner.invoke(chain, ['add', 'chain-123', 'node-456'])
        
        # Assertions
        assert result.exit_code == 0
        assert "added to node" in result.output
        mock_chain_manager.add_chain_to_node.assert_called_once_with('chain-123', 'node-456')

    def test_add_chain_failure(self, runner, mock_config, mock_chain_manager):
        """Test failure when adding a chain to a node"""
        # Setup mock
        mock_chain_manager.add_chain_to_node.return_value = False
        
        # Run command
        result = runner.invoke(chain, ['add', 'chain-123', 'node-456'])
        
        # Assertions
        assert result.exit_code != 0
        assert "Failed to add chain" in result.output
        mock_chain_manager.add_chain_to_node.assert_called_once_with('chain-123', 'node-456')

    def test_add_chain_exception(self, runner, mock_config, mock_chain_manager):
        """Test exception handling during chain addition"""
        # Setup mock
        mock_chain_manager.add_chain_to_node.side_effect = Exception("Connection error")
        
        # Run command
        result = runner.invoke(chain, ['add', 'chain-123', 'node-456'])
        
        # Assertions
        assert result.exit_code != 0
        assert "Error adding chain to node: Connection error" in result.output
        mock_chain_manager.add_chain_to_node.assert_called_once_with('chain-123', 'node-456')

    def test_add_chain_missing_args(self, runner):
        """Test command with missing arguments"""
        # Missing node_id
        result = runner.invoke(chain, ['add', 'chain-123'])
        assert result.exit_code != 0
        assert "Missing argument" in result.output

        # Missing chain_id and node_id
        result = runner.invoke(chain, ['add'])
        assert result.exit_code != 0
        assert "Missing argument" in result.output
