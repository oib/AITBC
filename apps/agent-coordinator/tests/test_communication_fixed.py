"""
Fixed Agent Communication Tests
Resolves async/await issues and deprecation warnings
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock
import sys
import os

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from app.protocols.communication import (
    HierarchicalProtocol, PeerToPeerProtocol, BroadcastProtocol,
    CommunicationManager
)
from app.protocols.message_types import (
    AgentMessage, MessageType, Priority, MessageQueue,
    MessageRouter, LoadBalancer
)

class TestAgentMessage:
    """Test agent message functionality"""
    
    def test_message_creation(self):
        """Test message creation"""
        message = AgentMessage(
            sender_id="agent_001",
            receiver_id="agent_002",
            message_type=MessageType.COORDINATION,
            payload={"action": "test"},
            priority=Priority.NORMAL
        )
        
        assert message.sender_id == "agent_001"
        assert message.receiver_id == "agent_002"
        assert message.message_type == MessageType.COORDINATION
        assert message.priority == Priority.NORMAL
        assert "action" in message.payload
    
    def test_message_expiration(self):
        """Test message expiration"""
        old_message = AgentMessage(
            sender_id="agent_001",
            receiver_id="agent_002",
            message_type=MessageType.COORDINATION,
            payload={"action": "test"},
            priority=Priority.NORMAL,
            expires_at=datetime.now() - timedelta(seconds=400)
        )
        
        assert old_message.is_expired() is True
        
        new_message = AgentMessage(
            sender_id="agent_001",
            receiver_id="agent_002",
            message_type=MessageType.COORDINATION,
            payload={"action": "test"},
            priority=Priority.NORMAL,
            expires_at=datetime.now() + timedelta(seconds=400)
        )
        
        assert new_message.is_expired() is False

class TestHierarchicalProtocol:
    """Test hierarchical communication protocol"""
    
    def setup_method(self):
        self.master_protocol = HierarchicalProtocol("master_001")
    
    @pytest.mark.asyncio
    async def test_add_sub_agent(self):
        """Test adding sub-agent"""
        await self.master_protocol.add_sub_agent("sub-agent-001")
        assert "sub-agent-001" in self.master_protocol.sub_agents
    
    @pytest.mark.asyncio
    async def test_send_to_sub_agents(self):
        """Test sending to sub-agents"""
        await self.master_protocol.add_sub_agent("sub-agent-001")
        await self.master_protocol.add_sub_agent("sub-agent-002")
        
        message = AgentMessage(
            sender_id="master_001",
            receiver_id="broadcast",
            message_type=MessageType.COORDINATION,
            payload={"action": "test"},
            priority=Priority.NORMAL
        )
        
        result = await self.master_protocol.send_message(message)
        assert result == 2  # Sent to 2 sub-agents

class TestPeerToPeerProtocol:
    """Test peer-to-peer communication protocol"""
    
    def setup_method(self):
        self.p2p_protocol = PeerToPeerProtocol("agent_001")
    
    @pytest.mark.asyncio
    async def test_add_peer(self):
        """Test adding peer"""
        await self.p2p_protocol.add_peer("agent-002", {"endpoint": "http://localhost:8002"})
        assert "agent-002" in self.p2p_protocol.peers
    
    @pytest.mark.asyncio
    async def test_remove_peer(self):
        """Test removing peer"""
        await self.p2p_protocol.add_peer("agent-002", {"endpoint": "http://localhost:8002"})
        await self.p2p_protocol.remove_peer("agent-002")
        assert "agent-002" not in self.p2p_protocol.peers
    
    @pytest.mark.asyncio
    async def test_send_to_peer(self):
        """Test sending to peer"""
        await self.p2p_protocol.add_peer("agent-002", {"endpoint": "http://localhost:8002"})
        
        message = AgentMessage(
            sender_id="agent_001",
            receiver_id="agent-002",
            message_type=MessageType.COORDINATION,
            payload={"action": "test"},
            priority=Priority.NORMAL
        )
        
        result = await self.p2p_protocol.send_message(message)
        assert result is True

class TestBroadcastProtocol:
    """Test broadcast communication protocol"""
    
    def setup_method(self):
        self.broadcast_protocol = BroadcastProtocol("agent_001")
    
    @pytest.mark.asyncio
    async def test_subscribe_unsubscribe(self):
        """Test subscribe and unsubscribe"""
        await self.broadcast_protocol.subscribe("agent-002")
        assert "agent-002" in self.broadcast_protocol.subscribers
        
        await self.broadcast_protocol.unsubscribe("agent-002")
        assert "agent-002" not in self.broadcast_protocol.subscribers
    
    @pytest.mark.asyncio
    async def test_broadcast(self):
        """Test broadcasting"""
        await self.broadcast_protocol.subscribe("agent-002")
        await self.broadcast_protocol.subscribe("agent-003")
        
        message = AgentMessage(
            sender_id="agent_001",
            receiver_id="broadcast",
            message_type=MessageType.COORDINATION,
            payload={"action": "test"},
            priority=Priority.NORMAL
        )
        
        result = await self.broadcast_protocol.send_message(message)
        assert result == 2  # Sent to 2 subscribers

class TestCommunicationManager:
    """Test communication manager"""
    
    def setup_method(self):
        self.comm_manager = CommunicationManager("agent_001")
    
    @pytest.mark.asyncio
    async def test_send_message(self):
        """Test sending message through manager"""
        message = AgentMessage(
            sender_id="agent_001",
            receiver_id="agent_002",
            message_type=MessageType.COORDINATION,
            payload={"action": "test"},
            priority=Priority.NORMAL
        )
        
        result = await self.comm_manager.send_message(message)
        assert result is True

class TestMessageTemplates:
    """Test message templates"""
    
    def test_create_heartbeat(self):
        """Test heartbeat message creation"""
        from app.protocols.communication import create_heartbeat_message
        
        heartbeat = create_heartbeat_message("agent_001", "agent_002")
        assert heartbeat.message_type == MessageType.HEARTBEAT
        assert heartbeat.sender_id == "agent_001"
        assert heartbeat.receiver_id == "agent_002"

class TestCommunicationIntegration:
    """Integration tests for communication"""
    
    @pytest.mark.asyncio
    async def test_message_flow(self):
        """Test message flow between protocols"""
        # Create protocols
        master = HierarchicalProtocol("master")
        sub1 = PeerToPeerProtocol("sub1")
        sub2 = PeerToPeerProtocol("sub2")
        
        # Setup hierarchy
        await master.add_sub_agent("sub1")
        await master.add_sub_agent("sub2")
        
        # Create message
        message = AgentMessage(
            sender_id="master",
            receiver_id="broadcast",
            message_type=MessageType.COORDINATION,
            payload={"action": "test_flow"},
            priority=Priority.NORMAL
        )
        
        # Send message
        result = await master.send_message(message)
        assert result == 2

if __name__ == '__main__':
    pytest.main([__file__])
