"""
Agent Communication Service for Advanced Agent Features
Implements secure agent-to-agent messaging with reputation-based access control
"""

import asyncio
import logging
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
from enum import Enum
import json
import hashlib
import base64
from dataclasses import dataclass, asdict, field

from .cross_chain_reputation import CrossChainReputationService, ReputationTier

logger = logging.getLogger(__name__)


class MessageType(str, Enum):
    """Types of agent messages"""
    TEXT = "text"
    DATA = "data"
    TASK_REQUEST = "task_request"
    TASK_RESPONSE = "task_response"
    COLLABORATION = "collaboration"
    NOTIFICATION = "notification"
    SYSTEM = "system"
    URGENT = "urgent"
    BULK = "bulk"


class ChannelType(str, Enum):
    """Types of communication channels"""
    DIRECT = "direct"
    GROUP = "group"
    BROADCAST = "broadcast"
    PRIVATE = "private"


class MessageStatus(str, Enum):
    """Message delivery status"""
    PENDING = "pending"
    DELIVERED = "delivered"
    READ = "read"
    FAILED = "failed"
    EXPIRED = "expired"


class EncryptionType(str, Enum):
    """Encryption types for messages"""
    AES256 = "aes256"
    RSA = "rsa"
    HYBRID = "hybrid"
    NONE = "none"


@dataclass
class Message:
    """Agent message data"""
    id: str
    sender: str
    recipient: str
    message_type: MessageType
    content: bytes
    encryption_key: bytes
    encryption_type: EncryptionType
    size: int
    timestamp: datetime
    delivery_timestamp: Optional[datetime] = None
    read_timestamp: Optional[datetime] = None
    status: MessageStatus = MessageStatus.PENDING
    paid: bool = False
    price: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    expires_at: Optional[datetime] = None
    reply_to: Optional[str] = None
    thread_id: Optional[str] = None


@dataclass
class CommunicationChannel:
    """Communication channel between agents"""
    id: str
    agent1: str
    agent2: str
    channel_type: ChannelType
    is_active: bool
    created_timestamp: datetime
    last_activity: datetime
    message_count: int
    participants: List[str] = field(default_factory=list)
    encryption_enabled: bool = True
    auto_delete: bool = False
    retention_period: int = 2592000  # 30 days


@dataclass
class MessageTemplate:
    """Message template for common communications"""
    id: str
    name: str
    description: str
    message_type: MessageType
    content_template: str
    variables: List[str]
    base_price: float
    is_active: bool
    creator: str
    usage_count: int = 0


@dataclass
class CommunicationStats:
    """Communication statistics for agent"""
    total_messages: int
    total_earnings: float
    messages_sent: int
    messages_received: int
    active_channels: int
    last_activity: datetime
    average_response_time: float
    delivery_rate: float


