"""
Test for multi-chain node integration
"""

import asyncio
import pytest
from aitbc_cli.core.config import MultiChainConfig, NodeConfig
from aitbc_cli.core.node_client import NodeClient
from aitbc_cli.core.chain_manager import ChainManager

def test_node_client_creation():
    """Test node client creation and basic functionality"""
    node_config = NodeConfig(
        id="test-node",
        endpoint="http://localhost:8545",
        timeout=30,
        retry_count=3,
        max_connections=10
    )
    
    # Test client creation
    client = NodeClient(node_config)
    assert client.config.id == "test-node"
    assert client.config.endpoint == "http://localhost:8545"

async def test_node_client_mock_operations():
    """Test node client operations with mock data"""
    node_config = NodeConfig(
        id="test-node",
        endpoint="http://localhost:8545",
        timeout=30,
        retry_count=3,
        max_connections=10
    )
    
    async with NodeClient(node_config) as client:
        # Test node info
        node_info = await client.get_node_info()
        assert node_info["node_id"] == "test-node"
        assert "status" in node_info
        assert "uptime_days" in node_info
        
        # Test hosted chains
        chains = await client.get_hosted_chains()
        assert isinstance(chains, list)
        if chains:  # If mock data is available
            assert hasattr(chains[0], 'id')
            assert hasattr(chains[0], 'type')
        
        # Test chain stats
        stats = await client.get_chain_stats("test-chain")
        assert "chain_id" in stats
        assert "block_height" in stats

def test_chain_manager_with_node_client():
    """Test chain manager integration with node client"""
    config = MultiChainConfig()
    
    # Add a test node
    test_node = NodeConfig(
        id="test-node",
        endpoint="http://localhost:8545",
        timeout=30,
        retry_count=3,
        max_connections=10
    )
    config.nodes["test-node"] = test_node
    
    chain_manager = ChainManager(config)
    
    # Test that chain manager can use the node client
    assert "test-node" in chain_manager.config.nodes
    assert chain_manager.config.nodes["test-node"].endpoint == "http://localhost:8545"

async def test_chain_operations_with_node():
    """Test chain operations using node client"""
    config = MultiChainConfig()
    
    # Add a test node
    test_node = NodeConfig(
        id="test-node",
        endpoint="http://localhost:8545",
        timeout=30,
        retry_count=3,
        max_connections=10
    )
    config.nodes["test-node"] = test_node
    
    chain_manager = ChainManager(config)
    
    # Test listing chains (should work with mock data)
    chains = await chain_manager.list_chains()
    assert isinstance(chains, list)
    
    # Test node-specific operations
    node_chains = await chain_manager._get_node_chains("test-node")
    assert isinstance(node_chains, list)

def test_backup_restore_operations():
    """Test backup and restore operations"""
    config = MultiChainConfig()
    
    # Add a test node
    test_node = NodeConfig(
        id="test-node",
        endpoint="http://localhost:8545",
        timeout=30,
        retry_count=3,
        max_connections=10
    )
    config.nodes["test-node"] = test_node
    
    chain_manager = ChainManager(config)
    
    # These would normally be async, but we're testing the structure
    assert hasattr(chain_manager, '_execute_backup')
    assert hasattr(chain_manager, '_execute_restore')
    assert hasattr(chain_manager, '_get_chain_hosting_nodes')

if __name__ == "__main__":
    # Run basic tests
    test_node_client_creation()
    
    # Run async tests
    asyncio.run(test_node_client_mock_operations())
    asyncio.run(test_chain_operations_with_node())
    
    # Run sync tests
    test_chain_manager_with_node_client()
    test_backup_restore_operations()
    
    print("✅ All node integration tests passed!")
