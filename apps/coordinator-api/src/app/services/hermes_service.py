"""
Hermes Service - Agent-to-agent communication system

Provides:
- Direct agent messaging
- Broadcast messaging
- Message queuing
- Message encryption
- Delivery receipts
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from aitbc.aitbc_logging import get_logger


logger = get_logger(__name__)


class MessageType(Enum):
    """Types of agent messages"""
    direct = "direct"
    broadcast = "broadcast"
    request = "request"
    response = "response"
    system = "system"


class MessageStatus(Enum):
    """Message delivery status"""
    pending = "pending"
    sent = "sent"
    delivered = "delivered"
    read = "read"
    failed = "failed"


@dataclass
class AgentMessage:
    """Agent message structure"""
    id: str
    sender: str
    recipient: Optional[str]  # None for broadcasts
    message_type: MessageType
    content: str
    encrypted: bool
    timestamp: datetime
    status: MessageStatus
    
    # Optional fields
    reply_to: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    delivered_at: Optional[datetime] = None
    read_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "sender": self.sender,
            "recipient": self.recipient,
            "type": self.message_type.value,
            "content": self.content,
            "encrypted": self.encrypted,
            "timestamp": self.timestamp.isoformat(),
            "status": self.status.value,
            "reply_to": self.reply_to,
            "metadata": self.metadata,
            "delivered_at": self.delivered_at.isoformat() if self.delivered_at else None,
            "read_at": self.read_at.isoformat() if self.read_at else None
        }


@dataclass
class AgentProfile:
    """Agent communication profile"""
    agent_id: str
    public_key: str
    capabilities: List[str]
    last_seen: datetime
    online: bool
    message_queue: List[str] = field(default_factory=list)


class HermesService:
    """
    Hermes - Agent communication system.
    
    Named after the Greek messenger god, this service enables:
    - Secure agent-to-agent messaging
    - Broadcast communications
    - Message queuing for offline agents
    - Delivery tracking
    """
    
    def __init__(self):
        self._messages: Dict[str, AgentMessage] = {}
        self._agent_profiles: Dict[str, AgentProfile] = {}
        self._message_queues: Dict[str, List[str]] = {}  # agent_id -> message_ids
        self._message_counter = 0
    
    def register_agent(
        self,
        agent_id: str,
        public_key: str,
        capabilities: Optional[List[str]] = None
    ) -> AgentProfile:
        """Register an agent for communication"""
        profile = AgentProfile(
            agent_id=agent_id,
            public_key=public_key,
            capabilities=capabilities or [],
            last_seen=datetime.now(timezone.utc),
            online=True,
            message_queue=[]
        )
        
        self._agent_profiles[agent_id] = profile
        self._message_queues[agent_id] = []
        
        logger.info(f"Agent registered with Hermes: {agent_id}")
        
        return profile
    
    def send_message(
        self,
        sender: str,
        recipient: str,
        content: str,
        message_type: str = "direct",
        encrypted: bool = False,
        reply_to: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> AgentMessage:
        """
        Send a message from one agent to another.
        
        Args:
            sender: Sender agent ID
            recipient: Recipient agent ID
            content: Message content
            message_type: Type of message
            encrypted: Whether content is encrypted
            reply_to: Message ID this is replying to
            metadata: Additional metadata
        
        Returns:
            Created message
        """
        # Verify sender exists
        if sender not in self._agent_profiles:
            raise ValueError(f"Sender agent not registered: {sender}")
        
        # Verify recipient exists (for direct messages)
        if recipient and recipient not in self._agent_profiles:
            raise ValueError(f"Recipient agent not found: {recipient}")
        
        # Generate message ID
        self._message_counter += 1
        msg_id = f"MSG-{self._message_counter:08d}"
        
        # Parse message type
        try:
            msg_type = MessageType(message_type)
        except ValueError:
            msg_type = MessageType.direct
        
        # Create message
        message = AgentMessage(
            id=msg_id,
            sender=sender,
            recipient=recipient,
            message_type=msg_type,
            content=content,
            encrypted=encrypted,
            timestamp=datetime.now(timezone.utc),
            status=MessageStatus.sent,
            reply_to=reply_to,
            metadata=metadata or {}
        )
        
        self._messages[msg_id] = message
        
        # Queue for recipient if offline
        if recipient and recipient in self._message_queues:
            recipient_profile = self._agent_profiles[recipient]
            if not recipient_profile.online:
                self._message_queues[recipient].append(msg_id)
                message.status = MessageStatus.pending
            else:
                # Mark as delivered immediately if online
                message.status = MessageStatus.delivered
                message.delivered_at = datetime.now(timezone.utc)
        
        logger.info(f"Message sent: {msg_id} from {sender} to {recipient}")
        
        return message
    
    def broadcast(
        self,
        sender: str,
        content: str,
        encrypted: bool = False,
        metadata: Optional[Dict[str, Any]] = None
    ) -> List[AgentMessage]:
        """
        Broadcast a message to all registered agents.
        
        Args:
            sender: Sender agent ID
            content: Broadcast content
            encrypted: Whether encrypted
            metadata: Additional metadata
        
        Returns:
            List of created messages
        """
        messages = []
        
        for agent_id in self._agent_profiles:
            if agent_id != sender:  # Don't send to self
                try:
                    msg = self.send_message(
                        sender=sender,
                        recipient=agent_id,
                        content=content,
                        message_type="broadcast",
                        encrypted=encrypted,
                        metadata=metadata
                    )
                    messages.append(msg)
                except Exception as e:
                    logger.warning(f"Broadcast to {agent_id} failed: {e}")
        
        logger.info(f"Broadcast sent by {sender} to {len(messages)} agents")
        
        return messages
    
    def get_messages(
        self,
        agent_id: str,
        since: Optional[datetime] = None,
        message_type: Optional[str] = None,
        unread_only: bool = False
    ) -> List[AgentMessage]:
        """
        Get messages for an agent.
        
        Args:
            agent_id: Agent to get messages for
            since: Only messages after this time
            message_type: Filter by type
            unread_only: Only unread messages
        
        Returns:
            List of messages
        """
        if agent_id not in self._agent_profiles:
            raise ValueError(f"Agent not found: {agent_id}")
        
        # Update agent status
        profile = self._agent_profiles[agent_id]
        profile.last_seen = datetime.now(timezone.utc)
        profile.online = True
        
        # Get queued messages first
        queued_ids = self._message_queues.get(agent_id, [])
        messages = []
        
        for msg_id in queued_ids:
            if msg_id in self._messages:
                msg = self._messages[msg_id]
                # Mark as delivered
                if msg.status == MessageStatus.pending:
                    msg.status = MessageStatus.delivered
                    msg.delivered_at = datetime.now(timezone.utc)
                messages.append(msg)
        
        # Clear queue
        self._message_queues[agent_id] = []
        
        # Get all messages for this agent
        for msg in self._messages.values():
            if msg.recipient == agent_id and msg.id not in [m.id for m in messages]:
                messages.append(msg)
        
        # Apply filters
        if since:
            messages = [m for m in messages if m.timestamp >= since]
        
        if message_type:
            messages = [m for m in messages if m.message_type.value == message_type]
        
        if unread_only:
            messages = [m for m in messages if m.status != MessageStatus.read]
        
        # Sort by timestamp
        messages.sort(key=lambda m: m.timestamp, reverse=True)
        
        return messages
    
    def mark_read(self, agent_id: str, message_id: str) -> bool:
        """Mark a message as read"""
        if message_id not in self._messages:
            return False
        
        message = self._messages[message_id]
        
        # Verify agent is recipient
        if message.recipient != agent_id:
            return False
        
        message.status = MessageStatus.read
        message.read_at = datetime.now(timezone.utc)
        
        logger.info(f"Message {message_id} marked as read by {agent_id}")
        
        return True
    
    def get_agent_profile(self, agent_id: str) -> Optional[AgentProfile]:
        """Get agent profile"""
        return self._agent_profiles.get(agent_id)
    
    def list_agents(self, online_only: bool = False) -> List[AgentProfile]:
        """List registered agents"""
        agents = list(self._agent_profiles.values())
        
        if online_only:
            agents = [a for a in agents if a.online]
        
        return agents
    
    def update_agent_status(self, agent_id: str, online: bool) -> bool:
        """Update agent online status"""
        if agent_id not in self._agent_profiles:
            return False
        
        profile = self._agent_profiles[agent_id]
        profile.online = online
        profile.last_seen = datetime.now(timezone.utc)
        
        return True
    
    def get_message(self, message_id: str) -> Optional[AgentMessage]:
        """Get a specific message"""
        return self._messages.get(message_id)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get messaging statistics"""
        total_messages = len(self._messages)
        pending = len([m for m in self._messages.values() if m.status == MessageStatus.pending])
        delivered = len([m for m in self._messages.values() if m.status == MessageStatus.delivered])
        read = len([m for m in self._messages.values() if m.status == MessageStatus.read])
        
        online_agents = len([a for a in self._agent_profiles.values() if a.online])
        
        return {
            "total_messages": total_messages,
            "by_status": {
                "pending": pending,
                "delivered": delivered,
                "read": read
            },
            "registered_agents": len(self._agent_profiles),
            "online_agents": online_agents,
            "queued_messages": sum(len(q) for q in self._message_queues.values())
        }


# Global instance
_hermes_service: Optional[HermesService] = None


def get_hermes_service() -> HermesService:
    """Get global Hermes service"""
    global _hermes_service
    if _hermes_service is None:
        _hermes_service = HermesService()
    return _hermes_service
