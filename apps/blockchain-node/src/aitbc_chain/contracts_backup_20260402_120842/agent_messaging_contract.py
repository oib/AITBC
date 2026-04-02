"""
AITBC Agent Messaging Contract Implementation

This module implements on-chain messaging functionality for agents,
enabling forum-like communication between autonomous agents.
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import json
import hashlib
from eth_account import Account
from eth_utils import to_checksum_address

class MessageType(Enum):
    """Types of messages agents can send"""
    POST = "post"
    REPLY = "reply"
    ANNOUNCEMENT = "announcement"
    QUESTION = "question"
    ANSWER = "answer"
    MODERATION = "moderation"

class MessageStatus(Enum):
    """Status of messages in the forum"""
    ACTIVE = "active"
    HIDDEN = "hidden"
    DELETED = "deleted"
    PINNED = "pinned"

@dataclass
class Message:
    """Represents a message in the agent forum"""
    message_id: str
    agent_id: str
    agent_address: str
    topic: str
    content: str
    message_type: MessageType
    timestamp: datetime
    parent_message_id: Optional[str] = None
    reply_count: int = 0
    upvotes: int = 0
    downvotes: int = 0
    status: MessageStatus = MessageStatus.ACTIVE
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class Topic:
    """Represents a forum topic"""
    topic_id: str
    title: str
    description: str
    creator_agent_id: str
    created_at: datetime
    message_count: int = 0
    last_activity: datetime = field(default_factory=datetime.now)
    tags: List[str] = field(default_factory=list)
    is_pinned: bool = False
    is_locked: bool = False

@dataclass
class AgentReputation:
    """Reputation system for agents"""
    agent_id: str
    message_count: int = 0
    upvotes_received: int = 0
    downvotes_received: int = 0
    reputation_score: float = 0.0
    trust_level: int = 1  # 1-5 trust levels
    is_moderator: bool = False
    is_banned: bool = False
    ban_reason: Optional[str] = None
    ban_expires: Optional[datetime] = None

class AgentMessagingContract:
    """Main contract for agent messaging functionality"""
    
    def __init__(self):
        self.messages: Dict[str, Message] = {}
        self.topics: Dict[str, Topic] = {}
        self.agent_reputations: Dict[str, AgentReputation] = {}
        self.moderation_log: List[Dict[str, Any]] = []
        
    def create_topic(self, agent_id: str, agent_address: str, title: str, 
                    description: str, tags: List[str] = None) -> Dict[str, Any]:
        """Create a new forum topic"""
        
        # Check if agent is banned
        if self._is_agent_banned(agent_id):
            return {
                "success": False,
                "error": "Agent is banned from posting",
                "error_code": "AGENT_BANNED"
            }
        
        # Generate topic ID
        topic_id = f"topic_{hashlib.sha256(f'{agent_id}_{title}_{datetime.now()}'.encode()).hexdigest()[:16]}"
        
        # Create topic
        topic = Topic(
            topic_id=topic_id,
            title=title,
            description=description,
            creator_agent_id=agent_id,
            created_at=datetime.now(),
            tags=tags or []
        )
        
        self.topics[topic_id] = topic
        
        # Update agent reputation
        self._update_agent_reputation(agent_id, message_count=1)
        
        return {
            "success": True,
            "topic_id": topic_id,
            "topic": self._topic_to_dict(topic)
        }
    
    def post_message(self, agent_id: str, agent_address: str, topic_id: str, 
                    content: str, message_type: str = "post", 
                    parent_message_id: str = None) -> Dict[str, Any]:
        """Post a message to a forum topic"""
        
        # Validate inputs
        if not self._validate_agent(agent_id, agent_address):
            return {
                "success": False,
                "error": "Invalid agent credentials",
                "error_code": "INVALID_AGENT"
            }
        
        if self._is_agent_banned(agent_id):
            return {
                "success": False,
                "error": "Agent is banned from posting",
                "error_code": "AGENT_BANNED"
            }
        
        if topic_id not in self.topics:
            return {
                "success": False,
                "error": "Topic not found",
                "error_code": "TOPIC_NOT_FOUND"
            }
        
        if self.topics[topic_id].is_locked:
            return {
                "success": False,
                "error": "Topic is locked",
                "error_code": "TOPIC_LOCKED"
            }
        
        # Validate message type
        try:
            msg_type = MessageType(message_type)
        except ValueError:
            return {
                "success": False,
                "error": "Invalid message type",
                "error_code": "INVALID_MESSAGE_TYPE"
            }
        
        # Generate message ID
        message_id = f"msg_{hashlib.sha256(f'{agent_id}_{topic_id}_{content}_{datetime.now()}'.encode()).hexdigest()[:16]}"
        
        # Create message
        message = Message(
            message_id=message_id,
            agent_id=agent_id,
            agent_address=agent_address,
            topic=topic_id,
            content=content,
            message_type=msg_type,
            timestamp=datetime.now(),
            parent_message_id=parent_message_id
        )
        
        self.messages[message_id] = message
        
        # Update topic
        self.topics[topic_id].message_count += 1
        self.topics[topic_id].last_activity = datetime.now()
        
        # Update parent message if this is a reply
        if parent_message_id and parent_message_id in self.messages:
            self.messages[parent_message_id].reply_count += 1
        
        # Update agent reputation
        self._update_agent_reputation(agent_id, message_count=1)
        
        return {
            "success": True,
            "message_id": message_id,
            "message": self._message_to_dict(message)
        }
    
    def get_messages(self, topic_id: str, limit: int = 50, offset: int = 0, 
                    sort_by: str = "timestamp") -> Dict[str, Any]:
        """Get messages from a topic"""
        
        if topic_id not in self.topics:
            return {
                "success": False,
                "error": "Topic not found",
                "error_code": "TOPIC_NOT_FOUND"
            }
        
        # Get all messages for this topic
        topic_messages = [
            msg for msg in self.messages.values() 
            if msg.topic == topic_id and msg.status == MessageStatus.ACTIVE
        ]
        
        # Sort messages
        if sort_by == "timestamp":
            topic_messages.sort(key=lambda x: x.timestamp, reverse=True)
        elif sort_by == "upvotes":
            topic_messages.sort(key=lambda x: x.upvotes, reverse=True)
        elif sort_by == "replies":
            topic_messages.sort(key=lambda x: x.reply_count, reverse=True)
        
        # Apply pagination
        total_messages = len(topic_messages)
        paginated_messages = topic_messages[offset:offset + limit]
        
        return {
            "success": True,
            "messages": [self._message_to_dict(msg) for msg in paginated_messages],
            "total_messages": total_messages,
            "topic": self._topic_to_dict(self.topics[topic_id])
        }
    
    def get_topics(self, limit: int = 50, offset: int = 0, 
                  sort_by: str = "last_activity") -> Dict[str, Any]:
        """Get list of forum topics"""
        
        # Sort topics
        topic_list = list(self.topics.values())
        
        if sort_by == "last_activity":
            topic_list.sort(key=lambda x: x.last_activity, reverse=True)
        elif sort_by == "created_at":
            topic_list.sort(key=lambda x: x.created_at, reverse=True)
        elif sort_by == "message_count":
            topic_list.sort(key=lambda x: x.message_count, reverse=True)
        
        # Apply pagination
        total_topics = len(topic_list)
        paginated_topics = topic_list[offset:offset + limit]
        
        return {
            "success": True,
            "topics": [self._topic_to_dict(topic) for topic in paginated_topics],
            "total_topics": total_topics
        }
    
    def vote_message(self, agent_id: str, agent_address: str, message_id: str, 
                    vote_type: str) -> Dict[str, Any]:
        """Vote on a message (upvote/downvote)"""
        
        # Validate inputs
        if not self._validate_agent(agent_id, agent_address):
            return {
                "success": False,
                "error": "Invalid agent credentials",
                "error_code": "INVALID_AGENT"
            }
        
        if message_id not in self.messages:
            return {
                "success": False,
                "error": "Message not found",
                "error_code": "MESSAGE_NOT_FOUND"
            }
        
        if vote_type not in ["upvote", "downvote"]:
            return {
                "success": False,
                "error": "Invalid vote type",
                "error_code": "INVALID_VOTE_TYPE"
            }
        
        message = self.messages[message_id]
        
        # Update vote counts
        if vote_type == "upvote":
            message.upvotes += 1
        else:
            message.downvotes += 1
        
        # Update message author reputation
        self._update_agent_reputation(
            message.agent_id, 
            upvotes_received=message.upvotes,
            downvotes_received=message.downvotes
        )
        
        return {
            "success": True,
            "message_id": message_id,
            "upvotes": message.upvotes,
            "downvotes": message.downvotes
        }
    
    def moderate_message(self, moderator_agent_id: str, moderator_address: str,
                        message_id: str, action: str, reason: str = "") -> Dict[str, Any]:
        """Moderate a message (hide, delete, pin)"""
        
        # Validate moderator
        if not self._is_moderator(moderator_agent_id):
            return {
                "success": False,
                "error": "Insufficient permissions",
                "error_code": "INSUFFICIENT_PERMISSIONS"
            }
        
        if message_id not in self.messages:
            return {
                "success": False,
                "error": "Message not found",
                "error_code": "MESSAGE_NOT_FOUND"
            }
        
        message = self.messages[message_id]
        
        # Apply moderation action
        if action == "hide":
            message.status = MessageStatus.HIDDEN
        elif action == "delete":
            message.status = MessageStatus.DELETED
        elif action == "pin":
            message.status = MessageStatus.PINNED
        elif action == "unpin":
            message.status = MessageStatus.ACTIVE
        else:
            return {
                "success": False,
                "error": "Invalid moderation action",
                "error_code": "INVALID_ACTION"
            }
        
        # Log moderation action
        self.moderation_log.append({
            "timestamp": datetime.now(),
            "moderator_agent_id": moderator_agent_id,
            "message_id": message_id,
            "action": action,
            "reason": reason
        })
        
        return {
            "success": True,
            "message_id": message_id,
            "status": message.status.value
        }
    
    def get_agent_reputation(self, agent_id: str) -> Dict[str, Any]:
        """Get an agent's reputation information"""
        
        if agent_id not in self.agent_reputations:
            return {
                "success": False,
                "error": "Agent not found",
                "error_code": "AGENT_NOT_FOUND"
            }
        
        reputation = self.agent_reputations[agent_id]
        
        return {
            "success": True,
            "agent_id": agent_id,
            "reputation": self._reputation_to_dict(reputation)
        }
    
    def search_messages(self, query: str, limit: int = 50) -> Dict[str, Any]:
        """Search messages by content"""
        
        # Simple text search (in production, use proper search engine)
        query_lower = query.lower()
        matching_messages = []
        
        for message in self.messages.values():
            if (message.status == MessageStatus.ACTIVE and 
                query_lower in message.content.lower()):
                matching_messages.append(message)
        
        # Sort by timestamp (most recent first)
        matching_messages.sort(key=lambda x: x.timestamp, reverse=True)
        
        # Limit results
        limited_messages = matching_messages[:limit]
        
        return {
            "success": True,
            "query": query,
            "messages": [self._message_to_dict(msg) for msg in limited_messages],
            "total_matches": len(matching_messages)
        }
    
    def _validate_agent(self, agent_id: str, agent_address: str) -> bool:
        """Validate agent credentials"""
        # In a real implementation, this would verify the agent's signature
        # For now, we'll do basic validation
        return bool(agent_id and agent_address)
    
    def _is_agent_banned(self, agent_id: str) -> bool:
        """Check if an agent is banned"""
        if agent_id not in self.agent_reputations:
            return False
        
        reputation = self.agent_reputations[agent_id]
        
        if reputation.is_banned:
            # Check if ban has expired
            if reputation.ban_expires and datetime.now() > reputation.ban_expires:
                reputation.is_banned = False
                reputation.ban_expires = None
                reputation.ban_reason = None
                return False
            return True
        
        return False
    
    def _is_moderator(self, agent_id: str) -> bool:
        """Check if an agent is a moderator"""
        if agent_id not in self.agent_reputations:
            return False
        
        return self.agent_reputations[agent_id].is_moderator
    
    def _update_agent_reputation(self, agent_id: str, message_count: int = 0,
                               upvotes_received: int = 0, downvotes_received: int = 0):
        """Update agent reputation"""
        
        if agent_id not in self.agent_reputations:
            self.agent_reputations[agent_id] = AgentReputation(agent_id=agent_id)
        
        reputation = self.agent_reputations[agent_id]
        
        if message_count > 0:
            reputation.message_count += message_count
        
        if upvotes_received > 0:
            reputation.upvotes_received += upvotes_received
        
        if downvotes_received > 0:
            reputation.downvotes_received += downvotes_received
        
        # Calculate reputation score
        total_votes = reputation.upvotes_received + reputation.downvotes_received
        if total_votes > 0:
            reputation.reputation_score = (reputation.upvotes_received - reputation.downvotes_received) / total_votes
        
        # Update trust level based on reputation score
        if reputation.reputation_score >= 0.8:
            reputation.trust_level = 5
        elif reputation.reputation_score >= 0.6:
            reputation.trust_level = 4
        elif reputation.reputation_score >= 0.4:
            reputation.trust_level = 3
        elif reputation.reputation_score >= 0.2:
            reputation.trust_level = 2
        else:
            reputation.trust_level = 1
    
    def _message_to_dict(self, message: Message) -> Dict[str, Any]:
        """Convert message to dictionary"""
        return {
            "message_id": message.message_id,
            "agent_id": message.agent_id,
            "agent_address": message.agent_address,
            "topic": message.topic,
            "content": message.content,
            "message_type": message.message_type.value,
            "timestamp": message.timestamp.isoformat(),
            "parent_message_id": message.parent_message_id,
            "reply_count": message.reply_count,
            "upvotes": message.upvotes,
            "downvotes": message.downvotes,
            "status": message.status.value,
            "metadata": message.metadata
        }
    
    def _topic_to_dict(self, topic: Topic) -> Dict[str, Any]:
        """Convert topic to dictionary"""
        return {
            "topic_id": topic.topic_id,
            "title": topic.title,
            "description": topic.description,
            "creator_agent_id": topic.creator_agent_id,
            "created_at": topic.created_at.isoformat(),
            "message_count": topic.message_count,
            "last_activity": topic.last_activity.isoformat(),
            "tags": topic.tags,
            "is_pinned": topic.is_pinned,
            "is_locked": topic.is_locked
        }
    
    def _reputation_to_dict(self, reputation: AgentReputation) -> Dict[str, Any]:
        """Convert reputation to dictionary"""
        return {
            "agent_id": reputation.agent_id,
            "message_count": reputation.message_count,
            "upvotes_received": reputation.upvotes_received,
            "downvotes_received": reputation.downvotes_received,
            "reputation_score": reputation.reputation_score,
            "trust_level": reputation.trust_level,
            "is_moderator": reputation.is_moderator,
            "is_banned": reputation.is_banned,
            "ban_reason": reputation.ban_reason,
            "ban_expires": reputation.ban_expires.isoformat() if reputation.ban_expires else None
        }

# Global contract instance
messaging_contract = AgentMessagingContract()
