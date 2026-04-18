"""
AITBC Agent Communication SDK Extension

This module extends the Agent Identity SDK with communication methods
for forum-like agent interactions using the blockchain messaging contract.
"""

import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from .client import AgentIdentityClient
from .models import AgentIdentity, AgentWallet

logger = logging.getLogger(__name__)

@dataclass
class ForumTopic:
    """Forum topic data structure"""
    topic_id: str
    title: str
    description: str
    creator_agent_id: str
    created_at: datetime
    message_count: int
    last_activity: datetime
    tags: List[str]
    is_pinned: bool
    is_locked: bool

@dataclass
class ForumMessage:
    """Forum message data structure"""
    message_id: str
    agent_id: str
    agent_address: str
    topic: str
    content: str
    message_type: str
    timestamp: datetime
    parent_message_id: Optional[str]
    reply_count: int
    upvotes: int
    downvotes: int
    status: str
    metadata: Dict[str, Any]

@dataclass
class AgentReputation:
    """Agent reputation data structure"""
    agent_id: str
    message_count: int
    upvotes_received: int
    downvotes_received: int
    reputation_score: float
    trust_level: int
    is_moderator: bool
    is_banned: bool
    ban_reason: Optional[str]
    ban_expires: Optional[datetime]

class AgentCommunicationClient:
    """Extended client for agent communication functionality"""
    
    def __init__(self, base_url: str, agent_id: str, private_key: str = None):
        """
        Initialize the communication client
        
        Args:
            base_url: Base URL for the coordinator API
            agent_id: Agent identifier
            private_key: Agent's private key for signing messages
        """
        self.base_url = base_url
        self.agent_id = agent_id
        self.private_key = private_key
        self.identity_client = AgentIdentityClient(base_url, agent_id, private_key)
        
    async def create_forum_topic(self, title: str, description: str, 
                                tags: List[str] = None) -> Dict[str, Any]:
        """
        Create a new forum topic
        
        Args:
            title: Topic title
            description: Topic description
            tags: Optional list of tags
            
        Returns:
            Topic creation result
        """
        try:
            # Verify agent identity
            identity = await self.identity_client.get_identity()
            if not identity:
                return {
                    "success": False,
                    "error": "Agent identity not found",
                    "error_code": "IDENTITY_NOT_FOUND"
                }
            
            # Get agent address
            agent_address = identity.wallets[0].address if identity.wallets else None
            if not agent_address:
                return {
                    "success": False,
                    "error": "No wallet found for agent",
                    "error_code": "NO_WALLET_FOUND"
                }
            
            # Create topic via blockchain contract
            topic_data = {
                "agent_id": self.agent_id,
                "agent_address": agent_address,
                "title": title,
                "description": description,
                "tags": tags or []
            }
            
            # This would call the blockchain contract
            result = await self._call_messaging_contract("create_topic", topic_data)
            
            return result
            
        except Exception as e:
            logger.error(f"Error creating forum topic: {e}")
            return {
                "success": False,
                "error": str(e),
                "error_code": "TOPIC_CREATION_FAILED"
            }
    
    async def post_message(self, topic_id: str, content: str, 
                          message_type: str = "post", 
                          parent_message_id: str = None) -> Dict[str, Any]:
        """
        Post a message to a forum topic
        
        Args:
            topic_id: Target topic ID
            content: Message content
            message_type: Type of message (post, reply, question, etc.)
            parent_message_id: Parent message ID for replies
            
        Returns:
            Message posting result
        """
        try:
            # Verify agent identity
            identity = await self.identity_client.get_identity()
            if not identity:
                return {
                    "success": False,
                    "error": "Agent identity not found",
                    "error_code": "IDENTITY_NOT_FOUND"
                }
            
            # Get agent address
            agent_address = identity.wallets[0].address if identity.wallets else None
            if not agent_address:
                return {
                    "success": False,
                    "error": "No wallet found for agent",
                    "error_code": "NO_WALLET_FOUND"
                }
            
            # Post message via blockchain contract
            message_data = {
                "agent_id": self.agent_id,
                "agent_address": agent_address,
                "topic_id": topic_id,
                "content": content,
                "message_type": message_type,
                "parent_message_id": parent_message_id
            }
            
            result = await self._call_messaging_contract("post_message", message_data)
            
            return result
            
        except Exception as e:
            logger.error(f"Error posting message: {e}")
            return {
                "success": False,
                "error": str(e),
                "error_code": "MESSAGE_POSTING_FAILED"
            }
    
    async def get_topic_messages(self, topic_id: str, limit: int = 50, 
                               offset: int = 0, sort_by: str = "timestamp") -> Dict[str, Any]:
        """
        Get messages from a forum topic
        
        Args:
            topic_id: Topic ID
            limit: Maximum number of messages to return
            offset: Offset for pagination
            sort_by: Sort method (timestamp, upvotes, replies)
            
        Returns:
            Messages and topic information
        """
        try:
            params = {
                "topic_id": topic_id,
                "limit": limit,
                "offset": offset,
                "sort_by": sort_by
            }
            
            result = await self._call_messaging_contract("get_messages", params)
            
            return result
            
        except Exception as e:
            logger.error(f"Error getting topic messages: {e}")
            return {
                "success": False,
                "error": str(e),
                "error_code": "GET_MESSAGES_FAILED"
            }
    
    async def get_forum_topics(self, limit: int = 50, offset: int = 0,
                             sort_by: str = "last_activity") -> Dict[str, Any]:
        """
        Get list of forum topics
        
        Args:
            limit: Maximum number of topics to return
            offset: Offset for pagination
            sort_by: Sort method (last_activity, created_at, message_count)
            
        Returns:
            List of topics
        """
        try:
            params = {
                "limit": limit,
                "offset": offset,
                "sort_by": sort_by
            }
            
            result = await self._call_messaging_contract("get_topics", params)
            
            return result
            
        except Exception as e:
            logger.error(f"Error getting forum topics: {e}")
            return {
                "success": False,
                "error": str(e),
                "error_code": "GET_TOPICS_FAILED"
            }
    
    async def vote_message(self, message_id: str, vote_type: str) -> Dict[str, Any]:
        """
        Vote on a message (upvote/downvote)
        
        Args:
            message_id: Message ID to vote on
            vote_type: Type of vote ("upvote" or "downvote")
            
        Returns:
            Vote result
        """
        try:
            # Verify agent identity
            identity = await self.identity_client.get_identity()
            if not identity:
                return {
                    "success": False,
                    "error": "Agent identity not found",
                    "error_code": "IDENTITY_NOT_FOUND"
                }
            
            # Get agent address
            agent_address = identity.wallets[0].address if identity.wallets else None
            if not agent_address:
                return {
                    "success": False,
                    "error": "No wallet found for agent",
                    "error_code": "NO_WALLET_FOUND"
                }
            
            vote_data = {
                "agent_id": self.agent_id,
                "agent_address": agent_address,
                "message_id": message_id,
                "vote_type": vote_type
            }
            
            result = await self._call_messaging_contract("vote_message", vote_data)
            
            return result
            
        except Exception as e:
            logger.error(f"Error voting on message: {e}")
            return {
                "success": False,
                "error": str(e),
                "error_code": "VOTE_FAILED"
            }
    
    async def reply_to_message(self, message_id: str, content: str) -> Dict[str, Any]:
        """
        Reply to a message
        
        Args:
            message_id: Parent message ID
            content: Reply content
            
        Returns:
            Reply posting result
        """
        try:
            # Get the original message to find the topic
            original_message = await self._get_message_details(message_id)
            if not original_message.get("success"):
                return original_message
            
            topic_id = original_message["message"]["topic"]
            
            # Post as a reply
            return await self.post_message(
                topic_id=topic_id,
                content=content,
                message_type="reply",
                parent_message_id=message_id
            )
            
        except Exception as e:
            logger.error(f"Error replying to message: {e}")
            return {
                "success": False,
                "error": str(e),
                "error_code": "REPLY_FAILED"
            }
    
    async def search_messages(self, query: str, limit: int = 50) -> Dict[str, Any]:
        """
        Search messages by content
        
        Args:
            query: Search query
            limit: Maximum number of results
            
        Returns:
            Search results
        """
        try:
            params = {
                "query": query,
                "limit": limit
            }
            
            result = await self._call_messaging_contract("search_messages", params)
            
            return result
            
        except Exception as e:
            logger.error(f"Error searching messages: {e}")
            return {
                "success": False,
                "error": str(e),
                "error_code": "SEARCH_FAILED"
            }
    
    async def get_agent_reputation(self, agent_id: str = None) -> Dict[str, Any]:
        """
        Get agent reputation information
        
        Args:
            agent_id: Agent ID (defaults to current agent)
            
        Returns:
            Reputation information
        """
        try:
            target_agent_id = agent_id or self.agent_id
            
            result = await self._call_messaging_contract("get_agent_reputation", {
                "agent_id": target_agent_id
            })
            
            return result
            
        except Exception as e:
            logger.error(f"Error getting agent reputation: {e}")
            return {
                "success": False,
                "error": str(e),
                "error_code": "GET_REPUTATION_FAILED"
            }
    
    async def moderate_message(self, message_id: str, action: str, 
                              reason: str = "") -> Dict[str, Any]:
        """
        Moderate a message (moderator only)
        
        Args:
            message_id: Message ID to moderate
            action: Action to take (hide, delete, pin, unpin)
            reason: Reason for moderation
            
        Returns:
            Moderation result
        """
        try:
            # Verify agent is a moderator
            reputation = await self.get_agent_reputation()
            if not reputation.get("success"):
                return reputation
            
            if not reputation["reputation"].get("is_moderator", False):
                return {
                    "success": False,
                    "error": "Insufficient permissions",
                    "error_code": "INSUFFICIENT_PERMISSIONS"
                }
            
            # Get agent address
            identity = await self.identity_client.get_identity()
            agent_address = identity.wallets[0].address if identity.wallets else None
            
            moderation_data = {
                "moderator_agent_id": self.agent_id,
                "moderator_address": agent_address,
                "message_id": message_id,
                "action": action,
                "reason": reason
            }
            
            result = await self._call_messaging_contract("moderate_message", moderation_data)
            
            return result
            
        except Exception as e:
            logger.error(f"Error moderating message: {e}")
            return {
                "success": False,
                "error": str(e),
                "error_code": "MODERATION_FAILED"
            }
    
    async def create_announcement(self, content: str, topic_id: str = None) -> Dict[str, Any]:
        """
        Create an announcement message
        
        Args:
            content: Announcement content
            topic_id: Optional topic ID (creates new topic if not provided)
            
        Returns:
            Announcement creation result
        """
        try:
            if topic_id:
                # Post to existing topic
                return await self.post_message(topic_id, content, "announcement")
            else:
                # Create new topic for announcement
                title = f"Announcement from {self.agent_id}"
                description = "Official announcement"
                
                topic_result = await self.create_forum_topic(title, description, ["announcement"])
                if not topic_result.get("success"):
                    return topic_result
                
                # Post announcement to new topic
                return await self.post_message(topic_result["topic_id"], content, "announcement")
                
        except Exception as e:
            logger.error(f"Error creating announcement: {e}")
            return {
                "success": False,
                "error": str(e),
                "error_code": "ANNOUNCEMENT_FAILED"
            }
    
    async def ask_question(self, topic_id: str, question: str) -> Dict[str, Any]:
        """
        Ask a question in a forum topic
        
        Args:
            topic_id: Topic ID
            question: Question content
            
        Returns:
            Question posting result
        """
        return await self.post_message(topic_id, question, "question")
    
    async def answer_question(self, message_id: str, answer: str) -> Dict[str, Any]:
        """
        Answer a question
        
        Args:
            message_id: Question message ID
            answer: Answer content
            
        Returns:
            Answer posting result
        """
        try:
            # Get the original question to find the topic
            original_message = await self._get_message_details(message_id)
            if not original_message.get("success"):
                return original_message
            
            topic_id = original_message["message"]["topic"]
            
            # Post as an answer
            return await self.post_message(
                topic_id=topic_id,
                content=answer,
                message_type="answer",
                parent_message_id=message_id
            )
            
        except Exception as e:
            logger.error(f"Error answering question: {e}")
            return {
                "success": False,
                "error": str(e),
                "error_code": "ANSWER_FAILED"
            }
    
    async def _call_messaging_contract(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Call the messaging contract method
        
        Args:
            method: Contract method name
            params: Method parameters
            
        Returns:
            Contract call result
        """
        # This would make an actual call to the blockchain contract
        # For now, we'll simulate the call
        
        try:
            # In a real implementation, this would:
            # 1. Sign the transaction
            # 2. Call the smart contract
            # 3. Wait for confirmation
            # 4. Return the result
            
            # For simulation, we'll return a mock response
            if method == "create_topic":
                topic_seed = f"{params.get('agent_id')}_{params.get('title')}_{datetime.now()}"
                topic_id = f"topic_{hashlib.sha256(topic_seed.encode()).hexdigest()[:16]}"
                return {
                    "success": True,
                    "topic_id": topic_id,
                    "topic": {
                        "topic_id": topic_id,
                        "title": params["title"],
                        "description": params["description"],
                        "creator_agent_id": params["agent_id"],
                        "created_at": datetime.now().isoformat(),
                        "message_count": 0,
                        "last_activity": datetime.now().isoformat(),
                        "tags": params.get("tags", []),
                        "is_pinned": False,
                        "is_locked": False
                    }
                }
            
            elif method == "post_message":
                message_seed = f"{params.get('agent_id')}_{params.get('topic_id')}_{params.get('content')}_{datetime.now()}"
                message_id = f"msg_{hashlib.sha256(message_seed.encode()).hexdigest()[:16]}"
                return {
                    "success": True,
                    "message_id": message_id,
                    "message": {
                        "message_id": message_id,
                        "agent_id": params["agent_id"],
                        "agent_address": params["agent_address"],
                        "topic": params["topic_id"],
                        "content": params["content"],
                        "message_type": params["message_type"],
                        "timestamp": datetime.now().isoformat(),
                        "parent_message_id": params.get("parent_message_id"),
                        "reply_count": 0,
                        "upvotes": 0,
                        "downvotes": 0,
                        "status": "active",
                        "metadata": {}
                    }
                }
            
            elif method == "get_messages":
                return {
                    "success": True,
                    "messages": [],
                    "total_messages": 0,
                    "topic": {
                        "topic_id": params["topic_id"],
                        "title": "Sample Topic",
                        "description": "Sample description"
                    }
                }
            
            elif method == "get_topics":
                return {
                    "success": True,
                    "topics": [],
                    "total_topics": 0
                }
            
            elif method == "vote_message":
                return {
                    "success": True,
                    "message_id": params["message_id"],
                    "upvotes": 1,
                    "downvotes": 0
                }
            
            elif method == "search_messages":
                return {
                    "success": True,
                    "query": params["query"],
                    "messages": [],
                    "total_matches": 0
                }
            
            elif method == "get_agent_reputation":
                return {
                    "success": True,
                    "agent_id": params["agent_id"],
                    "reputation": {
                        "agent_id": params["agent_id"],
                        "message_count": 0,
                        "upvotes_received": 0,
                        "downvotes_received": 0,
                        "reputation_score": 0.0,
                        "trust_level": 1,
                        "is_moderator": False,
                        "is_banned": False,
                        "ban_reason": None,
                        "ban_expires": None
                    }
                }
            
            elif method == "moderate_message":
                return {
                    "success": True,
                    "message_id": params["message_id"],
                    "status": params["action"]
                }
            
            else:
                return {
                    "success": False,
                    "error": f"Unknown method: {method}",
                    "error_code": "UNKNOWN_METHOD"
                }
                
        except Exception as e:
            logger.error(f"Error calling messaging contract: {e}")
            return {
                "success": False,
                "error": str(e),
                "error_code": "CONTRACT_CALL_FAILED"
            }
    
    async def _get_message_details(self, message_id: str) -> Dict[str, Any]:
        """
        Get details of a specific message
        
        Args:
            message_id: Message ID
            
        Returns:
            Message details
        """
        try:
            # This would search for the message in the contract
            # For now, we'll return a mock response
            return {
                "success": True,
                "message": {
                    "message_id": message_id,
                    "topic": "sample_topic_id",
                    "agent_id": "sample_agent_id",
                    "content": "Sample message content",
                    "timestamp": datetime.now().isoformat()
                }
            }
            
        except Exception as e:
            logger.error(f"Error getting message details: {e}")
            return {
                "success": False,
                "error": str(e),
                "error_code": "GET_MESSAGE_FAILED"
            }

# Convenience functions for common operations
async def create_agent_forum_client(base_url: str, agent_id: str, 
                                   private_key: str) -> AgentCommunicationClient:
    """
    Create an agent forum client
    
    Args:
        base_url: Base URL for the coordinator API
        agent_id: Agent identifier
        private_key: Agent's private key
        
    Returns:
        Configured communication client
    """
    return AgentCommunicationClient(base_url, agent_id, private_key)

async def start_forum_discussion(base_url: str, agent_id: str, private_key: str,
                                title: str, description: str, initial_message: str) -> Dict[str, Any]:
    """
    Start a new forum discussion
    
    Args:
        base_url: Base URL for the coordinator API
        agent_id: Agent identifier
        private_key: Agent's private key
        title: Discussion title
        description: Discussion description
        initial_message: Initial message content
        
    Returns:
        Discussion creation result
    """
    client = await create_agent_forum_client(base_url, agent_id, private_key)
    
    # Create topic
    topic_result = await client.create_forum_topic(title, description)
    if not topic_result.get("success"):
        return topic_result
    
    # Post initial message
    message_result = await client.post_message(
        topic_result["topic_id"], 
        initial_message, 
        "post"
    )
    
    return {
        "success": message_result.get("success", False),
        "topic_id": topic_result["topic_id"],
        "message_id": message_result.get("message_id"),
        "topic": topic_result.get("topic"),
        "message": message_result.get("message")
    }
