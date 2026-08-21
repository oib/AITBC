"""
Multi-Agent Communication Protocols for AITBC Agent Coordination
"""

import asyncio
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from aitbc.aitbc_logging import get_logger

from ..websocket import get_connection_manager

logger = get_logger(__name__)


class MessageType(StrEnum):
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


class Priority(StrEnum):
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
    receiver_id: str | None = None
    message_type: MessageType = MessageType.DIRECT
    priority: Priority = Priority.NORMAL
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    payload: dict[str, Any] = field(default_factory=dict)
    correlation_id: str | None = None
    reply_to: str | None = None
    ttl: int = 300

    def to_dict(self) -> dict[str, Any]:
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
            "ttl": self.ttl,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentMessage":
        """Create message from dictionary"""
        data["timestamp"] = datetime.fromisoformat(data["timestamp"])
        data["message_type"] = MessageType(data["message_type"])
        data["priority"] = Priority(data["priority"])
        return cls(**data)


class CommunicationProtocol:
    """Base class for communication protocols"""

    def __init__(self, agent_id: str) -> None:
        self.agent_id = agent_id
        self.message_handlers: dict[MessageType, list[Callable[[AgentMessage], Any]]] = {}
        self.active_connections: dict[str, Any] = {}

    async def register_handler(self, message_type: MessageType, handler: Callable[[AgentMessage], Any]) -> None:
        """Register a message handler for a specific message type"""
        if message_type not in self.message_handlers:
            self.message_handlers[message_type] = []
        self.message_handlers[message_type].append(handler)

    async def send_message(self, message: AgentMessage) -> bool:
        """Send a message to another agent or broadcast to all connected agents."""
        try:
            if message.message_type == MessageType.BROADCAST and not message.receiver_id:
                return await self._broadcast_message(message)
            if message.receiver_id:
                return await self._send_to_agent(message)
            logger.warning("Cannot send message without receiver_id")
            return False
        except Exception as e:
            logger.error("Error sending message: %s", e)
            return False

    async def receive_message(self, message: AgentMessage) -> Any:
        """Process received message"""
        try:
            if self._is_message_expired(message):
                logger.warning("Message %s expired, ignoring", message.id)
                return
            handlers = self.message_handlers.get(message.message_type, [])
            for handler in handlers:
                try:
                    await handler(message)
                except Exception as e:
                    logger.error("Error in message handler: %s", e)
        except Exception as e:
            logger.error("Error processing message: %s", e)

    def _is_message_expired(self, message: AgentMessage) -> bool:
        """Check if message has expired"""
        age = (datetime.now(UTC) - message.timestamp).total_seconds()
        return age > message.ttl

    async def _send_to_agent(self, message: AgentMessage) -> bool:
        """Send message to a specific agent via the WebSocket ConnectionManager.

        If the recipient is not currently connected, the message is queued in
        the connection manager's in-memory inbox for delivery on reconnect.
        """
        if not message.receiver_id:
            logger.warning("Cannot send message without receiver_id")
            return False
        try:
            connection_manager = get_connection_manager()
            message_data = message.to_dict()
            delivered = await connection_manager.send_personal_message(message_data, message.receiver_id)
            if not delivered:
                if message.receiver_id not in connection_manager.agent_inboxes:
                    connection_manager.agent_inboxes[message.receiver_id] = []
                connection_manager.agent_inboxes[message.receiver_id].append(message_data)
                logger.info("Queued message for offline agent %s", message.receiver_id)
            return True
        except Exception as e:
            logger.error("Error sending message to %s: %s", message.receiver_id, e)
            return False

    async def _broadcast_message(self, message: AgentMessage) -> bool:
        """Broadcast message to all connected agents via the WebSocket ConnectionManager."""
        try:
            connection_manager = get_connection_manager()
            await connection_manager.broadcast(message.to_dict())
            return True
        except Exception as e:
            logger.error("Error broadcasting message: %s", e)
            return False


