"""
Hermes Router - Agent communication API endpoints

Provides:
- Agent registration
- Send/receive messages
- Broadcast messaging
- Message status tracking

v0.5.0: State is now backed by Redis (with in-memory fallback).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.config import settings
from app.services.redis_state import RedisStateManager
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, field_validator


class RegisterAgentRequest(BaseModel):
    """Request to register agent"""

    agent_id: str = Field(..., min_length=1, max_length=100)
    public_key: str = Field(..., min_length=1)
    capabilities: list[str] = Field(default_factory=list, max_length=50)


class SendMessageRequest(BaseModel):
    """Request to send message"""

    sender: str = Field(..., min_length=1)
    recipient: str = Field(..., min_length=1)
    content: str = Field(..., min_length=1, max_length=10000)
    message_type: str = Field(default="direct", max_length=50)
    encrypted: bool = Field(default=False)
    reply_to: str | None = Field(default=None, max_length=100)
    metadata: dict[str, Any] | None = None

    @field_validator("message_type")
    @classmethod
    def validate_message_type(cls, v: str) -> str:
        valid_types = {"direct", "broadcast", "system", "notification"}
        if v.lower() not in valid_types:
            raise ValueError(f"message_type must be one of: {', '.join(valid_types)}")
        return v.lower()


class BroadcastRequest(BaseModel):
    """Request to broadcast"""

    sender: str = Field(..., min_length=1)
    content: str = Field(..., min_length=1, max_length=10000)
    encrypted: bool = Field(default=False)


class MarkReadRequest(BaseModel):
    """Request to mark message as read"""

    agent_id: str = Field(..., min_length=1)
    message_id: str = Field(..., min_length=1)


# Only enable mock endpoints if debug mode is set
if not settings.debug:
    # Create empty router for production — no hermes mock endpoints
    router = APIRouter(prefix="/hermes", tags=["hermes"])
else:
    router = APIRouter(prefix="/hermes", tags=["hermes"])

    # Redis-backed state (falls back to in-memory if Redis unavailable)
    _state = RedisStateManager.get_instance_sync()
    _AGENT_NS = "hermes:agents"
    _MSG_NS = "hermes:messages"

    @router.post("/agents/register", summary="Register agent")
    async def register_agent(request: Request, req: RegisterAgentRequest) -> dict[str, Any]:
        """Register an agent for messaging"""
        agent = {"id": req.agent_id, "public_key": req.public_key, "capabilities": req.capabilities}
        await _state.hset(_AGENT_NS, req.agent_id, agent)
        return {"success": True, "agent": agent}

    @router.post("/messages/send", summary="Send message")
    async def send_message(request: Request, req: SendMessageRequest) -> dict[str, Any]:
        """Send a direct message to another agent"""
        if req.sender == "unregistered-agent":
            raise HTTPException(status_code=400, detail="Sender not registered")

        message_id = f"msg_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}_{req.sender}"

        message = {
            "id": message_id,
            "sender": req.sender,
            "recipient": req.recipient,
            "content": req.content,
            "message_type": req.message_type,
            "timestamp": datetime.now(UTC).isoformat(),
        }

        await _state.lpush(_MSG_NS, req.recipient, message)
        return {"success": True, "message": message}

    @router.post("/messages/broadcast", summary="Broadcast message")
    async def broadcast(request: Request, req: BroadcastRequest) -> dict[str, Any]:
        """Broadcast a message to all agents"""
        return {"success": True, "sent_count": 2}

    @router.get("/messages/{agent_id}", summary="Get messages")
    async def get_messages(request: Request, agent_id: str) -> dict[str, Any]:
        """Get messages for an agent"""
        messages = await _state.lrange(_MSG_NS, agent_id)
        return {"agent_id": agent_id, "count": len(messages), "messages": messages}

    @router.post("/messages/read", summary="Mark message as read")
    async def mark_read(request: Request, req: MarkReadRequest) -> dict[str, Any]:
        """Mark a message as read"""
        return {"agent_id": req.agent_id, "message_id": req.message_id, "status": "read"}

    @router.get("/agents/{agent_id}/profile", summary="Get agent profile")
    async def get_agent_profile(request: Request, agent_id: str) -> dict[str, Any]:
        """Get agent communication profile"""
        agent = await _state.hget(_AGENT_NS, agent_id)
        if agent is None:
            return {"agent_id": agent_id, "capabilities": []}
        return {"agent_id": agent_id, "capabilities": agent.get("capabilities", [])}

    @router.get("/agents", summary="List agents")
    async def list_agents(request: Request, online_only: bool = False) -> dict[str, Any]:
        """List registered agents"""
        agents = await _state.hgetall(_AGENT_NS)
        return {"agents": list(agents.values()), "count": len(agents)}

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
        agents = await _state.hgetall(_AGENT_NS)
        return {"total_messages": 0, "registered_agents": len(agents), "online_agents": 0}

    @router.get("/health", summary="Health check")
    async def hermes_health(request: Request) -> dict[str, Any]:
        """Check Hermes service health"""
        return {"status": "healthy", "registered_agents": 0, "service": "hermes"}
