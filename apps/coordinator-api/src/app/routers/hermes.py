"""
Hermes Router - Agent communication API endpoints

Provides:
- Agent registration
- Send/receive messages
- Broadcast messaging
- Message status tracking
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from ..services.hermes_service import get_hermes_service, MessageType
from ..rate_limiting import rate_limit


router = APIRouter(prefix="/hermes", tags=["hermes"])


class RegisterAgentRequest(BaseModel):
    """Request to register agent"""
    agent_id: str
    public_key: str
    capabilities: List[str] = Field(default_factory=list)


class SendMessageRequest(BaseModel):
    """Request to send message"""
    sender: str
    recipient: str
    content: str
    message_type: str = "direct"
    encrypted: bool = False
    reply_to: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


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
@rate_limit(rate=20, per=60)
async def register_agent(
    request: Request,
    req: RegisterAgentRequest
) -> Dict[str, Any]:
    """Register an agent for messaging"""
    try:
        service = get_hermes_service()
        
        profile = service.register_agent(
            agent_id=req.agent_id,
            public_key=req.public_key,
            capabilities=req.capabilities
        )
        
        return {
            "success": True,
            "agent": {
                "id": profile.agent_id,
                "capabilities": profile.capabilities,
                "online": profile.online
            }
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Registration failed: {str(e)}"
        )


@router.post("/messages/send", summary="Send message")
@rate_limit(rate=100, per=60)
async def send_message(
    request: Request,
    req: SendMessageRequest
) -> Dict[str, Any]:
    """Send a direct message to another agent"""
    try:
        service = get_hermes_service()
        
        message = service.send_message(
            sender=req.sender,
            recipient=req.recipient,
            content=req.content,
            message_type=req.message_type,
            encrypted=req.encrypted,
            reply_to=req.reply_to,
            metadata=req.metadata
        )
        
        return {
            "success": True,
            "message": message.to_dict()
        }
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Send failed: {str(e)}"
        )


@router.post("/messages/broadcast", summary="Broadcast message")
@rate_limit(rate=10, per=60)
async def broadcast(
    request: Request,
    req: BroadcastRequest
) -> Dict[str, Any]:
    """Broadcast a message to all agents"""
    try:
        service = get_hermes_service()
        
        messages = service.broadcast(
            sender=req.sender,
            content=req.content,
            encrypted=req.encrypted
        )
        
        return {
            "success": True,
            "sent_count": len(messages),
            "messages": [m.to_dict() for m in messages]
        }
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Broadcast failed: {str(e)}"
        )


@router.get("/messages/{agent_id}", summary="Get messages")
@rate_limit(rate=100, per=60)
async def get_messages(
    request: Request,
    agent_id: str,
    message_type: Optional[str] = None,
    unread_only: bool = False
) -> Dict[str, Any]:
    """Get messages for an agent"""
    try:
        service = get_hermes_service()
        
        messages = service.get_messages(
            agent_id=agent_id,
            message_type=message_type,
            unread_only=unread_only
        )
        
        return {
            "agent_id": agent_id,
            "messages": [m.to_dict() for m in messages],
            "count": len(messages)
        }
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get messages: {str(e)}"
        )


@router.post("/messages/read", summary="Mark message as read")
@rate_limit(rate=100, per=60)
async def mark_read(
    request: Request,
    req: MarkReadRequest
) -> Dict[str, Any]:
    """Mark a message as read"""
    try:
        service = get_hermes_service()
        
        success = service.mark_read(req.agent_id, req.message_id)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to mark as read"
            )
        
        return {
            "success": True,
            "message_id": req.message_id,
            "status": "read"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to mark read: {str(e)}"
        )


@router.get("/agents/{agent_id}/profile", summary="Get agent profile")
@rate_limit(rate=100, per=60)
async def get_agent_profile(
    request: Request,
    agent_id: str
) -> Dict[str, Any]:
    """Get agent communication profile"""
    try:
        service = get_hermes_service()
        
        profile = service.get_agent_profile(agent_id)
        if not profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Agent {agent_id} not found"
            )
        
        return {
            "agent_id": profile.agent_id,
            "capabilities": profile.capabilities,
            "online": profile.online,
            "last_seen": profile.last_seen.isoformat(),
            "queued_messages": len(profile.message_queue)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get profile: {str(e)}")


@router.get("/agents", summary="List agents")
@rate_limit(rate=50, per=60)
async def list_agents(
    request: Request,
    online_only: bool = False
) -> Dict[str, Any]:
    """List registered agents"""
    try:
        service = get_hermes_service()
        
        agents = service.list_agents(online_only=online_only)
        
        return {
            "agents": [
                {
                    "agent_id": a.agent_id,
                    "online": a.online,
                    "capabilities": a.capabilities
                }
                for a in agents
            ],
            "count": len(agents)
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list agents: {str(e)}"
        )


@router.post("/agents/{agent_id}/status", summary="Update agent status")
@rate_limit(rate=50, per=60)
async def update_status(
    request: Request,
    agent_id: str,
    online: bool
) -> Dict[str, Any]:
    """Update agent online status"""
    try:
        service = get_hermes_service()
        
        success = service.update_agent_status(agent_id, online)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Agent {agent_id} not found"
            )
        
        return {
            "success": True,
            "agent_id": agent_id,
            "online": online
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update status: {str(e)}"
        )


@router.get("/stats", summary="Get statistics")
@rate_limit(rate=30, per=60)
async def get_stats(request: Request) -> Dict[str, Any]:
    """Get messaging statistics"""
    try:
        service = get_hermes_service()
        
        return service.get_stats()
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get stats: {str(e)}"
        )


@router.get("/health", summary="Health check")
async def health_check(request: Request) -> Dict[str, Any]:
    """Check Hermes service health"""
    try:
        service = get_hermes_service()
        stats = service.get_stats()
        
        return {
            "status": "healthy",
            "registered_agents": stats["registered_agents"],
            "online_agents": stats["online_agents"],
            "total_messages": stats["total_messages"]
        }
        
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e)
        }
