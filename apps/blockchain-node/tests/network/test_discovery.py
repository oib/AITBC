"""
Tests for P2P Discovery Service
"""

import pytest
import asyncio
from unittest.mock import Mock, patch

from aitbc_chain.network.discovery import P2PDiscovery, PeerNode, NodeStatus

class TestP2PDiscovery:
    """Test cases for P2P discovery service"""
    
    def setup_method(self):
        """Setup test environment"""
        self.discovery = P2PDiscovery("test-node", "127.0.0.1", 8000)
        
        # Add bootstrap nodes
        self.discovery.add_bootstrap_node("127.0.0.1", 8001)
        self.discovery.add_bootstrap_node("127.0.0.1", 8002)
    
    def test_generate_node_id(self):
        """Test node ID generation"""
        address = "127.0.0.1"
        port = 8000
        public_key = "test_public_key"
        
        node_id = self.discovery.generate_node_id(address, port, public_key)
        
        assert isinstance(node_id, str)
        assert len(node_id) == 64  # SHA256 hex length
        
        # Test consistency
        node_id2 = self.discovery.generate_node_id(address, port, public_key)
        assert node_id == node_id2
    
    def test_add_bootstrap_node(self):
        """Test adding bootstrap node"""
        initial_count = len(self.discovery.bootstrap_nodes)
        
        self.discovery.add_bootstrap_node("127.0.0.1", 8003)
        
        assert len(self.discovery.bootstrap_nodes) == initial_count + 1
        assert ("127.0.0.1", 8003) in self.discovery.bootstrap_nodes
    
    def test_generate_node_id_consistency(self):
        """Test node ID generation consistency"""
        address = "192.168.1.1"
        port = 9000
        public_key = "test_key"
        
        node_id1 = self.discovery.generate_node_id(address, port, public_key)
        node_id2 = self.discovery.generate_node_id(address, port, public_key)
        
        assert node_id1 == node_id2
        
        # Different inputs should produce different IDs
        node_id3 = self.discovery.generate_node_id("192.168.1.2", port, public_key)
        assert node_id1 != node_id3
    
    def test_get_peer_count_empty(self):
        """Test getting peer count with no peers"""
        assert self.discovery.get_peer_count() == 0
    
    def test_get_peer_list_empty(self):
        """Test getting peer list with no peers"""
        assert self.discovery.get_peer_list() == []
    
    def test_update_peer_reputation_new_peer(self):
        """Test updating reputation for non-existent peer"""
        result = self.discovery.update_peer_reputation("nonexistent", 0.1)
        assert result is False
    
    def test_update_peer_reputation_bounds(self):
        """Test reputation bounds"""
        # Add a test peer
        peer = PeerNode(
            node_id="test_peer",
            address="127.0.0.1",
            port=8001,
            public_key="test_key",
            last_seen=0,
            status=NodeStatus.ONLINE,
            capabilities=["test"],
            reputation=0.5,
            connection_count=0
        )
        self.discovery.peers["test_peer"] = peer
        
        # Try to increase beyond 1.0
        result = self.discovery.update_peer_reputation("test_peer", 0.6)
        assert result is True
        assert self.discovery.peers["test_peer"].reputation == 1.0
        
        # Try to decrease below 0.0
        result = self.discovery.update_peer_reputation("test_peer", -1.5)
        assert result is True
        assert self.discovery.peers["test_peer"].reputation == 0.0

if __name__ == "__main__":
    pytest.main([__file__])
