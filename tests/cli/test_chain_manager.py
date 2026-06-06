"""
Chain Manager Tests
Tests for multi-chain manager
"""

import sys
from pathlib import Path
from unittest.mock import patch, Mock

# Add CLI path for imports
cli_path = Path("/opt/aitbc/cli")
if str(cli_path) not in sys.path:
    sys.path.insert(0, str(cli_path))

import pytest


class TestChainAlreadyExistsError:
    """Test ChainAlreadyExistsError exception"""

    def test_chain_already_exists_error(self):
        """Test ChainAlreadyExistsError can be raised"""
        from aitbc_cli.core.chain_manager import ChainAlreadyExistsError
        
        with pytest.raises(ChainAlreadyExistsError):
            raise ChainAlreadyExistsError("Chain already exists")


class TestChainNotFoundError:
    """Test ChainNotFoundError exception"""

    def test_chain_not_found_error(self):
        """Test ChainNotFoundError can be raised"""
        from aitbc_cli.core.chain_manager import ChainNotFoundError
        
        with pytest.raises(ChainNotFoundError):
            raise ChainNotFoundError("Chain not found")


class TestNodeNotAvailableError:
    """Test NodeNotAvailableError exception"""

    def test_node_not_available_error(self):
        """Test NodeNotAvailableError can be raised"""
        from aitbc_cli.core.chain_manager import NodeNotAvailableError
        
        with pytest.raises(NodeNotAvailableError):
            raise NodeNotAvailableError("Node not available")


class TestChainManager:
    """Test ChainManager class"""

    @patch('aitbc_cli.core.chain_manager.NodeClient')
    def test_init(self, mock_node_client):
        """Test ChainManager initialization"""
        from aitbc_cli.core.chain_manager import ChainManager, MultiChainConfig
        
        config = Mock(spec=MultiChainConfig)
        manager = ChainManager(config)
        
        assert manager.config == config
        assert manager._chain_cache == {}
        assert manager._node_clients == {}

    @patch('aitbc_cli.core.chain_manager.NodeClient')
    def test_chain_cache_initialization(self, mock_node_client):
        """Test chain cache initialization"""
        from aitbc_cli.core.chain_manager import ChainManager, MultiChainConfig
        
        config = Mock(spec=MultiChainConfig)
        manager = ChainManager(config)
        
        assert isinstance(manager._chain_cache, dict)
        assert len(manager._chain_cache) == 0

    @patch('aitbc_cli.core.chain_manager.NodeClient')
    def test_node_clients_initialization(self, mock_node_client):
        """Test node clients initialization"""
        from aitbc_cli.core.chain_manager import ChainManager, MultiChainConfig
        
        config = Mock(spec=MultiChainConfig)
        manager = ChainManager(config)
        
        assert isinstance(manager._node_clients, dict)
        assert len(manager._node_clients) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
