"""
Tests for Agent Communication Protocols
"""

import sys
import pytest
import asyncio
from datetime import datetime, UTC, timedelta
from unittest.mock import Mock, AsyncMock

from src.app.protocols.communication import (
    AgentMessage, MessageType, Priority, CommunicationProtocol,
    HierarchicalProtocol, PeerToPeerProtocol, BroadcastProtocol,
    CommunicationManager, MessageTemplates
)

class TestAgentMessage:
    """Test AgentMessage class"""
    
    def test_message_creation(self):
        """Test message creation"""
        message = AgentMessage(
            sender_id="agent-001",
            receiver_id="agent-002",
            message_type=MessageType.DIRECT,
            priority=Priority.NORMAL,
            payload={"data": "test"}
        )
        
        assert message.sender_id == "agent-001"
        assert message.receiver_id == "agent-002"
        assert message.message_type == MessageType.DIRECT
        assert message.priority == Priority.NORMAL
        assert message.payload["data"] == "test"
        assert message.ttl == 300
    
    def test_message_serialization(self):
        """Test message serialization"""
        message = AgentMessage(
            sender_id="agent-001",
            receiver_id="agent-002",
            message_type=MessageType.DIRECT,
            priority=Priority.NORMAL,
            payload={"data": "test"}
        )
        
        # To dict
        message_dict = message.to_dict()
        assert message_dict["sender_id"] == "agent-001"
        assert message_dict["message_type"] == "direct"
        assert message_dict["priority"] == "normal"
        
        # From dict
        restored_message = AgentMessage.from_dict(message_dict)
        assert restored_message.sender_id == message.sender_id
        assert restored_message.receiver_id == message.receiver_id
        assert restored_message.message_type == message.message_type
        assert restored_message.priority == message.priority
    
    def test_message_expiration(self):
        """Test message expiration"""
        old_message = AgentMessage(
            sender_id="agent-001",
            receiver_id="agent-002",
            message_type=MessageType.DIRECT,
            timestamp=datetime.now(datetime.UTC) - timedelta(seconds=400),
            ttl=300
        )
        
        # Message should be expired
        age = (datetime.now(datetime.UTC) - old_message.timestamp).total_seconds()
        assert age > old_message.ttl

class TestHierarchicalProtocol:
    """Test HierarchicalProtocol class"""
    
    @pytest.fixture
    def master_protocol(self):
        """Create master protocol"""
        return HierarchicalProtocol("master-agent", is_master=True)
    
    @pytest.fixture
    def sub_protocol(self):
        """Create sub-agent protocol"""
        return HierarchicalProtocol("sub-agent", is_master=False)
    
    def test_add_sub_agent(self, master_protocol):
        """Test adding sub-agent"""
        master_protocol.add_sub_agent("sub-agent-001")
        assert "sub-agent-001" in master_protocol.sub_agents
    
    def test_send_to_sub_agents(self, master_protocol):
        """Test sending to sub-agents"""
        master_protocol.add_sub_agent("sub-agent-001")
        master_protocol.add_sub_agent("sub-agent-002")
        
        message = MessageTemplates.create_heartbeat("master-agent")
        
        # Mock the send_message method
        master_protocol.send_message = AsyncMock(return_value=True)
        
        # Should send to both sub-agents
        asyncio.run(master_protocol.send_to_sub_agents(message))
        
        # Check that send_message was called twice
        assert master_protocol.send_message.call_count == 2
    
    def test_send_to_master(self, sub_protocol):
        """Test sending to master"""
        sub_protocol.master_agent = "master-agent"
        
        message = MessageTemplates.create_status_update("sub-agent", {"status": "active"})
        
        # Mock the send_message method
        sub_protocol.send_message = AsyncMock(return_value=True)
        
        asyncio.run(sub_protocol.send_to_master(message))
        
        # Check that send_message was called once
        assert sub_protocol.send_message.call_count == 1

class TestPeerToPeerProtocol:
    """Test PeerToPeerProtocol class"""
    
    @pytest.fixture
    def p2p_protocol(self):
        """Create P2P protocol"""
        return PeerToPeerProtocol("agent-001")
    
    def test_add_peer(self, p2p_protocol):
        """Test adding peer"""
        p2p_protocol.add_peer("agent-002", {"endpoint": "http://localhost:8002"})
        assert "agent-002" in p2p_protocol.peers
        assert p2p_protocol.peers["agent-002"]["endpoint"] == "http://localhost:8002"
    
    def test_remove_peer(self, p2p_protocol):
        """Test removing peer"""
        p2p_protocol.add_peer("agent-002", {"endpoint": "http://localhost:8002"})
        p2p_protocol.remove_peer("agent-002")
        assert "agent-002" not in p2p_protocol.peers
    
    def test_send_to_peer(self, p2p_protocol):
        """Test sending to peer"""
        p2p_protocol.add_peer("agent-002", {"endpoint": "http://localhost:8002"})
        
        message = MessageTemplates.create_task_assignment(
            "agent-001", "agent-002", {"task": "test"}
        )
        
        # Mock the send_message method
        p2p_protocol.send_message = AsyncMock(return_value=True)
        
        result = asyncio.run(p2p_protocol.send_to_peer(message, "agent-002"))
        
        assert result is True
        assert p2p_protocol.send_message.call_count == 1

