"""
Multi-Agent Communication Protocols for AITBC Agent Coordination
"""

import asyncio
import json
from enum import Enum
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from datetime import datetime
import uuid
from pydantic import BaseModel, Field

from aitbc import get_logger

logger = get_logger(__name__)

class MessageType(str, Enum):
    """Message types for agent communication"""
    COORDINATION = "coordination"
    TASK_ASSIGNMENT = "task_assignment"
    STATUS_UPDATE = "status_update"
    DISCOVERY = "discovery"
    HEARTBEAT = "heartbeat"
    CONSENSUS = "consensus"
    BROADCAST = "broadcast"
    DIRECT = "direct"
    PEER_TO_PEER = "peer_to_peer"
    HIERARCHICAL = "hierarchical"

class Priority(str, Enum):
    """Message priority levels"""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"

@dataclass
class AgentMessage:
    """Base message structure for agent communication"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    sender_id: str = ""
    receiver_id: Optional[str] = None
    message_type: MessageType = MessageType.DIRECT
    priority: Priority = Priority.NORMAL
    timestamp: datetime = field(default_factory=datetime.utcnow)
    payload: Dict[str, Any] = field(default_factory=dict)
    correlation_id: Optional[str] = None
    reply_to: Optional[str] = None
    ttl: int = 300  # Time to live in seconds
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert message to dictionary"""
        return {
            "id": self.id,
            "sender_id": self.sender_id,
            "receiver_id": self.receiver_id,
            "message_type": self.message_type.value,
            "priority": self.priority.value,
            "timestamp": self.timestamp.isoformat(),
            "payload": self.payload,
            "correlation_id": self.correlation_id,
            "reply_to": self.reply_to,
            "ttl": self.ttl
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentMessage":
        """Create message from dictionary"""
        data["timestamp"] = datetime.fromisoformat(data["timestamp"])
        data["message_type"] = MessageType(data["message_type"])
        data["priority"] = Priority(data["priority"])
        return cls(**data)

class CommunicationProtocol:
    """Base class for communication protocols"""
    
    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.message_handlers: Dict[MessageType, List[Callable]] = {}
        self.active_connections: Dict[str, Any] = {}
        
    async def register_handler(self, message_type: MessageType, handler: Callable):
        """Register a message handler for a specific message type"""
        if message_type not in self.message_handlers:
            self.message_handlers[message_type] = []
        self.message_handlers[message_type].append(handler)
        
    async def send_message(self, message: AgentMessage) -> bool:
        """Send a message to another agent"""
        try:
            if message.receiver_id and message.receiver_id in self.active_connections:
                await self._send_to_agent(message)
                return True
            elif message.message_type == MessageType.BROADCAST:
                await self._broadcast_message(message)
                return True
            else:
                logger.warning(f"Cannot send message to {message.receiver_id}: not connected")
                return False
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            return False
    
    async def receive_message(self, message: AgentMessage):
        """Process received message"""
        try:
            # Check TTL
            if self._is_message_expired(message):
                logger.warning(f"Message {message.id} expired, ignoring")
                return
                
            # Handle message
            handlers = self.message_handlers.get(message.message_type, [])
            for handler in handlers:
                try:
                    await handler(message)
                except Exception as e:
                    logger.error(f"Error in message handler: {e}")
                    
        except Exception as e:
            logger.error(f"Error processing message: {e}")
    
    def _is_message_expired(self, message: AgentMessage) -> bool:
        """Check if message has expired"""
        age = (datetime.utcnow() - message.timestamp).total_seconds()
        return age > message.ttl
    
    async def _send_to_agent(self, message: AgentMessage):
        """Send message to specific agent"""
        raise NotImplementedError("Subclasses must implement _send_to_agent")
    
    async def _broadcast_message(self, message: AgentMessage):
        """Broadcast message to all connected agents"""
        raise NotImplementedError("Subclasses must implement _broadcast_message")

class HierarchicalProtocol(CommunicationProtocol):
    """Hierarchical communication protocol (master-agent → sub-agents)"""
    
    def __init__(self, agent_id: str, is_master: bool = False):
        super().__init__(agent_id)
        self.is_master = is_master
        self.sub_agents: List[str] = []
        self.master_agent: Optional[str] = None
        
    async def add_sub_agent(self, agent_id: str):
        """Add a sub-agent to this master agent"""
        if self.is_master:
            self.sub_agents.append(agent_id)
            logger.info(f"Added sub-agent {agent_id} to master {self.agent_id}")
        else:
            logger.warning(f"Agent {self.agent_id} is not a master, cannot add sub-agents")
    
    async def send_to_sub_agents(self, message: AgentMessage):
        """Send message to all sub-agents"""
        if not self.is_master:
            logger.warning(f"Agent {self.agent_id} is not a master")
            return
            
        message.message_type = MessageType.HIERARCHICAL
        for sub_agent_id in self.sub_agents:
            message.receiver_id = sub_agent_id
            await self.send_message(message)
    
    async def send_to_master(self, message: AgentMessage):
        """Send message to master agent"""
        if self.is_master:
            logger.warning(f"Agent {self.agent_id} is a master, cannot send to master")
            return
            
        if self.master_agent:
            message.receiver_id = self.master_agent
            message.message_type = MessageType.HIERARCHICAL
            await self.send_message(message)
        else:
            logger.warning(f"Agent {self.agent_id} has no master agent")

class PeerToPeerProtocol(CommunicationProtocol):
    """Peer-to-peer communication protocol (agent ↔ agent)"""
    
    def __init__(self, agent_id: str):
        super().__init__(agent_id)
        self.peers: Dict[str, Dict[str, Any]] = {}
        
    async def add_peer(self, peer_id: str, connection_info: Dict[str, Any]):
        """Add a peer to the peer network"""
        self.peers[peer_id] = connection_info
        logger.info(f"Added peer {peer_id} to agent {self.agent_id}")
    
    async def remove_peer(self, peer_id: str):
        """Remove a peer from the peer network"""
        if peer_id in self.peers:
            del self.peers[peer_id]
            logger.info(f"Removed peer {peer_id} from agent {self.agent_id}")
    
    async def send_to_peer(self, message: AgentMessage, peer_id: str):
        """Send message to specific peer"""
        if peer_id not in self.peers:
            logger.warning(f"Peer {peer_id} not found")
            return False
            
        message.receiver_id = peer_id
        message.message_type = MessageType.PEER_TO_PEER
        return await self.send_message(message)
    
    async def broadcast_to_peers(self, message: AgentMessage):
        """Broadcast message to all peers"""
        message.message_type = MessageType.PEER_TO_PEER
        for peer_id in self.peers:
            message.receiver_id = peer_id
            await self.send_message(message)

class BroadcastProtocol(CommunicationProtocol):
    """Broadcast communication protocol (agent → all agents)"""
    
    def __init__(self, agent_id: str, broadcast_channel: str = "global"):
        super().__init__(agent_id)
        self.broadcast_channel = broadcast_channel
        self.subscribers: List[str] = []
        
    async def subscribe(self, agent_id: str):
        """Subscribe to broadcast channel"""
        if agent_id not in self.subscribers:
            self.subscribers.append(agent_id)
            logger.info(f"Agent {agent_id} subscribed to {self.broadcast_channel}")
    
    async def unsubscribe(self, agent_id: str):
        """Unsubscribe from broadcast channel"""
        if agent_id in self.subscribers:
            self.subscribers.remove(agent_id)
            logger.info(f"Agent {agent_id} unsubscribed from {self.broadcast_channel}")
    
    async def broadcast(self, message: AgentMessage):
        """Broadcast message to all subscribers"""
        message.message_type = MessageType.BROADCAST
        message.receiver_id = None  # Broadcast to all
        
        for subscriber_id in self.subscribers:
            if subscriber_id != self.agent_id:  # Don't send to self
                message_copy = AgentMessage(**message.__dict__)
                message_copy.receiver_id = subscriber_id
                await self.send_message(message_copy)

class CommunicationManager:
    """Manages multiple communication protocols for an agent"""
    
    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.protocols: Dict[str, CommunicationProtocol] = {}
        
    def add_protocol(self, name: str, protocol: CommunicationProtocol):
        """Add a communication protocol"""
        self.protocols[name] = protocol
        logger.info(f"Added protocol {name} to agent {self.agent_id}")
    
    def get_protocol(self, name: str) -> Optional[CommunicationProtocol]:
        """Get a communication protocol by name"""
        return self.protocols.get(name)
    
    async def send_message(self, protocol_name: str, message: AgentMessage) -> bool:
        """Send message using specific protocol"""
        protocol = self.get_protocol(protocol_name)
        if protocol:
            return await protocol.send_message(message)
        return False
    
    async def register_handler(self, protocol_name: str, message_type: MessageType, handler: Callable):
        """Register message handler for specific protocol"""
        protocol = self.get_protocol(protocol_name)
        if protocol:
            await protocol.register_handler(message_type, handler)
        else:
            logger.error(f"Protocol {protocol_name} not found")

# Message templates for common operations
class MessageTemplates:
    """Pre-defined message templates"""
    
    @staticmethod
    def create_heartbeat(sender_id: str) -> AgentMessage:
        """Create heartbeat message"""
        return AgentMessage(
            sender_id=sender_id,
            message_type=MessageType.HEARTBEAT,
            priority=Priority.LOW,
            payload={"timestamp": datetime.utcnow().isoformat()}
        )
    
    @staticmethod
    def create_task_assignment(sender_id: str, receiver_id: str, task_data: Dict[str, Any]) -> AgentMessage:
        """Create task assignment message"""
        return AgentMessage(
            sender_id=sender_id,
            receiver_id=receiver_id,
            message_type=MessageType.TASK_ASSIGNMENT,
            priority=Priority.NORMAL,
            payload=task_data
        )
    
    @staticmethod
    def create_status_update(sender_id: str, status_data: Dict[str, Any]) -> AgentMessage:
        """Create status update message"""
        return AgentMessage(
            sender_id=sender_id,
            message_type=MessageType.STATUS_UPDATE,
            priority=Priority.NORMAL,
            payload=status_data
        )
    
    @staticmethod
    def create_discovery(sender_id: str) -> AgentMessage:
        """Create discovery message"""
        return AgentMessage(
            sender_id=sender_id,
            message_type=MessageType.DISCOVERY,
            priority=Priority.NORMAL,
            payload={"agent_id": sender_id}
        )
    
    @staticmethod
    def create_consensus_request(sender_id: str, proposal_data: Dict[str, Any]) -> AgentMessage:
        """Create consensus request message"""
        return AgentMessage(
            sender_id=sender_id,
            message_type=MessageType.CONSENSUS,
            priority=Priority.HIGH,
            payload=proposal_data
        )

# WebSocket connection handler for real-time communication
class WebSocketHandler:
    """WebSocket handler for real-time agent communication"""
    
    def __init__(self, communication_manager: CommunicationManager):
        self.communication_manager = communication_manager
        self.websocket_connections: Dict[str, Any] = {}
        
    async def handle_connection(self, websocket, agent_id: str):
        """Handle WebSocket connection from agent"""
        import websockets

        self.websocket_connections[agent_id] = websocket
        logger.info(f"WebSocket connection established for agent {agent_id}")
        
        try:
            async for message in websocket:
                data = json.loads(message)
                agent_message = AgentMessage.from_dict(data)
                await self.communication_manager.receive_message(agent_message)
        except websockets.exceptions.ConnectionClosed:
            logger.info(f"WebSocket connection closed for agent {agent_id}")
        finally:
            if agent_id in self.websocket_connections:
                del self.websocket_connections[agent_id]
    
    async def send_to_agent(self, agent_id: str, message: AgentMessage):
        """Send message to agent via WebSocket"""
        if agent_id in self.websocket_connections:
            websocket = self.websocket_connections[agent_id]
            await websocket.send(json.dumps(message.to_dict()))
            return True
        return False
    
    async def broadcast_message(self, message: AgentMessage):
        """Broadcast message to all connected agents"""
        for websocket in self.websocket_connections.values():
            await websocket.send(json.dumps(message.to_dict()))

# Redis-based message broker for scalable communication
class RedisMessageBroker:
    """Redis-based message broker for agent communication"""
    
    def __init__(self, redis_url: str):
        self.redis_url = redis_url
        self.channels: Dict[str, Any] = {}
        
    async def publish_message(self, channel: str, message: AgentMessage):
        """Publish message to Redis channel"""
        import redis.asyncio as redis
        redis_client = redis.from_url(self.redis_url)
        
        await redis_client.publish(channel, json.dumps(message.to_dict()))
        await redis_client.close()
    
    async def subscribe_to_channel(self, channel: str, handler: Callable):
        """Subscribe to Redis channel"""
        import redis.asyncio as redis
        redis_client = redis.from_url(self.redis_url)
        
        pubsub = redis_client.pubsub()
        await pubsub.subscribe(channel)
        
        self.channels[channel] = {"pubsub": pubsub, "handler": handler}
        
        # Start listening for messages
        asyncio.create_task(self._listen_to_channel(channel, pubsub, handler))
    
    async def _listen_to_channel(self, channel: str, pubsub: Any, handler: Callable):
        """Listen for messages on channel"""
        async for message in pubsub.listen():
            if message["type"] == "message":
                data = json.loads(message["data"])
                agent_message = AgentMessage.from_dict(data)
                await handler(agent_message)

# Factory function for creating communication protocols
def create_protocol(protocol_type: str, agent_id: str, **kwargs) -> CommunicationProtocol:
    """Factory function to create communication protocols"""
    if protocol_type == "hierarchical":
        return HierarchicalProtocol(agent_id, kwargs.get("is_master", False))
    elif protocol_type == "peer_to_peer":
        return PeerToPeerProtocol(agent_id)
    elif protocol_type == "broadcast":
        return BroadcastProtocol(agent_id, kwargs.get("broadcast_channel", "global"))
    else:
        raise ValueError(f"Unknown protocol type: {protocol_type}")

# Example usage
async def example_usage():
    """Example of how to use the communication protocols"""
    
    # Create communication manager
    comm_manager = CommunicationManager("agent-001")
    
    # Add protocols
    hierarchical_protocol = create_protocol("hierarchical", "agent-001", is_master=True)
    p2p_protocol = create_protocol("peer_to_peer", "agent-001")
    broadcast_protocol = create_protocol("broadcast", "agent-001")
    
    comm_manager.add_protocol("hierarchical", hierarchical_protocol)
    comm_manager.add_protocol("peer_to_peer", p2p_protocol)
    comm_manager.add_protocol("broadcast", broadcast_protocol)
    
    # Register message handlers
    async def handle_heartbeat(message: AgentMessage):
        logger.info(f"Received heartbeat from {message.sender_id}")
    
    await comm_manager.register_handler("hierarchical", MessageType.HEARTBEAT, handle_heartbeat)
    
    # Send messages
    heartbeat = MessageTemplates.create_heartbeat("agent-001")
    await comm_manager.send_message("hierarchical", heartbeat)

if __name__ == "__main__":
    asyncio.run(example_usage())