class AgentCommunicationService:
    """Service for managing agent-to-agent communication"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.messages: Dict[str, Message] = {}
        self.channels: Dict[str, CommunicationChannel] = {}
        self.message_templates: Dict[str, MessageTemplate] = {}
        self.agent_messages: Dict[str, List[str]] = {}
        self.agent_channels: Dict[str, List[str]] = {}
        self.communication_stats: Dict[str, CommunicationStats] = {}
        
        # Services
        self.reputation_service: Optional[CrossChainReputationService] = None
        
        # Configuration
        self.min_reputation_score = 1000
        self.base_message_price = 0.001  # AITBC
        self.max_message_size = 100000  # 100KB
        self.message_timeout = 86400  # 24 hours
        self.channel_timeout = 2592000  # 30 days
        self.encryption_enabled = True
        
        # Access control
        self.authorized_agents: Dict[str, bool] = {}
        self.contact_lists: Dict[str, Dict[str, bool]] = {}
        self.blocked_lists: Dict[str, Dict[str, bool]] = {}
        
        # Message routing
        self.message_queue: List[Message] = []
        self.delivery_attempts: Dict[str, int] = {}
        
        # Templates
        self._initialize_default_templates()
    
    def set_reputation_service(self, reputation_service: CrossChainReputationService):
        """Set reputation service for access control"""
        self.reputation_service = reputation_service
    
    async def initialize(self):
        """Initialize the agent communication service"""
        logger.info("Initializing Agent Communication Service")
        
        # Load existing data
        await self._load_communication_data()
        
        # Start background tasks
        asyncio.create_task(self._process_message_queue())
        asyncio.create_task(self._cleanup_expired_messages())
        asyncio.create_task(self._cleanup_inactive_channels())
        
        logger.info("Agent Communication Service initialized")
    
    async def authorize_agent(self, agent_id: str) -> bool:
        """Authorize an agent to use the communication system"""
        
        try:
            self.authorized_agents[agent_id] = True
            
            # Initialize communication stats
            if agent_id not in self.communication_stats:
                self.communication_stats[agent_id] = CommunicationStats(
                    total_messages=0,
                    total_earnings=0.0,
                    messages_sent=0,
                    messages_received=0,
                    active_channels=0,
                    last_activity=datetime.utcnow(),
                    average_response_time=0.0,
                    delivery_rate=0.0
                )
            
            logger.info(f"Authorized agent: {agent_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to authorize agent {agent_id}: {e}")
            return False
    
    async def revoke_agent(self, agent_id: str) -> bool:
        """Revoke agent authorization"""
        
        try:
            self.authorized_agents[agent_id] = False
            
            # Clean up agent data
            if agent_id in self.agent_messages:
                del self.agent_messages[agent_id]
            if agent_id in self.agent_channels:
                del self.agent_channels[agent_id]
            if agent_id in self.communication_stats:
                del self.communication_stats[agent_id]
            
            logger.info(f"Revoked authorization for agent: {agent_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to revoke agent {agent_id}: {e}")
            return False
    
    async def add_contact(self, agent_id: str, contact_id: str) -> bool:
        """Add contact to agent's contact list"""
        
        try:
            if agent_id not in self.contact_lists:
                self.contact_lists[agent_id] = {}
            
            self.contact_lists[agent_id][contact_id] = True
            
            # Remove from blocked list if present
            if agent_id in self.blocked_lists and contact_id in self.blocked_lists[agent_id]:
                del self.blocked_lists[agent_id][contact_id]
            
            logger.info(f"Added contact {contact_id} for agent {agent_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to add contact: {e}")
            return False
    
    async def remove_contact(self, agent_id: str, contact_id: str) -> bool:
        """Remove contact from agent's contact list"""
        
        try:
            if agent_id in self.contact_lists and contact_id in self.contact_lists[agent_id]:
                del self.contact_lists[agent_id][contact_id]
            
            logger.info(f"Removed contact {contact_id} for agent {agent_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to remove contact: {e}")
            return False
    
    async def block_agent(self, agent_id: str, blocked_id: str) -> bool:
        """Block an agent"""
        
        try:
            if agent_id not in self.blocked_lists:
                self.blocked_lists[agent_id] = {}
            
            self.blocked_lists[agent_id][blocked_id] = True
            
            # Remove from contact list if present
            if agent_id in self.contact_lists and blocked_id in self.contact_lists[agent_id]:
                del self.contact_lists[agent_id][blocked_id]
            
            logger.info(f"Blocked agent {blocked_id} for agent {agent_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to block agent: {e}")
            return False
    
    async def unblock_agent(self, agent_id: str, blocked_id: str) -> bool:
        """Unblock an agent"""
        
        try:
            if agent_id in self.blocked_lists and blocked_id in self.blocked_lists[agent_id]:
                del self.blocked_lists[agent_id][blocked_id]
            
            logger.info(f"Unblocked agent {blocked_id} for agent {agent_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to unblock agent: {e}")
            return False
    
    async def send_message(
        self,
        sender: str,
        recipient: str,
        message_type: MessageType,
        content: str,
        encryption_type: EncryptionType = EncryptionType.AES256,
        metadata: Optional[Dict[str, Any]] = None,
        reply_to: Optional[str] = None,
        thread_id: Optional[str] = None
    ) -> str:
        """Send a message to another agent"""
        
        try:
            # Validate authorization
            if not await self._can_send_message(sender, recipient):
                raise PermissionError("Not authorized to send message")
            
            # Validate content
            content_bytes = content.encode('utf-8')
            if len(content_bytes) > self.max_message_size:
                raise ValueError(f"Message too large: {len(content_bytes)} > {self.max_message_size}")
            
            # Generate message ID
            message_id = await self._generate_message_id()
            
            # Encrypt content
            if encryption_type != EncryptionType.NONE:
                encrypted_content, encryption_key = await self._encrypt_content(content_bytes, encryption_type)
            else:
                encrypted_content = content_bytes
                encryption_key = b''
            
            # Calculate price
            price = await self._calculate_message_price(len(content_bytes), message_type)
            
            # Create message
            message = Message(
                id=message_id,
                sender=sender,
                recipient=recipient,
                message_type=message_type,
                content=encrypted_content,
                encryption_key=encryption_key,
                encryption_type=encryption_type,
                size=len(content_bytes),
                timestamp=datetime.utcnow(),
                status=MessageStatus.PENDING,
                price=price,
                metadata=metadata or {},
                expires_at=datetime.utcnow() + timedelta(seconds=self.message_timeout),
                reply_to=reply_to,
                thread_id=thread_id
            )
            
            # Store message
            self.messages[message_id] = message
            
            # Update message lists
            if sender not in self.agent_messages:
                self.agent_messages[sender] = []
            if recipient not in self.agent_messages:
                self.agent_messages[recipient] = []
            
            self.agent_messages[sender].append(message_id)
            self.agent_messages[recipient].append(message_id)
            
            # Update stats
            await self._update_message_stats(sender, recipient, 'sent')
            
            # Create or update channel
            await self._get_or_create_channel(sender, recipient, ChannelType.DIRECT)
            
            # Add to queue for delivery
            self.message_queue.append(message)
            
            logger.info(f"Message sent from {sender} to {recipient}: {message_id}")
            return message_id
            
        except Exception as e:
            logger.error(f"Failed to send message: {e}")
            raise
    
    async def deliver_message(self, message_id: str) -> bool:
        """Mark message as delivered"""
        
        try:
            if message_id not in self.messages:
                raise ValueError(f"Message {message_id} not found")
            
            message = self.messages[message_id]
            if message.status != MessageStatus.PENDING:
                raise ValueError(f"Message {message_id} not pending")
            
            message.status = MessageStatus.DELIVERED
            message.delivery_timestamp = datetime.utcnow()
            
            # Update stats
            await self._update_message_stats(message.sender, message.recipient, 'delivered')
            
            logger.info(f"Message delivered: {message_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to deliver message {message_id}: {e}")
            return False
    
    async def read_message(self, message_id: str, reader: str) -> Optional[str]:
        """Mark message as read and return decrypted content"""
        
        try:
            if message_id not in self.messages:
                raise ValueError(f"Message {message_id} not found")
            
            message = self.messages[message_id]
            if message.recipient != reader:
                raise PermissionError("Not message recipient")
            
            if message.status != MessageStatus.DELIVERED:
                raise ValueError("Message not delivered")
            
            if message.read:
                raise ValueError("Message already read")
            
            # Mark as read
            message.status = MessageStatus.READ
            message.read_timestamp = datetime.utcnow()
            
            # Update stats
            await self._update_message_stats(message.sender, message.recipient, 'read')
            
            # Decrypt content
            if message.encryption_type != EncryptionType.NONE:
                decrypted_content = await self._decrypt_content(message.content, message.encryption_key, message.encryption_type)
                return decrypted_content.decode('utf-8')
            else:
                return message.content.decode('utf-8')
            
        except Exception as e:
            logger.error(f"Failed to read message {message_id}: {e}")
            return None
    
    async def pay_for_message(self, message_id: str, payer: str, amount: float) -> bool:
        """Pay for a message"""
        
        try:
            if message_id not in self.messages:
                raise ValueError(f"Message {message_id} not found")
            
            message = self.messages[message_id]
            
            if amount < message.price:
                raise ValueError(f"Insufficient payment: {amount} < {message.price}")
            
            # Process payment (simplified)
            # In production, implement actual payment processing
            
            message.paid = True
            
            # Update sender's earnings
            if message.sender in self.communication_stats:
                self.communication_stats[message.sender].total_earnings += message.price
            
            logger.info(f"Payment processed for message {message_id}: {amount}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to process payment for message {message_id}: {e}")
            return False
    
    async def create_channel(
        self,
        agent1: str,
        agent2: str,
        channel_type: ChannelType = ChannelType.DIRECT,
        encryption_enabled: bool = True
    ) -> str:
        """Create a communication channel"""
        
        try:
            # Validate agents
            if not self.authorized_agents.get(agent1, False) or not self.authorized_agents.get(agent2, False):
                raise PermissionError("Agents not authorized")
            
            if agent1 == agent2:
                raise ValueError("Cannot create channel with self")
            
            # Generate channel ID
            channel_id = await self._generate_channel_id()
            
            # Create channel
            channel = CommunicationChannel(
                id=channel_id,
                agent1=agent1,
                agent2=agent2,
                channel_type=channel_type,
                is_active=True,
                created_timestamp=datetime.utcnow(),
                last_activity=datetime.utcnow(),
                message_count=0,
                participants=[agent1, agent2],
                encryption_enabled=encryption_enabled
            )
            
            # Store channel
            self.channels[channel_id] = channel
            
            # Update agent channel lists
            if agent1 not in self.agent_channels:
                self.agent_channels[agent1] = []
            if agent2 not in self.agent_channels:
                self.agent_channels[agent2] = []
            
            self.agent_channels[agent1].append(channel_id)
            self.agent_channels[agent2].append(channel_id)
            
            # Update stats
            self.communication_stats[agent1].active_channels += 1
            self.communication_stats[agent2].active_channels += 1
            
            logger.info(f"Channel created: {channel_id} between {agent1} and {agent2}")
            return channel_id
            
        except Exception as e:
            logger.error(f"Failed to create channel: {e}")
            raise
    
    async def create_message_template(
        self,
        creator: str,
        name: str,
        description: str,
        message_type: MessageType,
        content_template: str,
        variables: List[str],
        base_price: float = 0.001
    ) -> str:
        """Create a message template"""
        
        try:
            # Generate template ID
            template_id = await self._generate_template_id()
            
            template = MessageTemplate(
                id=template_id,
                name=name,
                description=description,
                message_type=message_type,
                content_template=content_template,
                variables=variables,
                base_price=base_price,
                is_active=True,
                creator=creator
            )
            
            self.message_templates[template_id] = template
            
            logger.info(f"Template created: {template_id}")
            return template_id
            
        except Exception as e:
            logger.error(f"Failed to create template: {e}")
            raise
    
    async def use_template(
        self,
        template_id: str,
        sender: str,
        recipient: str,
        variables: Dict[str, str]
    ) -> str:
        """Use a message template to send a message"""
        
        try:
            if template_id not in self.message_templates:
                raise ValueError(f"Template {template_id} not found")
            
            template = self.message_templates[template_id]
            
            if not template.is_active:
                raise ValueError(f"Template {template_id} not active")
            
            # Substitute variables
            content = template.content_template
            for var, value in variables.items():
                if var in template.variables:
                    content = content.replace(f"{{{var}}}", value)
            
            # Send message
            message_id = await self.send_message(
                sender=sender,
                recipient=recipient,
                message_type=template.message_type,
                content=content,
                metadata={"template_id": template_id}
            )
            
            # Update template usage
            template.usage_count += 1
            
            logger.info(f"Template used: {template_id} -> {message_id}")
            return message_id
            
        except Exception as e:
            logger.error(f"Failed to use template {template_id}: {e}")
            raise
    
    async def get_agent_messages(
        self,
        agent_id: str,
        limit: int = 50,
        offset: int = 0,
        status: Optional[MessageStatus] = None
    ) -> List[Message]:
        """Get messages for an agent"""
        
        try:
            if agent_id not in self.agent_messages:
                return []
            
            message_ids = self.agent_messages[agent_id]
            
            # Apply filters
            filtered_messages = []
            for message_id in message_ids:
                if message_id in self.messages:
                    message = self.messages[message_id]
                    if status is None or message.status == status:
                        filtered_messages.append(message)
            
            # Sort by timestamp (newest first)
            filtered_messages.sort(key=lambda x: x.timestamp, reverse=True)
            
            # Apply pagination
            return filtered_messages[offset:offset + limit]
            
        except Exception as e:
            logger.error(f"Failed to get messages for {agent_id}: {e}")
            return []
    
    async def get_unread_messages(self, agent_id: str) -> List[Message]:
        """Get unread messages for an agent"""
        
        try:
            if agent_id not in self.agent_messages:
                return []
            
            unread_messages = []
            for message_id in self.agent_messages[agent_id]:
                if message_id in self.messages:
                    message = self.messages[message_id]
                    if message.recipient == agent_id and message.status == MessageStatus.DELIVERED:
                        unread_messages.append(message)
            
            return unread_messages
            
        except Exception as e:
            logger.error(f"Failed to get unread messages for {agent_id}: {e}")
            return []
    
    async def get_agent_channels(self, agent_id: str) -> List[CommunicationChannel]:
        """Get channels for an agent"""
        
        try:
            if agent_id not in self.agent_channels:
                return []
            
            channels = []
            for channel_id in self.agent_channels[agent_id]:
                if channel_id in self.channels:
                    channels.append(self.channels[channel_id])
            
            return channels
            
        except Exception as e:
            logger.error(f"Failed to get channels for {agent_id}: {e}")
            return []
    
    async def get_communication_stats(self, agent_id: str) -> CommunicationStats:
        """Get communication statistics for an agent"""
        
        try:
            if agent_id not in self.communication_stats:
                raise ValueError(f"Agent {agent_id} not found")
            
            return self.communication_stats[agent_id]
            
        except Exception as e:
            logger.error(f"Failed to get stats for {agent_id}: {e}")
            raise
    
    async def can_communicate(self, sender: str, recipient: str) -> bool:
        """Check if agents can communicate"""
        
        # Check authorization
        if not self.authorized_agents.get(sender, False) or not self.authorized_agents.get(recipient, False):
            return False
        
        # Check blocked lists
        if (sender in self.blocked_lists and recipient in self.blocked_lists[sender]) or \
           (recipient in self.blocked_lists and sender in self.blocked_lists[recipient]):
            return False
        
        # Check contact lists
        if sender in self.contact_lists and recipient in self.contact_lists[sender]:
            return True
        
        # Check reputation
        if self.reputation_service:
            sender_reputation = await self.reputation_service.get_reputation_score(sender)
            return sender_reputation >= self.min_reputation_score
        
        return False
    
    async def _can_send_message(self, sender: str, recipient: str) -> bool:
        """Check if sender can send message to recipient"""
        return await self.can_communicate(sender, recipient)
    
    async def _generate_message_id(self) -> str:
        """Generate unique message ID"""
        import uuid
        return str(uuid.uuid4())
    
    async def _generate_channel_id(self) -> str:
        """Generate unique channel ID"""
        import uuid
        return str(uuid.uuid4())
    
    async def _generate_template_id(self) -> str:
        """Generate unique template ID"""
        import uuid
        return str(uuid.uuid4())
    
    async def _encrypt_content(self, content: bytes, encryption_type: EncryptionType) -> Tuple[bytes, bytes]:
        """Encrypt message content"""
        
        if encryption_type == EncryptionType.AES256:
            # Simplified AES encryption
            key = hashlib.sha256(content).digest()[:32]  # Generate key from content
            import os
            iv = os.urandom(16)
            
            # In production, use proper AES encryption
            encrypted = content + iv  # Simplified
            return encrypted, key
        
        elif encryption_type == EncryptionType.RSA:
            # Simplified RSA encryption
            key = hashlib.sha256(content).digest()[:256]
            return content + key, key
        
        else:
            return content, b''
    
    async def _decrypt_content(self, encrypted_content: bytes, key: bytes, encryption_type: EncryptionType) -> bytes:
        """Decrypt message content"""
        
        if encryption_type == EncryptionType.AES256:
            # Simplified AES decryption
            if len(encrypted_content) < 16:
                return encrypted_content
            return encrypted_content[:-16]  # Remove IV
        
        elif encryption_type == EncryptionType.RSA:
            # Simplified RSA decryption
            if len(encrypted_content) < 256:
                return encrypted_content
            return encrypted_content[:-256]  # Remove key
        
        else:
            return encrypted_content
    
    async def _calculate_message_price(self, size: int, message_type: MessageType) -> float:
        """Calculate message price based on size and type"""
        
        base_price = self.base_message_price
        
        # Size multiplier
        size_multiplier = max(1, size / 1000)  # 1 AITBC per 1000 bytes
        
        # Type multiplier
        type_multipliers = {
            MessageType.TEXT: 1.0,
            MessageType.DATA: 1.5,
            MessageType.TASK_REQUEST: 2.0,
            MessageType.TASK_RESPONSE: 2.0,
            MessageType.COLLABORATION: 3.0,
            MessageType.NOTIFICATION: 0.5,
            MessageType.SYSTEM: 0.1,
            MessageType.URGENT: 5.0,
            MessageType.BULK: 10.0
        }
        
        type_multiplier = type_multipliers.get(message_type, 1.0)
        
        return base_price * size_multiplier * type_multiplier
    
    async def _get_or_create_channel(self, agent1: str, agent2: str, channel_type: ChannelType) -> str:
        """Get or create communication channel"""
        
        # Check if channel already exists
        if agent1 in self.agent_channels:
            for channel_id in self.agent_channels[agent1]:
                if channel_id in self.channels:
                    channel = self.channels[channel_id]
                    if channel.is_active and (
                        (channel.agent1 == agent1 and channel.agent2 == agent2) or
                        (channel.agent1 == agent2 and channel.agent2 == agent1)
                    ):
                        return channel_id
        
        # Create new channel
        return await self.create_channel(agent1, agent2, channel_type)
    
    async def _update_message_stats(self, sender: str, recipient: str, action: str):
        """Update message statistics"""
        
        if action == 'sent':
            if sender in self.communication_stats:
                self.communication_stats[sender].total_messages += 1
                self.communication_stats[sender].messages_sent += 1
                self.communication_stats[sender].last_activity = datetime.utcnow()
        
        elif action == 'delivered':
            if recipient in self.communication_stats:
                self.communication_stats[recipient].total_messages += 1
                self.communication_stats[recipient].messages_received += 1
                self.communication_stats[recipient].last_activity = datetime.utcnow()
        
        elif action == 'read':
            if recipient in self.communication_stats:
                self.communication_stats[recipient].last_activity = datetime.utcnow()
    
    async def _process_message_queue(self):
        """Process message queue for delivery"""
        
        while True:
            try:
                if self.message_queue:
                    message = self.message_queue.pop(0)
                    
                    # Simulate delivery
                    await asyncio.sleep(0.1)
                    await self.deliver_message(message.id)
                
                await asyncio.sleep(1)
            except Exception as e:
                logger.error(f"Error processing message queue: {e}")
                await asyncio.sleep(5)
    
    async def _cleanup_expired_messages(self):
        """Clean up expired messages"""
        
        while True:
            try:
                current_time = datetime.utcnow()
                expired_messages = []
                
                for message_id, message in self.messages.items():
                    if message.expires_at and current_time > message.expires_at:
                        expired_messages.append(message_id)
                
                for message_id in expired_messages:
                    del self.messages[message_id]
                    # Remove from agent message lists
                    for agent_id, message_ids in self.agent_messages.items():
                        if message_id in message_ids:
                            message_ids.remove(message_id)
                
                if expired_messages:
                    logger.info(f"Cleaned up {len(expired_messages)} expired messages")
                
                await asyncio.sleep(3600)  # Check every hour
            except Exception as e:
                logger.error(f"Error cleaning up messages: {e}")
                await asyncio.sleep(3600)
    
    async def _cleanup_inactive_channels(self):
        """Clean up inactive channels"""
        
        while True:
            try:
                current_time = datetime.utcnow()
                inactive_channels = []
                
                for channel_id, channel in self.channels.items():
                    if channel.is_active and current_time > channel.last_activity + timedelta(seconds=self.channel_timeout):
                        inactive_channels.append(channel_id)
                
                for channel_id in inactive_channels:
                    channel = self.channels[channel_id]
                    channel.is_active = False
                    
                    # Update stats
                    if channel.agent1 in self.communication_stats:
                        self.communication_stats[channel.agent1].active_channels = max(0, self.communication_stats[channel.agent1].active_channels - 1)
                    if channel.agent2 in self.communication_stats:
                        self.communication_stats[channel.agent2].active_channels = max(0, self.communication_stats[channel.agent2].active_channels - 1)
                
                if inactive_channels:
                    logger.info(f"Cleaned up {len(inactive_channels)} inactive channels")
                
                await asyncio.sleep(3600)  # Check every hour
            except Exception as e:
                logger.error(f"Error cleaning up channels: {e}")
                await asyncio.sleep(3600)
    
    def _initialize_default_templates(self):
        """Initialize default message templates"""
        
        templates = [
            MessageTemplate(
                id="task_request_default",
                name="Task Request",
                description="Default template for task requests",
                message_type=MessageType.TASK_REQUEST,
                content_template="Hello! I have a task for you: {task_description}. Budget: {budget} AITBC. Deadline: {deadline}.",
                variables=["task_description", "budget", "deadline"],
                base_price=0.002,
                is_active=True,
                creator="system"
            ),
            MessageTemplate(
                id="collaboration_invite",
                name="Collaboration Invite",
                description="Template for inviting agents to collaborate",
                message_type=MessageType.COLLABORATION,
                content_template="I'd like to collaborate on {project_name}. Your role would be {role_description}. Interested?",
                variables=["project_name", "role_description"],
                base_price=0.003,
                is_active=True,
                creator="system"
            ),
            MessageTemplate(
                id="notification_update",
                name="Notification Update",
                description="Template for sending notifications",
                message_type=MessageType.NOTIFICATION,
                content_template="Notification: {notification_type}. {message}. Action required: {action_required}.",
                variables=["notification_type", "message", "action_required"],
                base_price=0.001,
                is_active=True,
                creator="system"
            )
        ]
        
        for template in templates:
            self.message_templates[template.id] = template
    
    async def _load_communication_data(self):
        """Load existing communication data"""
        # In production, load from database
        pass
    
    async def export_communication_data(self, format: str = "json") -> str:
        """Export communication data"""
        
        data = {
            "messages": {k: asdict(v) for k, v in self.messages.items()},
            "channels": {k: asdict(v) for k, v in self.channels.items()},
            "templates": {k: asdict(v) for k, v in self.message_templates.items()},
            "export_timestamp": datetime.utcnow().isoformat()
        }
        
        if format.lower() == "json":
            return json.dumps(data, indent=2, default=str)
        else:
            raise ValueError(f"Unsupported format: {format}")
    
    async def import_communication_data(self, data: str, format: str = "json"):
        """Import communication data"""
        
        if format.lower() == "json":
            parsed_data = json.loads(data)
            
            # Import messages
            for message_id, message_data in parsed_data.get("messages", {}).items():
                message_data['timestamp'] = datetime.fromisoformat(message_data['timestamp'])
                self.messages[message_id] = Message(**message_data)
            
            # Import channels
            for channel_id, channel_data in parsed_data.get("channels", {}).items():
                channel_data['created_timestamp'] = datetime.fromisoformat(channel_data['created_timestamp'])
                channel_data['last_activity'] = datetime.fromisoformat(channel_data['last_activity'])
                self.channels[channel_id] = CommunicationChannel(**channel_data)
            
            logger.info("Communication data imported successfully")
        else:
            raise ValueError(f"Unsupported format: {format}")
