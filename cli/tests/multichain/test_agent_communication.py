"""
Test for cross-chain agent communication system
"""

import asyncio
import pytest
from datetime import datetime, timedelta
from aitbc_cli.core.config import MultiChainConfig, NodeConfig
from aitbc_cli.core.agent_communication import (
    CrossChainAgentCommunication, AgentInfo, AgentMessage, 
    MessageType, AgentStatus, AgentCollaboration, AgentReputation
)

def test_agent_communication_creation():
    """Test agent communication system creation"""
    config = MultiChainConfig()
    comm = CrossChainAgentCommunication(config)
    
    assert comm.config == config
    assert comm.agents == {}
    assert comm.messages == {}
    assert comm.collaborations == {}
    assert comm.reputations == {}
    assert comm.routing_table == {}

async def test_agent_registration():
    """Test agent registration"""
    config = MultiChainConfig()
    comm = CrossChainAgentCommunication(config)
    
    # Create test agent
    agent_info = AgentInfo(
        agent_id="test-agent-1",
        name="Test Agent",
        chain_id="chain-1",
        node_id="node-1",
        status=AgentStatus.ACTIVE,
        capabilities=["trading", "analytics"],
        reputation_score=0.8,
        last_seen=datetime.now(),
        endpoint="http://localhost:8080",
        version="1.0.0"
    )
    
    # Register agent
    success = await comm.register_agent(agent_info)
    
    assert success
    assert "test-agent-1" in comm.agents
    assert comm.agents["test-agent-1"].name == "Test Agent"
    assert "test-agent-1" in comm.reputations
    assert comm.reputations["test-agent-1"].reputation_score == 0.8

async def test_agent_discovery():
    """Test agent discovery"""
    config = MultiChainConfig()
    comm = CrossChainAgentCommunication(config)
    
    # Register multiple agents
    agents = [
        AgentInfo(
            agent_id="agent-1",
            name="Agent 1",
            chain_id="chain-1",
            node_id="node-1",
            status=AgentStatus.ACTIVE,
            capabilities=["trading", "analytics"],
            reputation_score=0.8,
            last_seen=datetime.now(),
            endpoint="http://localhost:8080",
            version="1.0.0"
        ),
        AgentInfo(
            agent_id="agent-2",
            name="Agent 2",
            chain_id="chain-1",
            node_id="node-1",
            status=AgentStatus.ACTIVE,
            capabilities=["mining"],
            reputation_score=0.7,
            last_seen=datetime.now(),
            endpoint="http://localhost:8081",
            version="1.0.0"
        ),
        AgentInfo(
            agent_id="agent-3",
            name="Agent 3",
            chain_id="chain-2",
            node_id="node-2",
            status=AgentStatus.INACTIVE,
            capabilities=["trading"],
            reputation_score=0.6,
            last_seen=datetime.now(),
            endpoint="http://localhost:8082",
            version="1.0.0"
        )
    ]
    
    for agent in agents:
        await comm.register_agent(agent)
    
    # Discover agents on chain-1
    chain1_agents = await comm.discover_agents("chain-1")
    assert len(chain1_agents) == 2
    assert all(agent.chain_id == "chain-1" for agent in chain1_agents)
    
    # Discover agents with trading capability
    trading_agents = await comm.discover_agents("chain-1", ["trading"])
    assert len(trading_agents) == 1
    assert trading_agents[0].agent_id == "agent-1"
    
    # Discover active agents only
    active_agents = await comm.discover_agents("chain-1")
    assert all(agent.status == AgentStatus.ACTIVE for agent in active_agents)

async def test_message_sending():
    """Test message sending"""
    config = MultiChainConfig()
    comm = CrossChainAgentCommunication(config)
    
    # Register agents
    sender = AgentInfo(
        agent_id="sender-agent",
        name="Sender",
        chain_id="chain-1",
        node_id="node-1",
        status=AgentStatus.ACTIVE,
        capabilities=["trading"],
        reputation_score=0.8,
        last_seen=datetime.now(),
        endpoint="http://localhost:8080",
        version="1.0.0"
    )
    
    receiver = AgentInfo(
        agent_id="receiver-agent",
        name="Receiver",
        chain_id="chain-1",
        node_id="node-1",
        status=AgentStatus.ACTIVE,
        capabilities=["analytics"],
        reputation_score=0.7,
        last_seen=datetime.now(),
        endpoint="http://localhost:8081",
        version="1.0.0"
    )
    
    await comm.register_agent(sender)
    await comm.register_agent(receiver)
    
    # Create message
    message = AgentMessage(
        message_id="test-message-1",
        sender_id="sender-agent",
        receiver_id="receiver-agent",
        message_type=MessageType.COMMUNICATION,
        chain_id="chain-1",
        target_chain_id=None,
        payload={"action": "test", "data": "hello"},
        timestamp=datetime.now(),
        signature="test-signature",
        priority=5,
        ttl_seconds=3600
    )
    
    # Send message
    success = await comm.send_message(message)
    
    assert success
    assert "test-message-1" in comm.messages
    assert len(comm.message_queue["receiver-agent"]) == 0  # Should be delivered immediately