class HierarchicalProtocol(CommunicationProtocol):
    """Hierarchical communication protocol (master-agent → sub-agents)"""

    def __init__(self, agent_id: str, is_master: bool = False) -> None:
        super().__init__(agent_id)
        self.is_master = is_master
        self.sub_agents: list[str] = []
        self.master_agent: str | None = None

    async def add_sub_agent(self, agent_id: str) -> None:
        """Add a sub-agent to this master agent"""
        if self.is_master:
            self.sub_agents.append(agent_id)
            logger.info("Added sub-agent %s to master %s", agent_id, self.agent_id)
        else:
            logger.warning("Agent %s is not a master, cannot add sub-agents", self.agent_id)

    async def send_to_sub_agents(self, message: AgentMessage) -> None:
        """Send message to all sub-agents"""
        if not self.is_master:
            logger.warning("Agent %s is not a master", self.agent_id)
            return
        message.message_type = MessageType.HIERARCHICAL
        for sub_agent_id in self.sub_agents:
            message.receiver_id = sub_agent_id
            await self.send_message(message)

    async def send_to_master(self, message: AgentMessage) -> None:
        """Send message to master agent"""
        if self.is_master:
            logger.warning("Agent %s is a master, cannot send to master", self.agent_id)
            return
        if self.master_agent:
            message.receiver_id = self.master_agent
            message.message_type = MessageType.HIERARCHICAL
            await self.send_message(message)
        else:
            logger.warning("Agent %s has no master agent", self.agent_id)


class PeerToPeerProtocol(CommunicationProtocol):
    """Peer-to-peer communication protocol (agent ↔ agent)"""

    def __init__(self, agent_id: str) -> None:
        super().__init__(agent_id)
        self.peers: dict[str, dict[str, Any]] = {}

    async def add_peer(self, peer_id: str, connection_info: dict[str, Any]) -> None:
        """Add a peer to the peer network"""
        self.peers[peer_id] = connection_info
        logger.info("Added peer %s to agent %s", peer_id, self.agent_id)

    async def remove_peer(self, peer_id: str) -> None:
        """Remove a peer from the peer network"""
        if peer_id in self.peers:
            del self.peers[peer_id]
            logger.info("Removed peer %s from agent %s", peer_id, self.agent_id)

    async def send_to_peer(self, message: AgentMessage, peer_id: str) -> bool:
        """Send message to specific peer"""
        if peer_id not in self.peers:
            logger.warning("Peer %s not found", peer_id)
            return False
        message.receiver_id = peer_id
        message.message_type = MessageType.PEER_TO_PEER
        return await self.send_message(message)

    async def broadcast_to_peers(self, message: AgentMessage) -> None:
        """Broadcast message to all peers"""
        message.message_type = MessageType.PEER_TO_PEER
        for peer_id in self.peers:
            message.receiver_id = peer_id
            await self.send_message(message)


class BroadcastProtocol(CommunicationProtocol):
    """Broadcast communication protocol (agent → all agents)"""

    def __init__(self, agent_id: str, broadcast_channel: str = "global") -> None:
        super().__init__(agent_id)
        self.broadcast_channel = broadcast_channel
        self.subscribers: list[str] = []

    async def subscribe(self, agent_id: str) -> None:
        """Subscribe to broadcast channel"""
        if agent_id not in self.subscribers:
            self.subscribers.append(agent_id)
            logger.info("Agent %s subscribed to %s", agent_id, self.broadcast_channel)

    async def unsubscribe(self, agent_id: str) -> None:
        """Unsubscribe from broadcast channel"""
        if agent_id in self.subscribers:
            self.subscribers.remove(agent_id)
            logger.info("Agent %s unsubscribed from %s", agent_id, self.broadcast_channel)

    async def broadcast(self, message: AgentMessage) -> None:
        """Broadcast message to all subscribers"""
        message.message_type = MessageType.BROADCAST
        message.receiver_id = None
        for subscriber_id in self.subscribers:
            if subscriber_id != self.agent_id:
                message_copy = AgentMessage(**message.__dict__)
                message_copy.receiver_id = subscriber_id
                await self.send_message(message_copy)