class TestBroadcastProtocol:
    """Test BroadcastProtocol class"""
    
    @pytest.fixture
    def broadcast_protocol(self):
        """Create broadcast protocol"""
        return BroadcastProtocol("agent-001", "test-channel")
    
    def test_subscribe_unsubscribe(self, broadcast_protocol):
        """Test subscribe and unsubscribe"""
        broadcast_protocol.subscribe("agent-002")
        assert "agent-002" in broadcast_protocol.subscribers
        
        broadcast_protocol.unsubscribe("agent-002")
        assert "agent-002" not in broadcast_protocol.subscribers
    
    def test_broadcast(self, broadcast_protocol):
        """Test broadcasting"""
        broadcast_protocol.subscribe("agent-002")
        broadcast_protocol.subscribe("agent-003")
        
        message = MessageTemplates.create_discovery("agent-001")
        
        # Mock the send_message method
        broadcast_protocol.send_message = AsyncMock(return_value=True)
        
        asyncio.run(broadcast_protocol.broadcast(message))
        
        # Should send to 2 subscribers (not including self)
        assert broadcast_protocol.send_message.call_count == 2

class TestCommunicationManager:
    """Test CommunicationManager class"""
    
    @pytest.fixture
    def comm_manager(self):
        """Create communication manager"""
        return CommunicationManager("agent-001")
    
    def test_add_protocol(self, comm_manager):
        """Test adding protocol"""
        protocol = Mock(spec=CommunicationProtocol)
        comm_manager.add_protocol("test", protocol)
        
        assert "test" in comm_manager.protocols
        assert comm_manager.protocols["test"] == protocol
    
    def test_get_protocol(self, comm_manager):
        """Test getting protocol"""
        protocol = Mock(spec=CommunicationProtocol)
        comm_manager.add_protocol("test", protocol)
        
        retrieved_protocol = comm_manager.get_protocol("test")
        assert retrieved_protocol == protocol
        
        # Test non-existent protocol
        assert comm_manager.get_protocol("non-existent") is None
    
    @pytest.mark.asyncio
    async def test_send_message(self, comm_manager):
        """Test sending message"""
        protocol = Mock(spec=CommunicationProtocol)
        protocol.send_message = AsyncMock(return_value=True)
        comm_manager.add_protocol("test", protocol)
        
        message = MessageTemplates.create_heartbeat("agent-001")
        result = await comm_manager.send_message("test", message)
        
        assert result is True
        protocol.send_message.assert_called_once_with(message)
    
    @pytest.mark.asyncio
    async def test_register_handler(self, comm_manager):
        """Test registering handler"""
        protocol = Mock(spec=CommunicationProtocol)
        protocol.register_handler = AsyncMock()
        comm_manager.add_protocol("test", protocol)
        
        handler = AsyncMock()
        await comm_manager.register_handler("test", MessageType.HEARTBEAT, handler)
        
        protocol.register_handler.assert_called_once_with(MessageType.HEARTBEAT, handler)

class TestMessageTemplates:
    """Test MessageTemplates class"""
    
    def test_create_heartbeat(self):
        """Test creating heartbeat message"""
        message = MessageTemplates.create_heartbeat("agent-001")
        
        assert message.sender_id == "agent-001"
        assert message.message_type == MessageType.HEARTBEAT
        assert message.priority == Priority.LOW
        assert "timestamp" in message.payload
    
    def test_create_task_assignment(self):
        """Test creating task assignment message"""
        task_data = {"task_id": "task-001", "task_type": "process_data"}
        message = MessageTemplates.create_task_assignment("agent-001", "agent-002", task_data)
        
        assert message.sender_id == "agent-001"
        assert message.receiver_id == "agent-002"
        assert message.message_type == MessageType.TASK_ASSIGNMENT
        assert message.payload == task_data
    
    def test_create_status_update(self):
        """Test creating status update message"""
        status_data = {"status": "active", "load": 0.5}
        message = MessageTemplates.create_status_update("agent-001", status_data)
        
        assert message.sender_id == "agent-001"
        assert message.message_type == MessageType.STATUS_UPDATE
        assert message.payload == status_data
    
    def test_create_discovery(self):
        """Test creating discovery message"""
        message = MessageTemplates.create_discovery("agent-001")
        
        assert message.sender_id == "agent-001"
        assert message.message_type == MessageType.DISCOVERY
        assert message.payload["agent_id"] == "agent-001"
    
    def test_create_consensus_request(self):
        """Test creating consensus request message"""
        proposal_data = {"proposal": "test_proposal"}
        message = MessageTemplates.create_consensus_request("agent-001", proposal_data)
        
        assert message.sender_id == "agent-001"
        assert message.message_type == MessageType.CONSENSUS
        assert message.priority == Priority.HIGH
        assert message.payload == proposal_data

# Integration tests
class TestCommunicationIntegration:
    """Integration tests for communication system"""
    
    @pytest.mark.asyncio
    async def test_message_flow(self):
        """Test complete message flow"""
        # Create communication manager
        comm_manager = CommunicationManager("agent-001")
        
        # Create protocols
        hierarchical = HierarchicalProtocol("agent-001", is_master=True)
        p2p = PeerToPeerProtocol("agent-001")
        
        # Add protocols
        comm_manager.add_protocol("hierarchical", hierarchical)
        comm_manager.add_protocol("p2p", p2p)
        
        # Mock message sending
        hierarchical.send_message = AsyncMock(return_value=True)
        p2p.send_message = AsyncMock(return_value=True)
        
        # Register handler
        async def handle_heartbeat(message):
            assert message.sender_id == "agent-002"
            assert message.message_type == MessageType.HEARTBEAT
        
        await comm_manager.register_handler("hierarchical", MessageType.HEARTBEAT, handle_heartbeat)
        
        # Send heartbeat
        heartbeat = MessageTemplates.create_heartbeat("agent-001")
        result = await comm_manager.send_message("hierarchical", heartbeat)
        
        assert result is True
        hierarchical.send_message.assert_called_once()

if __name__ == "__main__":
    pytest.main([__file__])