async def test_cross_chain_messaging():
    """Test cross-chain messaging"""
    config = MultiChainConfig()
    comm = CrossChainAgentCommunication(config)
    
    # Register agents on different chains
    sender = AgentInfo(
        agent_id="cross-chain-sender",
        name="Cross Chain Sender",
        chain_id="chain-1",
        node_id="node-1",
        status=AgentStatus.ACTIVE,
        capabilities=["trading"],
        reputation_score=0.8,
        last_seen=datetime.now(),
        endpoint="http://localhost:8080",
        version="1.0.0"
    )
    
    receiver = AgentInfo(
        agent_id="cross-chain-receiver",
        name="Cross Chain Receiver",
        chain_id="chain-2",
        node_id="node-2",
        status=AgentStatus.ACTIVE,
        capabilities=["analytics"],
        reputation_score=0.7,
        last_seen=datetime.now(),
        endpoint="http://localhost:8081",
        version="1.0.0"
    )
    
    await comm.register_agent(sender)
    await comm.register_agent(receiver)
    
    # Create cross-chain message
    message = AgentMessage(
        message_id="cross-chain-message-1",
        sender_id="cross-chain-sender",
        receiver_id="cross-chain-receiver",
        message_type=MessageType.COMMUNICATION,
        chain_id="chain-1",
        target_chain_id="chain-2",
        payload={"action": "cross_chain_test", "data": "hello across chains"},
        timestamp=datetime.now(),
        signature="test-signature",
        priority=5,
        ttl_seconds=3600
    )
    
    # Send cross-chain message
    success = await comm.send_message(message)
    
    assert success
    assert "cross-chain-message-1" in comm.messages

async def test_collaboration_creation():
    """Test multi-agent collaboration creation"""
    config = MultiChainConfig()
    comm = CrossChainAgentCommunication(config)
    
    # Register multiple agents
    agents = []
    for i in range(3):
        agent = AgentInfo(
            agent_id=f"collab-agent-{i+1}",
            name=f"Collab Agent {i+1}",
            chain_id=f"chain-{(i % 2) + 1}",  # Spread across 2 chains
            node_id=f"node-{(i % 2) + 1}",
            status=AgentStatus.ACTIVE,
            capabilities=["trading", "analytics"],
            reputation_score=0.8,
            last_seen=datetime.now(),
            endpoint=f"http://localhost:808{i}",
            version="1.0.0"
        )
        await comm.register_agent(agent)
        agents.append(agent.agent_id)
    
    # Create collaboration
    collaboration_id = await comm.create_collaboration(
        agents,
        "research_project",
        {"voting_threshold": 0.6, "resource_sharing": True}
    )
    
    assert collaboration_id is not None
    assert collaboration_id in comm.collaborations
    
    collaboration = comm.collaborations[collaboration_id]
    assert collaboration.collaboration_type == "research_project"
    assert len(collaboration.agent_ids) == 3
    assert collaboration.status == "active"
    assert collaboration.governance_rules["voting_threshold"] == 0.6

async def test_reputation_system():
    """Test reputation system"""
    config = MultiChainConfig()
    comm = CrossChainAgentCommunication(config)
    
    # Register agent
    agent = AgentInfo(
        agent_id="reputation-agent",
        name="Reputation Agent",
        chain_id="chain-1",
        node_id="node-1",
        status=AgentStatus.ACTIVE,
        capabilities=["trading"],
        reputation_score=0.5,  # Start with neutral reputation
        last_seen=datetime.now(),
        endpoint="http://localhost:8080",
        version="1.0.0"
    )
    
    await comm.register_agent(agent)
    
    # Update reputation with successful interactions
    for i in range(5):
        await comm.update_reputation("reputation-agent", True, 0.8)
    
    # Update reputation with some failures
    for i in range(2):
        await comm.update_reputation("reputation-agent", False, 0.3)
    
    # Check reputation
    reputation = comm.reputations["reputation-agent"]
    assert reputation.total_interactions == 7
    assert reputation.successful_interactions == 5
    assert reputation.failed_interactions == 2
    assert reputation.reputation_score > 0.5  # Should have improved

