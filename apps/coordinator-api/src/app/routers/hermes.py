"""
Hermes Router - Agent communication API endpoints

Provides:
- Agent registration
- Send/receive messages
- Broadcast messaging
- Message status tracking
"""

from __future__ annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.config import settings

# Only enable mock endpoints if debug mode or explicit flag is set
if not (settings.debug or settings.enable_mock_hermes):
    # Create empty router for production
    router = APIRouter(prefix="/hermes", tags=["hermes"])
else:
    router = APIRouter(prefix="/hermes", tags=["hermes"])

    # In-memory state for mock data
    _mock_agents: dict[str, dict[str, Any]] = {}
    _mock_messages: dict[str, list[dict[str, Any]]] = {}
    _message_counter = 0


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


@router.post("/agents/register", summary="Register agent")
async def register_agent(request: Request, req: RegisterAgentRequest) -> dict[str, Any]:
    """Register an agent for messaging"""
    _mock_agents[req.agent_id] = {"id": req.agent_id, "public_key": req.public_key, "capabilities": req.capabilities}
    # Initialize message list for this agent
    if req.agent_id not in _mock_messages:
        _mock_messages[req.agent_id] = []
    return {"success": True, "agent": _mock_agents[req.agent_id]}


@router.post("/messages/send", summary="Send message")
async def send_message(request: Request, req: SendMessageRequest) -> dict[str, Any]:
    """Send a direct message to another agent"""
    if req.sender == "unregistered-agent":
        raise HTTPException(status_code=400, detail="Sender not registered")

    global _message_counter
    _message_counter += 1
    message_id = f"msg-{_message_counter:03d}"

    message = {
        "id": message_id,
        "sender": req.sender,
        "recipient": req.recipient,
        "content": req.content,
        "message_type": req.message_type,
        "timestamp": datetime.now(UTC).isoformat(),
    }

    # Add message to recipient's inbox
    if req.recipient not in _mock_messages:
        _mock_messages[req.recipient] = []
    _mock_messages[req.recipient].append(message)

    return {"success": True, "message": message}


@router.post("/messages/broadcast", summary="Broadcast message")
async def broadcast(request: Request, req: BroadcastRequest) -> dict[str, Any]:
    """Broadcast a message to all agents"""
    return {"success": True, "sent_count": 2}


@router.get("/messages/{agent_id}", summary="Get messages")
async def get_messages(request: Request, agent_id: str) -> dict[str, Any]:
    """Get messages for an agent"""
    messages = _mock_messages.get(agent_id, [])
    return {"agent_id": agent_id, "count": len(messages), "messages": messages}


@router.post("/messages/read", summary="Mark message as read")
async def mark_read(request: Request, req: MarkReadRequest) -> dict[str, Any]:
    """Mark a message as read"""
    return {"agent_id": req.agent_id, "message_id": req.message_id, "status": "read"}


@router.get("/agents/{agent_id}/profile", summary="Get agent profile")
async def get_agent_profile(request: Request, agent_id: str) -> dict[str, Any]:
    """Get agent communication profile"""
    return {"agent_id": agent_id, "capabilities": ["ai", "gpu"]}


@router.get("/agents", summary="List agents")
async def list_agents(request: Request, online_only: bool = False) -> dict[str, Any]:
    """List registered agents"""
    return {"agents": [], "count": 0}


@router.post("/agents/{agent_id}/heartbeat", summary="Agent heartbeat")
async def heartbeat(request: Request, agent_id: str) -> dict[str, Any]:
    """Send heartbeat from an agent"""
    return {"success": True}


@router.post("/agents/{agent_id}/status", summary="Update agent status")
async def update_status(request: Request, agent_id: str, online: bool) -> dict[str, Any]:
    """Update agent online status"""
    return {"success": True}


@router.get("/stats", summary="Get statistics")
async def get_stats(request: Request) -> dict[str, Any]:
    """Get messaging statistics"""
    return {"total_messages": 0, "registered_agents": 0, "online_agents": 0}


@router.get("/health", summary="Health check")
async def hermes_health(request: Request) -> dict[str, Any]:
    """Check Hermes service health"""
    return {"status": "healthy", "registered_agents": 0, "service": "hermes"}
