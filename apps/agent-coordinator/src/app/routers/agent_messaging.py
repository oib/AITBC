"""
Agent Messaging Router - Provides /api/v1/agent/messages/ endpoints

Migrated from Coordinator API hermes messaging to Agent Coordinator microservice.
Provides agent-to-agent messaging with PING/PONG support.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from aitbc import get_logger

from .. import state

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1/agent/messages", tags=["agent-messaging"])


class RegisterAgentRequest(BaseModel):
    """Request to register agent"""
    agent_id: str
    public_key: str
    capabilities: list[str] = Field(default_factory=list)


class SendMessageRequest(BaseModel):
    """Request to send message"""
    sender: str
    recipient: str
    content: str
    message_type: str = "direct"
    encrypted: bool = False
    reply_to: str | None = None
    metadata: dict[str, Any] | None = None


class BroadcastRequest(BaseModel):
    """Request to broadcast"""
    sender: str
    content: str
    encrypted: bool = False


class MarkReadRequest(BaseModel):
    """Request to mark message as read"""
    agent_id: str
    message_id: str


# In-memory state for compatibility with Coordinator API behavior
_mock_agents: dict[str, dict[str, Any]] = {}
_mock_messages: dict[str, list[dict[str, Any]]] = {}
_message_counter = 0


@router.post("/agents/register", summary="Register agent")
async def register_agent(
    request: Request,
    req: RegisterAgentRequest
) -> dict[str, Any]:
    """Register an agent for messaging"""
    global _mock_agents, _mock_messages
    
    _mock_agents[req.agent_id] = {
        "id": req.agent_id,
        "public_key": req.public_key,
        "capabilities": req.capabilities
    }
    # Initialize message list for this agent
    if req.agent_id not in _mock_messages:
        _mock_messages[req.agent_id] = []
    
    return {
        "success": True,
        "agent": _mock_agents[req.agent_id]
    }


@router.post("/send", summary="Send message")
async def send_message(
    request: Request,
    req: SendMessageRequest
) -> dict[str, Any]:
    """Send a direct message to another agent"""
    global _mock_messages, _message_counter
    
    if req.sender not in _mock_agents:
        _mock_agents[req.sender] = {"id": req.sender, "public_key": "", "capabilities": []}
        _mock_messages[req.sender] = []
    
    _message_counter += 1
    message_id = f"msg-{_message_counter:03d}"
    
    message = {
        "id": message_id,
        "sender": req.sender,
        "recipient": req.recipient,
        "content": req.content,
        "message_type": req.message_type,
        "timestamp": datetime.now(UTC).isoformat()
    }
    
    # Add message to recipient's inbox
    if req.recipient not in _mock_messages:
        _mock_messages[req.recipient] = []
    _mock_messages[req.recipient].append(message)
    
    logger.info(f"Message sent from {req.sender} to {req.recipient}: {req.content}")
    
    return {
        "success": True,
        "message": message
    }


@router.get("/{agent_id}", summary="Get messages for agent")
async def get_messages(
    request: Request,
    agent_id: str
) -> dict[str, Any]:
    """Get all messages for a specific agent"""
    if agent_id not in _mock_messages:
        return {
            "agent_id": agent_id,
            "count": 0,
            "messages": []
        }
    
    messages = _mock_messages[agent_id]
    
    return {
        "agent_id": agent_id,
        "count": len(messages),
        "messages": messages
    }


@router.post("/broadcast", summary="Broadcast message")
async def broadcast_message(
    request: Request,
    req: BroadcastRequest
) -> dict[str, Any]:
    """Broadcast message to all registered agents"""
    global _mock_messages, _message_counter
    
    if req.sender not in _mock_agents:
        raise HTTPException(status_code=400, detail="Sender not registered")
    
    recipients = []
    for agent_id in _mock_agents:
        if agent_id == req.sender:
            continue  # Skip sender
        
        _message_counter += 1
        message_id = f"msg-{_message_counter:03d}"
        
        message = {
            "id": message_id,
            "sender": req.sender,
            "recipient": agent_id,
            "content": req.content,
            "message_type": "broadcast",
            "timestamp": datetime.now(UTC).isoformat()
        }
        
        if agent_id not in _mock_messages:
            _mock_messages[agent_id] = []
        _mock_messages[agent_id].append(message)
        recipients.append(agent_id)
    
    logger.info(f"Broadcast from {req.sender} to {len(recipients)} agents")
    
    return {
        "success": True,
        "sent_count": len(recipients),
        "recipients": recipients
    }


@router.post("/read", summary="Mark message as read")
async def mark_read(
    request: Request,
    req: MarkReadRequest
) -> dict[str, Any]:
    """Mark a message as read"""
    if req.agent_id not in _mock_messages:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    for message in _mock_messages[req.agent_id]:
        if message["id"] == req.message_id:
            message["read"] = True
            message["read_at"] = datetime.now(UTC).isoformat()
            return {
                "status": "read",
                "message_id": req.message_id
            }
    
    raise HTTPException(status_code=404, detail="Message not found")


@router.get("/agents/list", summary="List all agents")
async def list_agents(
    request: Request
) -> dict[str, Any]:
    """List all registered agents"""
    return {
        "agents": list(_mock_agents.values()),
        "count": len(_mock_agents)
    }