async def test_agent_status():
    """Test agent status retrieval"""
    config = MultiChainConfig()
    comm = CrossChainAgentCommunication(config)
    
    # Register agent
    agent = AgentInfo(
        agent_id="status-agent",
        name="Status Agent",
        chain_id="chain-1",
        node_id="node-1",
        status=AgentStatus.ACTIVE,
        capabilities=["trading", "analytics"],
        reputation_score=0.8,
        last_seen=datetime.now(),
        endpoint="http://localhost:8080",
        version="1.0.0"
    )
    
    await comm.register_agent(agent)
    
    # Get agent status
    status = await comm.get_agent_status("status-agent")
    
    assert status is not None
    assert status["agent_info"]["agent_id"] == "status-agent"
    assert status["status"] == "active"
    assert status["reputation"] is not None
    assert status["message_queue_size"] == 0
    assert status["active_collaborations"] == 0

async def test_network_overview():
    """Test network overview"""
    config = MultiChainConfig()
    comm = CrossChainAgentCommunication(config)
    
    # Register multiple agents
    for i in range(5):
        agent = AgentInfo(
            agent_id=f"network-agent-{i+1}",
            name=f"Network Agent {i+1}",
            chain_id=f"chain-{(i % 3) + 1}",  # Spread across 3 chains
            node_id=f"node-{(i % 2) + 1}",
            status=AgentStatus.ACTIVE if i < 4 else AgentStatus.BUSY,
            capabilities=["trading", "analytics"],
            reputation_score=0.7 + (i * 0.05),
            last_seen=datetime.now(),
            endpoint=f"http://localhost:808{i}",
            version="1.0.0"
        )
        await comm.register_agent(agent)
    
    # Create some collaborations
    collab_id = await comm.create_collaboration(
        ["network-agent-1", "network-agent-2"],
        "test_collaboration",
        {}
    )
    
    # Get network overview
    overview = await comm.get_network_overview()
    
    assert overview["total_agents"] == 5
    assert overview["active_agents"] == 4
    assert overview["total_collaborations"] == 1
    assert overview["active_collaborations"] == 1
    assert len(overview["agents_by_chain"]) == 3
    assert overview["average_reputation"] > 0.7

def test_validation_functions():
    """Test validation functions"""
    config = MultiChainConfig()
    comm = CrossChainAgentCommunication(config)
    
    # Test agent validation
    valid_agent = AgentInfo(
        agent_id="valid-agent",
        name="Valid Agent",
        chain_id="chain-1",
        node_id="node-1",
        status=AgentStatus.ACTIVE,
        capabilities=["trading"],
        reputation_score=0.8,
        last_seen=datetime.now(),
        endpoint="http://localhost:8080",
        version="1.0.0"
    )
    
    assert comm._validate_agent_info(valid_agent) == True
    
    # Test invalid agent (missing capabilities)
    invalid_agent = AgentInfo(
        agent_id="invalid-agent",
        name="Invalid Agent",
        chain_id="chain-1",
        node_id="node-1",
        status=AgentStatus.ACTIVE,
        capabilities=[],  # Empty capabilities
        reputation_score=0.8,
        last_seen=datetime.now(),
        endpoint="http://localhost:8080",
        version="1.0.0"
    )
    
    assert comm._validate_agent_info(invalid_agent) == False
    
    # Test message validation
    valid_message = AgentMessage(
        message_id="valid-message",
        sender_id="sender",
        receiver_id="receiver",
        message_type=MessageType.COMMUNICATION,
        chain_id="chain-1",
        target_chain_id=None,
        payload={"test": "data"},
        timestamp=datetime.now(),
        signature="signature",
        priority=5,
        ttl_seconds=3600
    )
    
    assert comm._validate_message(valid_message) == True

if __name__ == "__main__":
    # Run basic tests
    test_agent_communication_creation()
    test_validation_functions()
    
    # Run async tests
    asyncio.run(test_agent_registration())
    asyncio.run(test_agent_discovery())
    asyncio.run(test_message_sending())
    asyncio.run(test_cross_chain_messaging())
    asyncio.run(test_collaboration_creation())
    asyncio.run(test_reputation_system())
    asyncio.run(test_agent_status())
    asyncio.run(test_network_overview())
    
    print("✅ All agent communication tests passed!")
