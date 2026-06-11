"""
Agent Communication Tests
Tests for cross-chain agent communication system
"""

import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

# Add CLI path for imports
cli_path = Path("/opt/aitbc/cli")
if str(cli_path) not in sys.path:
    sys.path.insert(0, str(cli_path))

import pytest


class TestMessageType:
    """Test MessageType enum"""

    def test_message_type_values(self):
        """Test MessageType enum values"""
        from aitbc_cli.core.agent_communication import MessageType
        
        assert MessageType.DISCOVERY.value == "discovery"
        assert MessageType.ROUTING.value == "routing"
        assert MessageType.COMMUNICATION.value == "communication"
        assert MessageType.COLLABORATION.value == "collaboration"
        assert MessageType.PAYMENT.value == "payment"
        assert MessageType.REPUTATION.value == "reputation"
        assert MessageType.GOVERNANCE.value == "governance"


class TestAgentStatus:
    """Test AgentStatus enum"""

    def test_agent_status_values(self):
        """Test AgentStatus enum values"""
        from aitbc_cli.core.agent_communication import AgentStatus
        
        assert AgentStatus.ACTIVE.value == "active"
        assert AgentStatus.INACTIVE.value == "inactive"
        assert AgentStatus.BUSY.value == "busy"
        assert AgentStatus.OFFLINE.value == "offline"


class TestAgentInfo:
    """Test AgentInfo dataclass"""

    def test_agent_info_creation(self):
        """Test creating AgentInfo"""
        from aitbc_cli.core.agent_communication import AgentInfo, AgentStatus
        
        agent = AgentInfo(
            agent_id="agent123",
            name="Test Agent",
            chain_id="aitbc-main",
            node_id="node456",
            status=AgentStatus.ACTIVE,
            capabilities=["compute", "storage"],
            reputation_score=0.95,
            last_seen=datetime.now(),
            endpoint="http://localhost:8080",
            version="1.0.0"
        )
        
        assert agent.agent_id == "agent123"
        assert agent.name == "Test Agent"
        assert agent.status == AgentStatus.ACTIVE
        assert agent.reputation_score == 0.95


class TestAgentMessage:
    """Test AgentMessage dataclass"""

    def test_agent_message_creation(self):
        """Test creating AgentMessage"""
        from aitbc_cli.core.agent_communication import AgentMessage, MessageType
        
        message = AgentMessage(
            message_id="msg123",
            sender_id="agent1",
            receiver_id="agent2",
            message_type=MessageType.COMMUNICATION,
            chain_id="aitbc-main",
            target_chain_id="aitbc-test",
            payload={"data": "test"},
            timestamp=datetime.now(),
            signature="sig123",
            priority=1,
            ttl_seconds=3600
        )
        
        assert message.message_id == "msg123"
        assert message.sender_id == "agent1"
        assert message.message_type == MessageType.COMMUNICATION
        assert message.priority == 1


class TestAgentCollaboration:
    """Test AgentCollaboration dataclass"""

    def test_agent_collaboration_creation(self):
        """Test creating AgentCollaboration"""
        from aitbc_cli.core.agent_communication import AgentCollaboration
        
        collab = AgentCollaboration(
            collaboration_id="collab123",
            agent_ids=["agent1", "agent2"],
            chain_ids=["aitbc-main", "aitbc-test"],
            collaboration_type="compute",
            status="active",
            created_at=datetime.now(),
            updated_at=datetime.now(),
            shared_resources={"cpu": 4},
            governance_rules={"consensus": "majority"}
        )
        
        assert collab.collaboration_id == "collab123"
        assert len(collab.agent_ids) == 2
        assert collab.collaboration_type == "compute"


class TestAgentReputation:
    """Test AgentReputation dataclass"""

    def test_agent_reputation_creation(self):
        """Test creating AgentReputation"""
        from aitbc_cli.core.agent_communication import AgentReputation
        
        reputation = AgentReputation(
            agent_id="agent123",
            chain_id="aitbc-main",
            reputation_score=0.95,
            successful_interactions=100,
            failed_interactions=5,
            total_interactions=105,
            last_updated=datetime.now(),
            feedback_scores=[5.0, 4.5, 5.0]
        )
        
        assert reputation.agent_id == "agent123"
        assert reputation.reputation_score == 0.95
        assert reputation.total_interactions == 105


class TestCrossChainAgentCommunication:
    """Test CrossChainAgentCommunication class"""

    @patch('aitbc_cli.core.agent_communication.NodeClient')
    def test_init(self, mock_node_client):
        """Test CrossChainAgentCommunication initialization"""
        from aitbc_cli.core.agent_communication import CrossChainAgentCommunication, MultiChainConfig
        
        config = Mock(spec=MultiChainConfig)
        comm = CrossChainAgentCommunication(config)
        
        assert comm.config == config
        assert comm.agents == {}
        assert comm.messages == {}
        assert comm.collaborations == {}
        assert comm.reputations == {}
        assert comm.routing_table == {}
        assert 'max_message_size' in comm.thresholds
        assert comm.thresholds['max_message_size'] == 1048576

    @patch('aitbc_cli.core.agent_communication.NodeClient')
    def test_validate_agent_info(self, mock_node_client):
        """Test agent info validation"""
        from aitbc_cli.core.agent_communication import AgentInfo, AgentStatus, CrossChainAgentCommunication, MultiChainConfig
        
        config = Mock(spec=MultiChainConfig)
        comm = CrossChainAgentCommunication(config)
        
        agent = AgentInfo(
            agent_id="agent123",
            name="Test Agent",
            chain_id="aitbc-main",
            node_id="node456",
            status=AgentStatus.ACTIVE,
            capabilities=["compute"],
            reputation_score=0.95,
            last_seen=datetime.now(),
            endpoint="http://localhost:8080",
            version="1.0.0"
        )
        
        # Test validation
        result = comm._validate_agent_info(agent)
        assert result is True

    @patch('aitbc_cli.core.agent_communication.NodeClient')
    def test_validate_agent_info_invalid(self, mock_node_client):
        """Test agent info validation with invalid data"""
        from aitbc_cli.core.agent_communication import AgentInfo, AgentStatus, CrossChainAgentCommunication, MultiChainConfig
        
        config = Mock(spec=MultiChainConfig)
        comm = CrossChainAgentCommunication(config)
        
        # Invalid reputation score
        agent = AgentInfo(
            agent_id="agent123",
            name="Test Agent",
            chain_id="aitbc-main",
            node_id="node456",
            status=AgentStatus.ACTIVE,
            capabilities=["compute"],
            reputation_score=1.5,  # Invalid > 1.0
            last_seen=datetime.now(),
            endpoint="http://localhost:8080",
            version="1.0.0"
        )
        
        result = comm._validate_agent_info(agent)
        assert result is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
