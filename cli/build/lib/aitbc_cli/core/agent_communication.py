"""
Cross-chain agent communication system
"""

import asyncio
import json
import hashlib
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, asdict
from enum import Enum
import uuid
from collections import defaultdict

from ..core.config import MultiChainConfig
from ..core.node_client import NodeClient

class MessageType(Enum):
    """Agent message types"""
    DISCOVERY = "discovery"
    ROUTING = "routing"
    COMMUNICATION = "communication"
    COLLABORATION = "collaboration"
    PAYMENT = "payment"
    REPUTATION = "reputation"
    GOVERNANCE = "governance"

class AgentStatus(Enum):
    """Agent status"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    BUSY = "busy"
    OFFLINE = "offline"

@dataclass
class AgentInfo:
    """Agent information"""
    agent_id: str
    name: str
    chain_id: str
    node_id: str
    status: AgentStatus
    capabilities: List[str]
    reputation_score: float
    last_seen: datetime
    endpoint: str
    version: str

@dataclass
class AgentMessage:
    """Agent communication message"""
    message_id: str
    sender_id: str
    receiver_id: str
    message_type: MessageType
    chain_id: str
    target_chain_id: Optional[str]
    payload: Dict[str, Any]
    timestamp: datetime
    signature: str
    priority: int
    ttl_seconds: int

@dataclass
class AgentCollaboration:
    """Agent collaboration record"""
    collaboration_id: str
    agent_ids: List[str]
    chain_ids: List[str]
    collaboration_type: str
    status: str
    created_at: datetime
    updated_at: datetime
    shared_resources: Dict[str, Any]
    governance_rules: Dict[str, Any]

@dataclass
class AgentReputation:
    """Agent reputation record"""
    agent_id: str
    chain_id: str
    reputation_score: float
    successful_interactions: int
    failed_interactions: int
    total_interactions: int
    last_updated: datetime
    feedback_scores: List[float]

class CrossChainAgentCommunication:
    """Cross-chain agent communication system"""
    
    def __init__(self, config: MultiChainConfig):
        self.config = config
        self.agents: Dict[str, AgentInfo] = {}
        self.messages: Dict[str, AgentMessage] = {}
        self.collaborations: Dict[str, AgentCollaboration] = {}
        self.reputations: Dict[str, AgentReputation] = {}
        self.routing_table: Dict[str, List[str]] = {}
        self.discovery_cache: Dict[str, List[AgentInfo]] = {}
        self.message_queue: Dict[str, List[AgentMessage]] = defaultdict(list)
        
        # Communication thresholds
        self.thresholds = {
            'max_message_size': 1048576,  # 1MB
            'max_ttl_seconds': 3600,  # 1 hour
            'max_queue_size': 1000,
            'min_reputation_score': 0.5,
            'max_collaboration_size': 10
        }
    
    async def register_agent(self, agent_info: AgentInfo) -> bool:
        """Register an agent in the cross-chain network"""
        try:
            # Validate agent info
            if not self._validate_agent_info(agent_info):
                return False
            
            # Check if agent already exists
            if agent_info.agent_id in self.agents:
                # Update existing agent
                self.agents[agent_info.agent_id] = agent_info
            else:
                # Register new agent
                self.agents[agent_info.agent_id] = agent_info
                
                # Initialize reputation
                if agent_info.agent_id not in self.reputations:
                    self.reputations[agent_info.agent_id] = AgentReputation(
                        agent_id=agent_info.agent_id,
                        chain_id=agent_info.chain_id,
                        reputation_score=agent_info.reputation_score,
                        successful_interactions=0,
                        failed_interactions=0,
                        total_interactions=0,
                        last_updated=datetime.now(),
                        feedback_scores=[]
                    )
            
            # Update routing table
            self._update_routing_table(agent_info)
            
            # Clear discovery cache
            self.discovery_cache.clear()
            
            return True
            
        except Exception as e:
            print(f"Error registering agent {agent_info.agent_id}: {e}")
            return False
    
    async def discover_agents(self, chain_id: str, capabilities: Optional[List[str]] = None) -> List[AgentInfo]:
        """Discover agents on a specific chain"""
        cache_key = f"{chain_id}:{'_'.join(capabilities or [])}"
        
        # Check cache first
        if cache_key in self.discovery_cache:
            cached_time = self.discovery_cache[cache_key][0].last_seen if self.discovery_cache[cache_key] else None
            if cached_time and (datetime.now() - cached_time).seconds < 300:  # 5 minute cache
                return self.discovery_cache[cache_key]
        
        # Discover agents from chain
        agents = []
        
        for agent_id, agent_info in self.agents.items():
            if agent_info.chain_id == chain_id and agent_info.status == AgentStatus.ACTIVE:
                if capabilities:
                    # Check if agent has required capabilities
                    if any(cap in agent_info.capabilities for cap in capabilities):
                        agents.append(agent_info)
                else:
                    agents.append(agent_info)
        
        # Cache results
        self.discovery_cache[cache_key] = agents
        
        return agents
    
    async def send_message(self, message: AgentMessage) -> bool:
        """Send a message to an agent"""
        try:
            # Validate message
            if not self._validate_message(message):
                return False
            
            # Check if receiver exists
            if message.receiver_id not in self.agents:
                return False
            
            # Check receiver reputation
            receiver_reputation = self.reputations.get(message.receiver_id)
            if receiver_reputation and receiver_reputation.reputation_score < self.thresholds['min_reputation_score']:
                return False
            
            # Add message to queue
            self.message_queue[message.receiver_id].append(message)
            self.messages[message.message_id] = message
            
            # Attempt immediate delivery
            await self._deliver_message(message)
            
            return True
            
        except Exception as e:
            print(f"Error sending message {message.message_id}: {e}")
            return False
    
    async def _deliver_message(self, message: AgentMessage) -> bool:
        """Deliver a message to the target agent"""
        try:
            receiver = self.agents.get(message.receiver_id)
            if not receiver:
                return False
            
            # Check if receiver is on same chain
            if message.chain_id == receiver.chain_id:
                # Same chain delivery
                return await self._deliver_same_chain(message, receiver)
            else:
                # Cross-chain delivery
                return await self._deliver_cross_chain(message, receiver)
                
        except Exception as e:
            print(f"Error delivering message {message.message_id}: {e}")
            return False
    
    async def _deliver_same_chain(self, message: AgentMessage, receiver: AgentInfo) -> bool:
        """Deliver message on the same chain"""
        try:
            # Simulate message delivery
            print(f"Delivering message {message.message_id} to agent {receiver.agent_id} on chain {message.chain_id}")
            
            # Update agent status
            receiver.last_seen = datetime.now()
            self.agents[receiver.agent_id] = receiver
            
            # Remove from queue
            if message in self.message_queue[receiver.agent_id]:
                self.message_queue[receiver.agent_id].remove(message)
            
            return True
            
        except Exception as e:
            print(f"Error in same-chain delivery: {e}")
            return False
    
    async def _deliver_cross_chain(self, message: AgentMessage, receiver: AgentInfo) -> bool:
        """Deliver message across chains"""
        try:
            # Find bridge nodes
            bridge_nodes = await self._find_bridge_nodes(message.chain_id, receiver.chain_id)
            if not bridge_nodes:
                return False
            
            # Route through bridge nodes
            for bridge_node in bridge_nodes:
                try:
                    # Simulate cross-chain routing
                    print(f"Routing message {message.message_id} through bridge node {bridge_node}")
                    
                    # Update routing table
                    if message.chain_id not in self.routing_table:
                        self.routing_table[message.chain_id] = []
                    if receiver.chain_id not in self.routing_table[message.chain_id]:
                        self.routing_table[message.chain_id].append(receiver.chain_id)
                    
                    # Update agent status
                    receiver.last_seen = datetime.now()
                    self.agents[receiver.agent_id] = receiver
                    
                    # Remove from queue
                    if message in self.message_queue[receiver.agent_id]:
                        self.message_queue[receiver.agent_id].remove(message)
                    
                    return True
                    
                except Exception as e:
                    print(f"Error routing through bridge node {bridge_node}: {e}")
                    continue
            
            return False
            
        except Exception as e:
            print(f"Error in cross-chain delivery: {e}")
            return False
    
    async def create_collaboration(self, agent_ids: List[str], collaboration_type: str, governance_rules: Dict[str, Any]) -> Optional[str]:
        """Create a multi-agent collaboration"""
        try:
            # Validate collaboration
            if len(agent_ids) > self.thresholds['max_collaboration_size']:
                return None
            
            # Check if all agents exist and are active
            active_agents = []
            for agent_id in agent_ids:
                agent = self.agents.get(agent_id)
                if agent and agent.status == AgentStatus.ACTIVE:
                    active_agents.append(agent)
                else:
                    return None
            
            if len(active_agents) < 2:
                return None
            
            # Create collaboration
            collaboration_id = str(uuid.uuid4())
            chain_ids = list(set(agent.chain_id for agent in active_agents))
            
            collaboration = AgentCollaboration(
                collaboration_id=collaboration_id,
                agent_ids=agent_ids,
                chain_ids=chain_ids,
                collaboration_type=collaboration_type,
                status="active",
                created_at=datetime.now(),
                updated_at=datetime.now(),
                shared_resources={},
                governance_rules=governance_rules
            )
            
            self.collaborations[collaboration_id] = collaboration
            
            # Notify all agents
            for agent_id in agent_ids:
                notification = AgentMessage(
                    message_id=str(uuid.uuid4()),
                    sender_id="system",
                    receiver_id=agent_id,
                    message_type=MessageType.COLLABORATION,
                    chain_id=active_agents[0].chain_id,
                    target_chain_id=None,
                    payload={
                        "action": "collaboration_created",
                        "collaboration_id": collaboration_id,
                        "collaboration_type": collaboration_type,
                        "participants": agent_ids
                    },
                    timestamp=datetime.now(),
                    signature="system_notification",
                    priority=5,
                    ttl_seconds=3600
                )
                await self.send_message(notification)
            
            return collaboration_id
            
        except Exception as e:
            print(f"Error creating collaboration: {e}")
            return None
    
    async def update_reputation(self, agent_id: str, interaction_success: bool, feedback_score: Optional[float] = None) -> bool:
        """Update agent reputation"""
        try:
            reputation = self.reputations.get(agent_id)
            if not reputation:
                return False
            
            # Update interaction counts
            reputation.total_interactions += 1
            if interaction_success:
                reputation.successful_interactions += 1
            else:
                reputation.failed_interactions += 1
            
            # Add feedback score if provided
            if feedback_score is not None:
                reputation.feedback_scores.append(feedback_score)
                # Keep only last 50 feedback scores
                reputation.feedback_scores = reputation.feedback_scores[-50:]
            
            # Calculate new reputation score
            success_rate = reputation.successful_interactions / reputation.total_interactions
            feedback_avg = sum(reputation.feedback_scores) / len(reputation.feedback_scores) if reputation.feedback_scores else 0.5
            
            # Weighted average: 70% success rate, 30% feedback
            reputation.reputation_score = (success_rate * 0.7) + (feedback_avg * 0.3)
            reputation.last_updated = datetime.now()
            
            # Update agent info
            if agent_id in self.agents:
                self.agents[agent_id].reputation_score = reputation.reputation_score
            
            return True
            
        except Exception as e:
            print(f"Error updating reputation for agent {agent_id}: {e}")
            return False
    
    async def get_agent_status(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Get comprehensive agent status"""
        try:
            agent = self.agents.get(agent_id)
            if not agent:
                return None
            
            reputation = self.reputations.get(agent_id)
            
            # Get message queue status
            queue_size = len(self.message_queue.get(agent_id, []))
            
            # Get active collaborations
            active_collaborations = [
                collab for collab in self.collaborations.values()
                if agent_id in collab.agent_ids and collab.status == "active"
            ]
            
            status = {
                "agent_info": asdict(agent),
                "reputation": asdict(reputation) if reputation else None,
                "message_queue_size": queue_size,
                "active_collaborations": len(active_collaborations),
                "last_seen": agent.last_seen.isoformat(),
                "status": agent.status.value
            }
            
            return status
            
        except Exception as e:
            print(f"Error getting agent status for {agent_id}: {e}")
            return None
    
    async def get_network_overview(self) -> Dict[str, Any]:
        """Get cross-chain network overview"""
        try:
            # Count agents by chain
            agents_by_chain = defaultdict(int)
            active_agents_by_chain = defaultdict(int)
            
            for agent in self.agents.values():
                agents_by_chain[agent.chain_id] += 1
                if agent.status == AgentStatus.ACTIVE:
                    active_agents_by_chain[agent.chain_id] += 1
            
            # Count collaborations by type
            collaborations_by_type = defaultdict(int)
            active_collaborations = 0
            
            for collab in self.collaborations.values():
                collaborations_by_type[collab.collaboration_type] += 1
                if collab.status == "active":
                    active_collaborations += 1
            
            # Message statistics
            total_messages = len(self.messages)
            queued_messages = sum(len(queue) for queue in self.message_queue.values())
            
            # Reputation statistics
            reputation_scores = [rep.reputation_score for rep in self.reputations.values()]
            avg_reputation = sum(reputation_scores) / len(reputation_scores) if reputation_scores else 0
            
            overview = {
                "total_agents": len(self.agents),
                "active_agents": len([a for a in self.agents.values() if a.status == AgentStatus.ACTIVE]),
                "agents_by_chain": dict(agents_by_chain),
                "active_agents_by_chain": dict(active_agents_by_chain),
                "total_collaborations": len(self.collaborations),
                "active_collaborations": active_collaborations,
                "collaborations_by_type": dict(collaborations_by_type),
                "total_messages": total_messages,
                "queued_messages": queued_messages,
                "average_reputation": avg_reputation,
                "routing_table_size": len(self.routing_table),
                "discovery_cache_size": len(self.discovery_cache)
            }
            
            return overview
            
        except Exception as e:
            print(f"Error getting network overview: {e}")
            return {}
    
    def _validate_agent_info(self, agent_info: AgentInfo) -> bool:
        """Validate agent information"""
        if not agent_info.agent_id or not agent_info.chain_id:
            return False
        
        if agent_info.reputation_score < 0 or agent_info.reputation_score > 1:
            return False
        
        if not agent_info.capabilities:
            return False
        
        return True
    
    def _validate_message(self, message: AgentMessage) -> bool:
        """Validate message"""
        if not message.sender_id or not message.receiver_id:
            return False
        
        if message.ttl_seconds > self.thresholds['max_ttl_seconds']:
            return False
        
        if len(json.dumps(message.payload)) > self.thresholds['max_message_size']:
            return False
        
        return True
    
    def _update_routing_table(self, agent_info: AgentInfo):
        """Update routing table with agent information"""
        if agent_info.chain_id not in self.routing_table:
            self.routing_table[agent_info.chain_id] = []
        
        # Add agent to routing table
        if agent_info.agent_id not in self.routing_table[agent_info.chain_id]:
            self.routing_table[agent_info.chain_id].append(agent_info.agent_id)
    
    async def _find_bridge_nodes(self, source_chain: str, target_chain: str) -> List[str]:
        """Find bridge nodes for cross-chain communication"""
        # For now, return any node that has agents on both chains
        bridge_nodes = []
        
        for node_id, node_config in self.config.nodes.items():
            try:
                async with NodeClient(node_config) as client:
                    chains = await client.get_hosted_chains()
                    chain_ids = [chain.id for chain in chains]
                    
                    if source_chain in chain_ids and target_chain in chain_ids:
                        bridge_nodes.append(node_id)
            except Exception:
                continue
        
        return bridge_nodes
