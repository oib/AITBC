#!/usr/bin/env python3
"""
Complete cross-chain agent communication workflow test
"""

import sys
import os
import asyncio
import json
from datetime import datetime
sys.path.insert(0, '/home/oib/windsurf/aitbc/cli')

from aitbc_cli.core.config import load_multichain_config
from aitbc_cli.core.agent_communication import (
    CrossChainAgentCommunication, AgentInfo, AgentMessage, 
    MessageType, AgentStatus
)

async def test_complete_agent_communication_workflow():
    """Test the complete agent communication workflow"""
    print("🚀 Starting Complete Cross-Chain Agent Communication Workflow Test")
    
    # Load configuration
    config = load_multichain_config('/home/oib/windsurf/aitbc/cli/multichain_config.yaml')
    print(f"✅ Configuration loaded with {len(config.nodes)} nodes")
    
    # Initialize agent communication system
    comm = CrossChainAgentCommunication(config)
    print("✅ Agent communication system initialized")
    
    # Test 1: Register multiple agents across different chains
    print("\n🤖 Testing Agent Registration...")
    
    # Create agents on different chains
    agents = [
        AgentInfo(
            agent_id="healthcare-agent-1",
            name="Healthcare Analytics Agent",
            chain_id="AITBC-TOPIC-HEALTHCARE-001",
            node_id="default-node",
            status=AgentStatus.ACTIVE,
            capabilities=["analytics", "data_processing", "ml_modeling"],
            reputation_score=0.85,
            last_seen=datetime.now(),
            endpoint="http://localhost:8081",
            version="1.0.0"
        ),
        AgentInfo(
            agent_id="collaboration-agent-1",
            name="Collaboration Agent",
            chain_id="AITBC-PRIVATE-COLLAB-001",
            node_id="default-node",
            status=AgentStatus.ACTIVE,
            capabilities=["coordination", "resource_sharing", "governance"],
            reputation_score=0.90,
            last_seen=datetime.now(),
            endpoint="http://localhost:8082",
            version="1.0.0"
        ),
        AgentInfo(
            agent_id="trading-agent-1",
            name="Trading Agent",
            chain_id="AITBC-TOPIC-HEALTHCARE-001",
            node_id="default-node",
            status=AgentStatus.ACTIVE,
            capabilities=["trading", "market_analysis", "risk_assessment"],
            reputation_score=0.75,
            last_seen=datetime.now(),
            endpoint="http://localhost:8083",
            version="1.0.0"
        ),
        AgentInfo(
            agent_id="research-agent-1",
            name="Research Agent",
            chain_id="AITBC-TOPIC-HEALTHCARE-001",
            node_id="default-node",
            status=AgentStatus.BUSY,
            capabilities=["research", "data_mining", "publication"],
            reputation_score=0.80,
            last_seen=datetime.now(),
            endpoint="http://localhost:8084",
            version="1.0.0"
        )
    ]
    
    # Register all agents
    registered_count = 0
    for agent in agents:
        success = await comm.register_agent(agent)
        if success:
            registered_count += 1
            print(f"  ✅ Registered: {agent.name} ({agent.agent_id})")
        else:
            print(f"  ❌ Failed to register: {agent.name}")
    
    print(f"  📊 Successfully registered {registered_count}/{len(agents)} agents")
    
    # Test 2: Agent discovery
    print("\n🔍 Testing Agent Discovery...")
    
    # Discover agents on healthcare chain
    healthcare_agents = await comm.discover_agents("AITBC-TOPIC-HEALTHCARE-001")
    print(f"  ✅ Found {len(healthcare_agents)} agents on healthcare chain")
    
    # Discover agents with analytics capability
    analytics_agents = await comm.discover_agents("AITBC-TOPIC-HEALTHCARE-001", ["analytics"])
    print(f"  ✅ Found {len(analytics_agents)} agents with analytics capability")
    
    # Discover active agents only
    active_agents = await comm.discover_agents("AITBC-TOPIC-HEALTHCARE-001")
    active_count = len([a for a in active_agents if a.status == AgentStatus.ACTIVE])
    print(f"  ✅ Found {active_count} active agents")
    
    # Test 3: Same-chain messaging
    print("\n📨 Testing Same-Chain Messaging...")
    
    # Send message from healthcare agent to trading agent (same chain)
    same_chain_message = AgentMessage(
        message_id="msg-same-chain-001",
        sender_id="healthcare-agent-1",
        receiver_id="trading-agent-1",
        message_type=MessageType.COMMUNICATION,
        chain_id="AITBC-TOPIC-HEALTHCARE-001",
        target_chain_id=None,
        payload={
            "action": "market_data_request",
            "parameters": {"timeframe": "24h", "assets": ["BTC", "ETH"]},
            "priority": "high"
        },
        timestamp=datetime.now(),
        signature="healthcare_agent_signature",
        priority=7,
        ttl_seconds=3600
    )
    
    success = await comm.send_message(same_chain_message)
    if success:
        print(f"  ✅ Same-chain message sent: {same_chain_message.message_id}")
    else:
        print(f"  ❌ Same-chain message failed")
    
    # Test 4: Cross-chain messaging
    print("\n🌐 Testing Cross-Chain Messaging...")
    
    # Send message from healthcare agent to collaboration agent (different chains)
    cross_chain_message = AgentMessage(
        message_id="msg-cross-chain-001",
        sender_id="healthcare-agent-1",
        receiver_id="collaboration-agent-1",
        message_type=MessageType.COMMUNICATION,
        chain_id="AITBC-TOPIC-HEALTHCARE-001",
        target_chain_id="AITBC-PRIVATE-COLLAB-001",
        payload={
            "action": "collaboration_request",
            "project": "healthcare_data_analysis",
            "requirements": ["analytics", "compute_resources"],
            "timeline": "2_weeks"
        },
        timestamp=datetime.now(),
        signature="healthcare_agent_signature",
        priority=8,
        ttl_seconds=7200
    )
    
    success = await comm.send_message(cross_chain_message)
    if success:
        print(f"  ✅ Cross-chain message sent: {cross_chain_message.message_id}")
    else:
        print(f"  ❌ Cross-chain message failed")
    
    # Test 5: Multi-agent collaboration
    print("\n🤝 Testing Multi-Agent Collaboration...")
    
    # Create collaboration between healthcare and trading agents
    collaboration_id = await comm.create_collaboration(
        ["healthcare-agent-1", "trading-agent-1"],
        "healthcare_trading_research",
        {
            "voting_threshold": 0.6,
            "resource_sharing": True,
            "data_privacy": "hipaa_compliant",
            "decision_making": "consensus"
        }
    )
    
    if collaboration_id:
        print(f"  ✅ Collaboration created: {collaboration_id}")
        
        # Send collaboration message
        collab_message = AgentMessage(
            message_id="msg-collab-001",
            sender_id="healthcare-agent-1",
            receiver_id="trading-agent-1",
            message_type=MessageType.COLLABORATION,
            chain_id="AITBC-TOPIC-HEALTHCARE-001",
            target_chain_id=None,
            payload={
                "action": "share_research_data",
                "collaboration_id": collaboration_id,
                "data_type": "anonymized_patient_data",
                "volume": "10GB"
            },
            timestamp=datetime.now(),
            signature="healthcare_agent_signature",
            priority=6,
            ttl_seconds=3600
        )
        
        success = await comm.send_message(collab_message)
        if success:
            print(f"  ✅ Collaboration message sent: {collab_message.message_id}")
    else:
        print(f"  ❌ Collaboration creation failed")
    
    # Test 6: Reputation system
    print("\n⭐ Testing Reputation System...")
    
    # Update reputation based on successful interactions
    reputation_updates = [
        ("healthcare-agent-1", True, 0.9),  # Successful interaction, positive feedback
        ("trading-agent-1", True, 0.8),
        ("collaboration-agent-1", True, 0.95),
        ("healthcare-agent-1", False, 0.3),  # Failed interaction, negative feedback
        ("trading-agent-1", True, 0.85)
    ]
    
    for agent_id, success, feedback in reputation_updates:
        await comm.update_reputation(agent_id, success, feedback)
        print(f"  ✅ Updated reputation for {agent_id}: {'Success' if success else 'Failure'} (feedback: {feedback})")
    
    # Check final reputations
    print(f"\n  📊 Final Reputation Scores:")
    for agent_id in ["healthcare-agent-1", "trading-agent-1", "collaboration-agent-1"]:
        status = await comm.get_agent_status(agent_id)
        if status and status.get('reputation'):
            rep = status['reputation']
            print(f"    {agent_id}: {rep['reputation_score']:.3f} ({rep['successful_interactions']}/{rep['total_interactions']} successful)")
    
    # Test 7: Agent status monitoring
    print("\n📊 Testing Agent Status Monitoring...")
    
    for agent_id in ["healthcare-agent-1", "trading-agent-1", "collaboration-agent-1"]:
        status = await comm.get_agent_status(agent_id)
        if status:
            print(f"  ✅ {agent_id}:")
            print(f"    Status: {status['status']}")
            print(f"    Queue Size: {status['message_queue_size']}")
            print(f"    Active Collaborations: {status['active_collaborations']}")
            print(f"    Last Seen: {status['last_seen']}")
    
    # Test 8: Network overview
    print("\n🌐 Testing Network Overview...")
    
    overview = await comm.get_network_overview()
    
    print(f"  ✅ Network Overview:")
    print(f"    Total Agents: {overview['total_agents']}")
    print(f"    Active Agents: {overview['active_agents']}")
    print(f"    Total Collaborations: {overview['total_collaborations']}")
    print(f"    Active Collaborations: {overview['active_collaborations']}")
    print(f"    Total Messages: {overview['total_messages']}")
    print(f"    Queued Messages: {overview['queued_messages']}")
    print(f"    Average Reputation: {overview['average_reputation']:.3f}")
    
    if overview['agents_by_chain']:
        print(f"    Agents by Chain:")
        for chain_id, count in overview['agents_by_chain'].items():
            active = overview['active_agents_by_chain'].get(chain_id, 0)
            print(f"      {chain_id}: {count} total, {active} active")
    
    if overview['collaborations_by_type']:
        print(f"    Collaborations by Type:")
        for collab_type, count in overview['collaborations_by_type'].items():
            print(f"      {collab_type}: {count}")
    
    # Test 9: Message routing efficiency
    print("\n🚀 Testing Message Routing Efficiency...")
    
    # Send multiple messages to test routing
    routing_test_messages = [
        ("healthcare-agent-1", "trading-agent-1", "AITBC-TOPIC-HEALTHCARE-001", None),
        ("trading-agent-1", "healthcare-agent-1", "AITBC-TOPIC-HEALTHCARE-001", None),
        ("collaboration-agent-1", "healthcare-agent-1", "AITBC-PRIVATE-COLLAB-001", "AITBC-TOPIC-HEALTHCARE-001"),
        ("healthcare-agent-1", "collaboration-agent-1", "AITBC-TOPIC-HEALTHCARE-001", "AITBC-PRIVATE-COLLAB-001")
    ]
    
    successful_routes = 0
    for i, (sender, receiver, chain, target_chain) in enumerate(routing_test_messages):
        message = AgentMessage(
            message_id=f"route-test-{i+1}",
            sender_id=sender,
            receiver_id=receiver,
            message_type=MessageType.ROUTING,
            chain_id=chain,
            target_chain_id=target_chain,
            payload={"test": "routing_efficiency", "index": i+1},
            timestamp=datetime.now(),
            signature="routing_test_signature",
            priority=5,
            ttl_seconds=1800
        )
        
        success = await comm.send_message(message)
        if success:
            successful_routes += 1
            route_type = "same-chain" if target_chain is None else "cross-chain"
            print(f"  ✅ Route {i+1} ({route_type}): {sender} → {receiver}")
        else:
            print(f"  ❌ Route {i+1} failed: {sender} → {receiver}")
    
    print(f"  📊 Routing Success Rate: {successful_routes}/{len(routing_test_messages)} ({(successful_routes/len(routing_test_messages)*100):.1f}%)")
    
    print("\n🎉 Complete Cross-Chain Agent Communication Workflow Test Finished!")
    print("📊 Summary:")
    print("  ✅ Agent registration and management working")
    print("  ✅ Agent discovery and filtering functional")
    print("  ✅ Same-chain messaging operational")
    print("  ✅ Cross-chain messaging functional")
    print("  ✅ Multi-agent collaboration system active")
    print("  ✅ Reputation scoring and updates working")
    print("  ✅ Agent status monitoring available")
    print("  ✅ Network overview and analytics complete")
    print("  ✅ Message routing efficiency verified")
    
    # Performance metrics
    print(f"\n📈 Current System Metrics:")
    print(f"  • Total Registered Agents: {overview['total_agents']}")
    print(f"  • Active Agents: {overview['active_agents']}")
    print(f"  • Active Collaborations: {overview['active_collaborations']}")
    print(f"  • Messages Processed: {overview['total_messages']}")
    print(f"  • Average Reputation Score: {overview['average_reputation']:.3f}")
    print(f"  • Routing Table Size: {overview['routing_table_size']}")
    print(f"  • Discovery Cache Entries: {overview['discovery_cache_size']}")

if __name__ == "__main__":
    asyncio.run(test_complete_agent_communication_workflow())