class CommunicationManager:
    """Manages multiple communication protocols for an agent"""

    def __init__(self, agent_id: str) -> None:
        self.agent_id = agent_id
        self.protocols: dict[str, CommunicationProtocol] = {}

    def add_protocol(self, name: str, protocol: CommunicationProtocol) -> None:
        """Add a communication protocol"""
        self.protocols[name] = protocol
        logger.info("Added protocol %s to agent %s", name, self.agent_id)

    def get_protocol(self, name: str) -> CommunicationProtocol | None:
        """Get a communication protocol by name"""
        return self.protocols.get(name)

    async def send_message(self, protocol_name: str, message: AgentMessage) -> bool:
        """Send message using specific protocol"""
        protocol = self.get_protocol(protocol_name)
        if protocol:
            return await protocol.send_message(message)
        return False

    async def register_handler(
        self, protocol_name: str, message_type: MessageType, handler: Callable[[AgentMessage], Any]
    ) -> None:
        """Register message handler for specific protocol"""
        protocol = self.get_protocol(protocol_name)
        if protocol:
            await protocol.register_handler(message_type, handler)
        else:
            logger.error("Protocol %s not found", protocol_name)


class MessageTemplates:
    """Pre-defined message templates"""

    @staticmethod
    def create_heartbeat(sender_id: str) -> AgentMessage:
        """Create heartbeat message"""
        return AgentMessage(
            sender_id=sender_id,
            message_type=MessageType.HEARTBEAT,
            priority=Priority.LOW,
            payload={"timestamp": datetime.now(UTC).isoformat()},
        )

    @staticmethod
    def create_task_assignment(sender_id: str, receiver_id: str, task_data: dict[str, Any]) -> AgentMessage:
        """Create task assignment message"""
        return AgentMessage(
            sender_id=sender_id,
            receiver_id=receiver_id,
            message_type=MessageType.TASK_ASSIGNMENT,
            priority=Priority.NORMAL,
            payload=task_data,
        )

    @staticmethod
    def create_status_update(sender_id: str, status_data: dict[str, Any]) -> AgentMessage:
        """Create status update message"""
        return AgentMessage(
            sender_id=sender_id, message_type=MessageType.STATUS_UPDATE, priority=Priority.NORMAL, payload=status_data
        )

    @staticmethod
    def create_discovery(sender_id: str) -> AgentMessage:
        """Create discovery message"""
        return AgentMessage(
            sender_id=sender_id, message_type=MessageType.DISCOVERY, priority=Priority.NORMAL, payload={"agent_id": sender_id}
        )

    @staticmethod
    def create_consensus_request(sender_id: str, proposal_data: dict[str, Any]) -> AgentMessage:
        """Create consensus request message"""
        return AgentMessage(
            sender_id=sender_id, message_type=MessageType.CONSENSUS, priority=Priority.HIGH, payload=proposal_data
        )


def create_protocol(protocol_type: str, agent_id: str, **kwargs: Any) -> CommunicationProtocol:
    """Factory function to create communication protocols"""
    if protocol_type == "hierarchical":
        return HierarchicalProtocol(agent_id, kwargs.get("is_master", False))
    elif protocol_type == "peer_to_peer":
        return PeerToPeerProtocol(agent_id)
    elif protocol_type == "broadcast":
        return BroadcastProtocol(agent_id, kwargs.get("broadcast_channel", "global"))
    else:
        raise ValueError(f"Unknown protocol type: {protocol_type}")


async def example_usage() -> Any:
    """Example of how to use the communication protocols"""
    comm_manager = CommunicationManager("agent-001")
    hierarchical_protocol = create_protocol("hierarchical", "agent-001", is_master=True)
    p2p_protocol = create_protocol("peer_to_peer", "agent-001")
    broadcast_protocol = create_protocol("broadcast", "agent-001")
    comm_manager.add_protocol("hierarchical", hierarchical_protocol)
    comm_manager.add_protocol("peer_to_peer", p2p_protocol)
    comm_manager.add_protocol("broadcast", broadcast_protocol)

    async def handle_heartbeat(message: AgentMessage) -> Any:
        logger.info("Received heartbeat from %s", message.sender_id)

    await comm_manager.register_handler("hierarchical", MessageType.HEARTBEAT, handle_heartbeat)
    heartbeat = MessageTemplates.create_heartbeat("agent-001")
    await comm_manager.send_message("hierarchical", heartbeat)


if __name__ == "__main__":
    asyncio.run(example_usage())
