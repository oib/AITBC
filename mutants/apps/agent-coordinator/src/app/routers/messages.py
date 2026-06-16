import json
from datetime import UTC, datetime
from typing import Any

from aitbc import get_logger
from aitbc.rate_limiting import rate_limit
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from .. import state
from ..encryption import get_encryptor
from ..models import BroadcastRequest
from ..protocols.communication import MessageType
from ..routing.load_balancer import LoadBalancingStrategy

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1/agent/messages", tags=["agent-messaging"])


from mutmut.mutation.trampoline import MutantDict
from mutmut.mutation.trampoline import wrap_in_trampoline as _mutmut_mutated


class SendMessageRequest(BaseModel):
    """Request to send encrypted message"""

    sender: str = Field(..., description="Sender agent ID")
    recipient: str = Field(..., description="Recipient agent ID")
    content: dict[str, Any] = Field(..., description="Message content")
    message_type: str = Field(default="direct", description="Message type")
    encrypt: bool = Field(default=True, description="Whether to encrypt message")
    priority: str = Field(default="normal", description="Message priority")
    ttl: int = Field(default=300, description="Time to live in seconds")


class SubscribeRequest(BaseModel):
    """Request to subscribe to topic"""

    agent_id: str = Field(..., description="Agent ID")
    topic: str = Field(..., description="Topic to subscribe to")
    filter: dict[str, Any] = Field(default_factory=dict, description="Filter criteria")


@router.post("/send")
@rate_limit(rate=50, per=60)
async def send_encrypted_message(request: Request, req: SendMessageRequest) -> dict[str, Any]:
    """Send encrypted message to agent"""
    try:
        encryptor = get_encryptor()
        message_content = {
            "content": req.content,
            "message_type": req.message_type,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        if req.encrypt:
            encrypted_msg = encryptor.encrypt_message(
                message=message_content, sender_id=req.sender, recipient_id=req.recipient
            )
            if not encrypted_msg:
                raise HTTPException(status_code=500, detail="Failed to encrypt message")
            message_data = encrypted_msg.to_dict()
            message_data["encrypted"] = True
        else:
            message_data = {
                "sender": req.sender,
                "recipient": req.recipient,
                "content": json.dumps(req.content),
                "message_type": req.message_type,
                "encrypted": False,
                "priority": req.priority,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        if state.message_storage:
            import uuid

            message_id = f"msg_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"
            redis_message_data = {k: str(v) if not isinstance(v, str) else v for k, v in message_data.items()}
            await state.message_storage.store_message(message_id, redis_message_data)
        return {
            "status": "success",
            "message_id": message_id if state.message_storage else "in-memory",
            "sender": req.sender,
            "recipient": req.recipient,
            "encrypted": req.encrypt,
            "sent_at": datetime.now(UTC).isoformat(),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error sending encrypted message: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/inbox")
@rate_limit(rate=200, per=60)
async def get_inbox(
    request: Request,
    agent_id: str = Query(..., description="Agent ID"),
    limit: int = Query(100, description="Maximum messages"),
    unread_only: bool = Query(False, description="Only unread messages"),
) -> dict[str, Any]:
    """Get agent's inbox"""
    try:
        if not state.message_storage:
            return {"agent_id": agent_id, "messages": [], "count": 0, "timestamp": datetime.now(UTC).isoformat()}
        messages = await state.message_storage.get_messages_by_receiver(agent_id, limit, 0)
        if unread_only:
            messages = [m for m in messages if not m.get("read", False)]
        return {"agent_id": agent_id, "messages": messages, "count": len(messages), "timestamp": datetime.now(UTC).isoformat()}
    except Exception as e:
        logger.error("Error getting inbox: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/history")
@rate_limit(rate=200, per=60)
async def get_message_history(
    request: Request,
    sender_id: str | None = Query(None, description="Filter by sender ID"),
    receiver_id: str | None = Query(None, description="Filter by receiver ID"),
    limit: int = Query(100, description="Maximum number of messages"),
    offset: int = Query(0, description="Offset for pagination"),
) -> dict[str, Any]:
    """Get message history with optional filters"""
    try:
        if not state.message_storage:
            raise HTTPException(status_code=503, detail="Message storage not available")
        if sender_id:
            messages = await state.message_storage.get_messages_by_sender(sender_id, limit, offset)
        elif receiver_id:
            messages = await state.message_storage.get_messages_by_receiver(receiver_id, limit, offset)
        else:
            messages = await state.message_storage.get_all_messages(limit, offset)
        total = 0
        if state.message_storage:
            total = await state.message_storage.get_message_count()
        return {
            "status": "success",
            "messages": messages,
            "count": len(messages),
            "total": total,
            "limit": limit,
            "offset": offset,
            "timestamp": datetime.now(UTC).isoformat(),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error retrieving message history: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/{agent_id}")
@rate_limit(rate=200, per=60)
async def get_messages_for_agent_compatibility(request: Request, agent_id: str) -> dict[str, Any]:
    """Get messages for agent - AgentDaemon compatibility route"""
    return await get_messages_for_agent(request, agent_id)


mutants_x_get_messages_for_agent__mutmut: MutantDict = {}  # type: ignore


@_mutmut_mutated(mutants_x_get_messages_for_agent__mutmut)
async def get_messages_for_agent(request: Request, agent_id: str) -> dict[str, Any]:
    try:
        if not state.message_storage:
            return {"agent_id": agent_id, "count": 0, "messages": [], "timestamp": datetime.now(UTC).isoformat()}
        messages = await state.message_storage.get_messages_by_receiver(agent_id, 100, 0)
        return {"agent_id": agent_id, "count": len(messages), "messages": messages, "timestamp": datetime.now(UTC).isoformat()}
    except Exception as e:
        logger.error("Error getting messages for agent %s: %s", agent_id, e)
        raise HTTPException(status_code=500, detail=str(e)) from e


async def x_get_messages_for_agent__mutmut_orig(request: Request, agent_id: str) -> dict[str, Any]:
    try:
        if not state.message_storage:
            return {"agent_id": agent_id, "count": 0, "messages": [], "timestamp": datetime.now(UTC).isoformat()}
        messages = await state.message_storage.get_messages_by_receiver(agent_id, 100, 0)
        return {"agent_id": agent_id, "count": len(messages), "messages": messages, "timestamp": datetime.now(UTC).isoformat()}
    except Exception as e:
        logger.error("Error getting messages for agent %s: %s", agent_id, e)
        raise HTTPException(status_code=500, detail=str(e)) from e


async def x_get_messages_for_agent__mutmut_1(request: Request, agent_id: str) -> dict[str, Any]:
    try:
        if state.message_storage:
            return {"agent_id": agent_id, "count": 0, "messages": [], "timestamp": datetime.now(UTC).isoformat()}
        messages = await state.message_storage.get_messages_by_receiver(agent_id, 100, 0)
        return {"agent_id": agent_id, "count": len(messages), "messages": messages, "timestamp": datetime.now(UTC).isoformat()}
    except Exception as e:
        logger.error("Error getting messages for agent %s: %s", agent_id, e)
        raise HTTPException(status_code=500, detail=str(e)) from e


async def x_get_messages_for_agent__mutmut_2(request: Request, agent_id: str) -> dict[str, Any]:
    try:
        if not state.message_storage:
            return {"XXagent_idXX": agent_id, "count": 0, "messages": [], "timestamp": datetime.now(UTC).isoformat()}
        messages = await state.message_storage.get_messages_by_receiver(agent_id, 100, 0)
        return {"agent_id": agent_id, "count": len(messages), "messages": messages, "timestamp": datetime.now(UTC).isoformat()}
    except Exception as e:
        logger.error("Error getting messages for agent %s: %s", agent_id, e)
        raise HTTPException(status_code=500, detail=str(e)) from e


async def x_get_messages_for_agent__mutmut_3(request: Request, agent_id: str) -> dict[str, Any]:
    try:
        if not state.message_storage:
            return {"AGENT_ID": agent_id, "count": 0, "messages": [], "timestamp": datetime.now(UTC).isoformat()}
        messages = await state.message_storage.get_messages_by_receiver(agent_id, 100, 0)
        return {"agent_id": agent_id, "count": len(messages), "messages": messages, "timestamp": datetime.now(UTC).isoformat()}
    except Exception as e:
        logger.error("Error getting messages for agent %s: %s", agent_id, e)
        raise HTTPException(status_code=500, detail=str(e)) from e


async def x_get_messages_for_agent__mutmut_4(request: Request, agent_id: str) -> dict[str, Any]:
    try:
        if not state.message_storage:
            return {"agent_id": agent_id, "XXcountXX": 0, "messages": [], "timestamp": datetime.now(UTC).isoformat()}
        messages = await state.message_storage.get_messages_by_receiver(agent_id, 100, 0)
        return {"agent_id": agent_id, "count": len(messages), "messages": messages, "timestamp": datetime.now(UTC).isoformat()}
    except Exception as e:
        logger.error("Error getting messages for agent %s: %s", agent_id, e)
        raise HTTPException(status_code=500, detail=str(e)) from e


async def x_get_messages_for_agent__mutmut_5(request: Request, agent_id: str) -> dict[str, Any]:
    try:
        if not state.message_storage:
            return {"agent_id": agent_id, "COUNT": 0, "messages": [], "timestamp": datetime.now(UTC).isoformat()}
        messages = await state.message_storage.get_messages_by_receiver(agent_id, 100, 0)
        return {"agent_id": agent_id, "count": len(messages), "messages": messages, "timestamp": datetime.now(UTC).isoformat()}
    except Exception as e:
        logger.error("Error getting messages for agent %s: %s", agent_id, e)
        raise HTTPException(status_code=500, detail=str(e)) from e


async def x_get_messages_for_agent__mutmut_6(request: Request, agent_id: str) -> dict[str, Any]:
    try:
        if not state.message_storage:
            return {"agent_id": agent_id, "count": 1, "messages": [], "timestamp": datetime.now(UTC).isoformat()}
        messages = await state.message_storage.get_messages_by_receiver(agent_id, 100, 0)
        return {"agent_id": agent_id, "count": len(messages), "messages": messages, "timestamp": datetime.now(UTC).isoformat()}
    except Exception as e:
        logger.error("Error getting messages for agent %s: %s", agent_id, e)
        raise HTTPException(status_code=500, detail=str(e)) from e


async def x_get_messages_for_agent__mutmut_7(request: Request, agent_id: str) -> dict[str, Any]:
    try:
        if not state.message_storage:
            return {"agent_id": agent_id, "count": 0, "XXmessagesXX": [], "timestamp": datetime.now(UTC).isoformat()}
        messages = await state.message_storage.get_messages_by_receiver(agent_id, 100, 0)
        return {"agent_id": agent_id, "count": len(messages), "messages": messages, "timestamp": datetime.now(UTC).isoformat()}
    except Exception as e:
        logger.error("Error getting messages for agent %s: %s", agent_id, e)
        raise HTTPException(status_code=500, detail=str(e)) from e


async def x_get_messages_for_agent__mutmut_8(request: Request, agent_id: str) -> dict[str, Any]:
    try:
        if not state.message_storage:
            return {"agent_id": agent_id, "count": 0, "MESSAGES": [], "timestamp": datetime.now(UTC).isoformat()}
        messages = await state.message_storage.get_messages_by_receiver(agent_id, 100, 0)
        return {"agent_id": agent_id, "count": len(messages), "messages": messages, "timestamp": datetime.now(UTC).isoformat()}
    except Exception as e:
        logger.error("Error getting messages for agent %s: %s", agent_id, e)
        raise HTTPException(status_code=500, detail=str(e)) from e


async def x_get_messages_for_agent__mutmut_9(request: Request, agent_id: str) -> dict[str, Any]:
    try:
        if not state.message_storage:
            return {"agent_id": agent_id, "count": 0, "messages": [], "XXtimestampXX": datetime.now(UTC).isoformat()}
        messages = await state.message_storage.get_messages_by_receiver(agent_id, 100, 0)
        return {"agent_id": agent_id, "count": len(messages), "messages": messages, "timestamp": datetime.now(UTC).isoformat()}
    except Exception as e:
        logger.error("Error getting messages for agent %s: %s", agent_id, e)
        raise HTTPException(status_code=500, detail=str(e)) from e


async def x_get_messages_for_agent__mutmut_10(request: Request, agent_id: str) -> dict[str, Any]:
    try:
        if not state.message_storage:
            return {"agent_id": agent_id, "count": 0, "messages": [], "TIMESTAMP": datetime.now(UTC).isoformat()}
        messages = await state.message_storage.get_messages_by_receiver(agent_id, 100, 0)
        return {"agent_id": agent_id, "count": len(messages), "messages": messages, "timestamp": datetime.now(UTC).isoformat()}
    except Exception as e:
        logger.error("Error getting messages for agent %s: %s", agent_id, e)
        raise HTTPException(status_code=500, detail=str(e)) from e


async def x_get_messages_for_agent__mutmut_11(request: Request, agent_id: str) -> dict[str, Any]:
    try:
        if not state.message_storage:
            return {"agent_id": agent_id, "count": 0, "messages": [], "timestamp": datetime.now(None).isoformat()}
        messages = await state.message_storage.get_messages_by_receiver(agent_id, 100, 0)
        return {"agent_id": agent_id, "count": len(messages), "messages": messages, "timestamp": datetime.now(UTC).isoformat()}
    except Exception as e:
        logger.error("Error getting messages for agent %s: %s", agent_id, e)
        raise HTTPException(status_code=500, detail=str(e)) from e


async def x_get_messages_for_agent__mutmut_12(request: Request, agent_id: str) -> dict[str, Any]:
    try:
        if not state.message_storage:
            return {"agent_id": agent_id, "count": 0, "messages": [], "timestamp": datetime.now(UTC).isoformat()}
        messages = None
        return {"agent_id": agent_id, "count": len(messages), "messages": messages, "timestamp": datetime.now(UTC).isoformat()}
    except Exception as e:
        logger.error("Error getting messages for agent %s: %s", agent_id, e)
        raise HTTPException(status_code=500, detail=str(e)) from e


async def x_get_messages_for_agent__mutmut_13(request: Request, agent_id: str) -> dict[str, Any]:
    try:
        if not state.message_storage:
            return {"agent_id": agent_id, "count": 0, "messages": [], "timestamp": datetime.now(UTC).isoformat()}
        messages = await state.message_storage.get_messages_by_receiver(None, 100, 0)
        return {"agent_id": agent_id, "count": len(messages), "messages": messages, "timestamp": datetime.now(UTC).isoformat()}
    except Exception as e:
        logger.error("Error getting messages for agent %s: %s", agent_id, e)
        raise HTTPException(status_code=500, detail=str(e)) from e


async def x_get_messages_for_agent__mutmut_14(request: Request, agent_id: str) -> dict[str, Any]:
    try:
        if not state.message_storage:
            return {"agent_id": agent_id, "count": 0, "messages": [], "timestamp": datetime.now(UTC).isoformat()}
        messages = await state.message_storage.get_messages_by_receiver(agent_id, None, 0)
        return {"agent_id": agent_id, "count": len(messages), "messages": messages, "timestamp": datetime.now(UTC).isoformat()}
    except Exception as e:
        logger.error("Error getting messages for agent %s: %s", agent_id, e)
        raise HTTPException(status_code=500, detail=str(e)) from e


async def x_get_messages_for_agent__mutmut_15(request: Request, agent_id: str) -> dict[str, Any]:
    try:
        if not state.message_storage:
            return {"agent_id": agent_id, "count": 0, "messages": [], "timestamp": datetime.now(UTC).isoformat()}
        messages = await state.message_storage.get_messages_by_receiver(agent_id, 100, None)
        return {"agent_id": agent_id, "count": len(messages), "messages": messages, "timestamp": datetime.now(UTC).isoformat()}
    except Exception as e:
        logger.error("Error getting messages for agent %s: %s", agent_id, e)
        raise HTTPException(status_code=500, detail=str(e)) from e


async def x_get_messages_for_agent__mutmut_16(request: Request, agent_id: str) -> dict[str, Any]:
    try:
        if not state.message_storage:
            return {"agent_id": agent_id, "count": 0, "messages": [], "timestamp": datetime.now(UTC).isoformat()}
        messages = await state.message_storage.get_messages_by_receiver(100, 0)
        return {"agent_id": agent_id, "count": len(messages), "messages": messages, "timestamp": datetime.now(UTC).isoformat()}
    except Exception as e:
        logger.error("Error getting messages for agent %s: %s", agent_id, e)
        raise HTTPException(status_code=500, detail=str(e)) from e


async def x_get_messages_for_agent__mutmut_17(request: Request, agent_id: str) -> dict[str, Any]:
    try:
        if not state.message_storage:
            return {"agent_id": agent_id, "count": 0, "messages": [], "timestamp": datetime.now(UTC).isoformat()}
        messages = await state.message_storage.get_messages_by_receiver(agent_id, 0)
        return {"agent_id": agent_id, "count": len(messages), "messages": messages, "timestamp": datetime.now(UTC).isoformat()}
    except Exception as e:
        logger.error("Error getting messages for agent %s: %s", agent_id, e)
        raise HTTPException(status_code=500, detail=str(e)) from e


async def x_get_messages_for_agent__mutmut_18(request: Request, agent_id: str) -> dict[str, Any]:
    try:
        if not state.message_storage:
            return {"agent_id": agent_id, "count": 0, "messages": [], "timestamp": datetime.now(UTC).isoformat()}
        messages = await state.message_storage.get_messages_by_receiver(
            agent_id,
            100,
        )
        return {"agent_id": agent_id, "count": len(messages), "messages": messages, "timestamp": datetime.now(UTC).isoformat()}
    except Exception as e:
        logger.error("Error getting messages for agent %s: %s", agent_id, e)
        raise HTTPException(status_code=500, detail=str(e)) from e


async def x_get_messages_for_agent__mutmut_19(request: Request, agent_id: str) -> dict[str, Any]:
    try:
        if not state.message_storage:
            return {"agent_id": agent_id, "count": 0, "messages": [], "timestamp": datetime.now(UTC).isoformat()}
        messages = await state.message_storage.get_messages_by_receiver(agent_id, 101, 0)
        return {"agent_id": agent_id, "count": len(messages), "messages": messages, "timestamp": datetime.now(UTC).isoformat()}
    except Exception as e:
        logger.error("Error getting messages for agent %s: %s", agent_id, e)
        raise HTTPException(status_code=500, detail=str(e)) from e


async def x_get_messages_for_agent__mutmut_20(request: Request, agent_id: str) -> dict[str, Any]:
    try:
        if not state.message_storage:
            return {"agent_id": agent_id, "count": 0, "messages": [], "timestamp": datetime.now(UTC).isoformat()}
        messages = await state.message_storage.get_messages_by_receiver(agent_id, 100, 1)
        return {"agent_id": agent_id, "count": len(messages), "messages": messages, "timestamp": datetime.now(UTC).isoformat()}
    except Exception as e:
        logger.error("Error getting messages for agent %s: %s", agent_id, e)
        raise HTTPException(status_code=500, detail=str(e)) from e


async def x_get_messages_for_agent__mutmut_21(request: Request, agent_id: str) -> dict[str, Any]:
    try:
        if not state.message_storage:
            return {"agent_id": agent_id, "count": 0, "messages": [], "timestamp": datetime.now(UTC).isoformat()}
        messages = await state.message_storage.get_messages_by_receiver(agent_id, 100, 0)
        return {
            "XXagent_idXX": agent_id,
            "count": len(messages),
            "messages": messages,
            "timestamp": datetime.now(UTC).isoformat(),
        }
    except Exception as e:
        logger.error("Error getting messages for agent %s: %s", agent_id, e)
        raise HTTPException(status_code=500, detail=str(e)) from e


async def x_get_messages_for_agent__mutmut_22(request: Request, agent_id: str) -> dict[str, Any]:
    try:
        if not state.message_storage:
            return {"agent_id": agent_id, "count": 0, "messages": [], "timestamp": datetime.now(UTC).isoformat()}
        messages = await state.message_storage.get_messages_by_receiver(agent_id, 100, 0)
        return {"AGENT_ID": agent_id, "count": len(messages), "messages": messages, "timestamp": datetime.now(UTC).isoformat()}
    except Exception as e:
        logger.error("Error getting messages for agent %s: %s", agent_id, e)
        raise HTTPException(status_code=500, detail=str(e)) from e


async def x_get_messages_for_agent__mutmut_23(request: Request, agent_id: str) -> dict[str, Any]:
    try:
        if not state.message_storage:
            return {"agent_id": agent_id, "count": 0, "messages": [], "timestamp": datetime.now(UTC).isoformat()}
        messages = await state.message_storage.get_messages_by_receiver(agent_id, 100, 0)
        return {
            "agent_id": agent_id,
            "XXcountXX": len(messages),
            "messages": messages,
            "timestamp": datetime.now(UTC).isoformat(),
        }
    except Exception as e:
        logger.error("Error getting messages for agent %s: %s", agent_id, e)
        raise HTTPException(status_code=500, detail=str(e)) from e


async def x_get_messages_for_agent__mutmut_24(request: Request, agent_id: str) -> dict[str, Any]:
    try:
        if not state.message_storage:
            return {"agent_id": agent_id, "count": 0, "messages": [], "timestamp": datetime.now(UTC).isoformat()}
        messages = await state.message_storage.get_messages_by_receiver(agent_id, 100, 0)
        return {"agent_id": agent_id, "COUNT": len(messages), "messages": messages, "timestamp": datetime.now(UTC).isoformat()}
    except Exception as e:
        logger.error("Error getting messages for agent %s: %s", agent_id, e)
        raise HTTPException(status_code=500, detail=str(e)) from e


async def x_get_messages_for_agent__mutmut_25(request: Request, agent_id: str) -> dict[str, Any]:
    try:
        if not state.message_storage:
            return {"agent_id": agent_id, "count": 0, "messages": [], "timestamp": datetime.now(UTC).isoformat()}
        messages = await state.message_storage.get_messages_by_receiver(agent_id, 100, 0)
        return {
            "agent_id": agent_id,
            "count": len(messages),
            "XXmessagesXX": messages,
            "timestamp": datetime.now(UTC).isoformat(),
        }
    except Exception as e:
        logger.error("Error getting messages for agent %s: %s", agent_id, e)
        raise HTTPException(status_code=500, detail=str(e)) from e


async def x_get_messages_for_agent__mutmut_26(request: Request, agent_id: str) -> dict[str, Any]:
    try:
        if not state.message_storage:
            return {"agent_id": agent_id, "count": 0, "messages": [], "timestamp": datetime.now(UTC).isoformat()}
        messages = await state.message_storage.get_messages_by_receiver(agent_id, 100, 0)
        return {"agent_id": agent_id, "count": len(messages), "MESSAGES": messages, "timestamp": datetime.now(UTC).isoformat()}
    except Exception as e:
        logger.error("Error getting messages for agent %s: %s", agent_id, e)
        raise HTTPException(status_code=500, detail=str(e)) from e


async def x_get_messages_for_agent__mutmut_27(request: Request, agent_id: str) -> dict[str, Any]:
    try:
        if not state.message_storage:
            return {"agent_id": agent_id, "count": 0, "messages": [], "timestamp": datetime.now(UTC).isoformat()}
        messages = await state.message_storage.get_messages_by_receiver(agent_id, 100, 0)
        return {
            "agent_id": agent_id,
            "count": len(messages),
            "messages": messages,
            "XXtimestampXX": datetime.now(UTC).isoformat(),
        }
    except Exception as e:
        logger.error("Error getting messages for agent %s: %s", agent_id, e)
        raise HTTPException(status_code=500, detail=str(e)) from e


async def x_get_messages_for_agent__mutmut_28(request: Request, agent_id: str) -> dict[str, Any]:
    try:
        if not state.message_storage:
            return {"agent_id": agent_id, "count": 0, "messages": [], "timestamp": datetime.now(UTC).isoformat()}
        messages = await state.message_storage.get_messages_by_receiver(agent_id, 100, 0)
        return {"agent_id": agent_id, "count": len(messages), "messages": messages, "TIMESTAMP": datetime.now(UTC).isoformat()}
    except Exception as e:
        logger.error("Error getting messages for agent %s: %s", agent_id, e)
        raise HTTPException(status_code=500, detail=str(e)) from e


async def x_get_messages_for_agent__mutmut_29(request: Request, agent_id: str) -> dict[str, Any]:
    try:
        if not state.message_storage:
            return {"agent_id": agent_id, "count": 0, "messages": [], "timestamp": datetime.now(UTC).isoformat()}
        messages = await state.message_storage.get_messages_by_receiver(agent_id, 100, 0)
        return {
            "agent_id": agent_id,
            "count": len(messages),
            "messages": messages,
            "timestamp": datetime.now(None).isoformat(),
        }
    except Exception as e:
        logger.error("Error getting messages for agent %s: %s", agent_id, e)
        raise HTTPException(status_code=500, detail=str(e)) from e


async def x_get_messages_for_agent__mutmut_30(request: Request, agent_id: str) -> dict[str, Any]:
    try:
        if not state.message_storage:
            return {"agent_id": agent_id, "count": 0, "messages": [], "timestamp": datetime.now(UTC).isoformat()}
        messages = await state.message_storage.get_messages_by_receiver(agent_id, 100, 0)
        return {"agent_id": agent_id, "count": len(messages), "messages": messages, "timestamp": datetime.now(UTC).isoformat()}
    except Exception as e:
        logger.error(None, agent_id, e)
        raise HTTPException(status_code=500, detail=str(e)) from e


async def x_get_messages_for_agent__mutmut_31(request: Request, agent_id: str) -> dict[str, Any]:
    try:
        if not state.message_storage:
            return {"agent_id": agent_id, "count": 0, "messages": [], "timestamp": datetime.now(UTC).isoformat()}
        messages = await state.message_storage.get_messages_by_receiver(agent_id, 100, 0)
        return {"agent_id": agent_id, "count": len(messages), "messages": messages, "timestamp": datetime.now(UTC).isoformat()}
    except Exception as e:
        logger.error("Error getting messages for agent %s: %s", None, e)
        raise HTTPException(status_code=500, detail=str(e)) from e


async def x_get_messages_for_agent__mutmut_32(request: Request, agent_id: str) -> dict[str, Any]:
    try:
        if not state.message_storage:
            return {"agent_id": agent_id, "count": 0, "messages": [], "timestamp": datetime.now(UTC).isoformat()}
        messages = await state.message_storage.get_messages_by_receiver(agent_id, 100, 0)
        return {"agent_id": agent_id, "count": len(messages), "messages": messages, "timestamp": datetime.now(UTC).isoformat()}
    except Exception as e:
        logger.error("Error getting messages for agent %s: %s", agent_id, None)
        raise HTTPException(status_code=500, detail=str(e)) from e


async def x_get_messages_for_agent__mutmut_33(request: Request, agent_id: str) -> dict[str, Any]:
    try:
        if not state.message_storage:
            return {"agent_id": agent_id, "count": 0, "messages": [], "timestamp": datetime.now(UTC).isoformat()}
        messages = await state.message_storage.get_messages_by_receiver(agent_id, 100, 0)
        return {"agent_id": agent_id, "count": len(messages), "messages": messages, "timestamp": datetime.now(UTC).isoformat()}
    except Exception as e:
        logger.error(agent_id, e)
        raise HTTPException(status_code=500, detail=str(e)) from e


async def x_get_messages_for_agent__mutmut_34(request: Request, agent_id: str) -> dict[str, Any]:
    try:
        if not state.message_storage:
            return {"agent_id": agent_id, "count": 0, "messages": [], "timestamp": datetime.now(UTC).isoformat()}
        messages = await state.message_storage.get_messages_by_receiver(agent_id, 100, 0)
        return {"agent_id": agent_id, "count": len(messages), "messages": messages, "timestamp": datetime.now(UTC).isoformat()}
    except Exception as e:
        logger.error("Error getting messages for agent %s: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


async def x_get_messages_for_agent__mutmut_35(request: Request, agent_id: str) -> dict[str, Any]:
    try:
        if not state.message_storage:
            return {"agent_id": agent_id, "count": 0, "messages": [], "timestamp": datetime.now(UTC).isoformat()}
        messages = await state.message_storage.get_messages_by_receiver(agent_id, 100, 0)
        return {"agent_id": agent_id, "count": len(messages), "messages": messages, "timestamp": datetime.now(UTC).isoformat()}
    except Exception as e:
        logger.error(
            "Error getting messages for agent %s: %s",
            agent_id,
        )
        raise HTTPException(status_code=500, detail=str(e)) from e


async def x_get_messages_for_agent__mutmut_36(request: Request, agent_id: str) -> dict[str, Any]:
    try:
        if not state.message_storage:
            return {"agent_id": agent_id, "count": 0, "messages": [], "timestamp": datetime.now(UTC).isoformat()}
        messages = await state.message_storage.get_messages_by_receiver(agent_id, 100, 0)
        return {"agent_id": agent_id, "count": len(messages), "messages": messages, "timestamp": datetime.now(UTC).isoformat()}
    except Exception as e:
        logger.error("XXError getting messages for agent %s: %sXX", agent_id, e)
        raise HTTPException(status_code=500, detail=str(e)) from e


async def x_get_messages_for_agent__mutmut_37(request: Request, agent_id: str) -> dict[str, Any]:
    try:
        if not state.message_storage:
            return {"agent_id": agent_id, "count": 0, "messages": [], "timestamp": datetime.now(UTC).isoformat()}
        messages = await state.message_storage.get_messages_by_receiver(agent_id, 100, 0)
        return {"agent_id": agent_id, "count": len(messages), "messages": messages, "timestamp": datetime.now(UTC).isoformat()}
    except Exception as e:
        logger.error("error getting messages for agent %s: %s", agent_id, e)
        raise HTTPException(status_code=500, detail=str(e)) from e


async def x_get_messages_for_agent__mutmut_38(request: Request, agent_id: str) -> dict[str, Any]:
    try:
        if not state.message_storage:
            return {"agent_id": agent_id, "count": 0, "messages": [], "timestamp": datetime.now(UTC).isoformat()}
        messages = await state.message_storage.get_messages_by_receiver(agent_id, 100, 0)
        return {"agent_id": agent_id, "count": len(messages), "messages": messages, "timestamp": datetime.now(UTC).isoformat()}
    except Exception as e:
        logger.error("ERROR GETTING MESSAGES FOR AGENT %S: %S", agent_id, e)
        raise HTTPException(status_code=500, detail=str(e)) from e


async def x_get_messages_for_agent__mutmut_39(request: Request, agent_id: str) -> dict[str, Any]:
    try:
        if not state.message_storage:
            return {"agent_id": agent_id, "count": 0, "messages": [], "timestamp": datetime.now(UTC).isoformat()}
        messages = await state.message_storage.get_messages_by_receiver(agent_id, 100, 0)
        return {"agent_id": agent_id, "count": len(messages), "messages": messages, "timestamp": datetime.now(UTC).isoformat()}
    except Exception as e:
        logger.error("Error getting messages for agent %s: %s", agent_id, e)
        raise HTTPException(status_code=None, detail=str(e)) from e


async def x_get_messages_for_agent__mutmut_40(request: Request, agent_id: str) -> dict[str, Any]:
    try:
        if not state.message_storage:
            return {"agent_id": agent_id, "count": 0, "messages": [], "timestamp": datetime.now(UTC).isoformat()}
        messages = await state.message_storage.get_messages_by_receiver(agent_id, 100, 0)
        return {"agent_id": agent_id, "count": len(messages), "messages": messages, "timestamp": datetime.now(UTC).isoformat()}
    except Exception as e:
        logger.error("Error getting messages for agent %s: %s", agent_id, e)
        raise HTTPException(status_code=500, detail=None) from e


async def x_get_messages_for_agent__mutmut_41(request: Request, agent_id: str) -> dict[str, Any]:
    try:
        if not state.message_storage:
            return {"agent_id": agent_id, "count": 0, "messages": [], "timestamp": datetime.now(UTC).isoformat()}
        messages = await state.message_storage.get_messages_by_receiver(agent_id, 100, 0)
        return {"agent_id": agent_id, "count": len(messages), "messages": messages, "timestamp": datetime.now(UTC).isoformat()}
    except Exception as e:
        logger.error("Error getting messages for agent %s: %s", agent_id, e)
        raise HTTPException(detail=str(e)) from e


async def x_get_messages_for_agent__mutmut_42(request: Request, agent_id: str) -> dict[str, Any]:
    try:
        if not state.message_storage:
            return {"agent_id": agent_id, "count": 0, "messages": [], "timestamp": datetime.now(UTC).isoformat()}
        messages = await state.message_storage.get_messages_by_receiver(agent_id, 100, 0)
        return {"agent_id": agent_id, "count": len(messages), "messages": messages, "timestamp": datetime.now(UTC).isoformat()}
    except Exception as e:
        logger.error("Error getting messages for agent %s: %s", agent_id, e)
        raise HTTPException(
            status_code=500,
        ) from e


async def x_get_messages_for_agent__mutmut_43(request: Request, agent_id: str) -> dict[str, Any]:
    try:
        if not state.message_storage:
            return {"agent_id": agent_id, "count": 0, "messages": [], "timestamp": datetime.now(UTC).isoformat()}
        messages = await state.message_storage.get_messages_by_receiver(agent_id, 100, 0)
        return {"agent_id": agent_id, "count": len(messages), "messages": messages, "timestamp": datetime.now(UTC).isoformat()}
    except Exception as e:
        logger.error("Error getting messages for agent %s: %s", agent_id, e)
        raise HTTPException(status_code=501, detail=str(e)) from e


async def x_get_messages_for_agent__mutmut_44(request: Request, agent_id: str) -> dict[str, Any]:
    try:
        if not state.message_storage:
            return {"agent_id": agent_id, "count": 0, "messages": [], "timestamp": datetime.now(UTC).isoformat()}
        messages = await state.message_storage.get_messages_by_receiver(agent_id, 100, 0)
        return {"agent_id": agent_id, "count": len(messages), "messages": messages, "timestamp": datetime.now(UTC).isoformat()}
    except Exception as e:
        logger.error("Error getting messages for agent %s: %s", agent_id, e)
        raise HTTPException(status_code=500, detail=str(None)) from e


mutants_x_get_messages_for_agent__mutmut["_mutmut_orig"] = x_get_messages_for_agent__mutmut_orig  # type: ignore # mutmut generated
mutants_x_get_messages_for_agent__mutmut["x_get_messages_for_agent__mutmut_1"] = x_get_messages_for_agent__mutmut_1  # type: ignore # mutmut generated
mutants_x_get_messages_for_agent__mutmut["x_get_messages_for_agent__mutmut_2"] = x_get_messages_for_agent__mutmut_2  # type: ignore # mutmut generated
mutants_x_get_messages_for_agent__mutmut["x_get_messages_for_agent__mutmut_3"] = x_get_messages_for_agent__mutmut_3  # type: ignore # mutmut generated
mutants_x_get_messages_for_agent__mutmut["x_get_messages_for_agent__mutmut_4"] = x_get_messages_for_agent__mutmut_4  # type: ignore # mutmut generated
mutants_x_get_messages_for_agent__mutmut["x_get_messages_for_agent__mutmut_5"] = x_get_messages_for_agent__mutmut_5  # type: ignore # mutmut generated
mutants_x_get_messages_for_agent__mutmut["x_get_messages_for_agent__mutmut_6"] = x_get_messages_for_agent__mutmut_6  # type: ignore # mutmut generated
mutants_x_get_messages_for_agent__mutmut["x_get_messages_for_agent__mutmut_7"] = x_get_messages_for_agent__mutmut_7  # type: ignore # mutmut generated
mutants_x_get_messages_for_agent__mutmut["x_get_messages_for_agent__mutmut_8"] = x_get_messages_for_agent__mutmut_8  # type: ignore # mutmut generated
mutants_x_get_messages_for_agent__mutmut["x_get_messages_for_agent__mutmut_9"] = x_get_messages_for_agent__mutmut_9  # type: ignore # mutmut generated
mutants_x_get_messages_for_agent__mutmut["x_get_messages_for_agent__mutmut_10"] = x_get_messages_for_agent__mutmut_10  # type: ignore # mutmut generated
mutants_x_get_messages_for_agent__mutmut["x_get_messages_for_agent__mutmut_11"] = x_get_messages_for_agent__mutmut_11  # type: ignore # mutmut generated
mutants_x_get_messages_for_agent__mutmut["x_get_messages_for_agent__mutmut_12"] = x_get_messages_for_agent__mutmut_12  # type: ignore # mutmut generated
mutants_x_get_messages_for_agent__mutmut["x_get_messages_for_agent__mutmut_13"] = x_get_messages_for_agent__mutmut_13  # type: ignore # mutmut generated
mutants_x_get_messages_for_agent__mutmut["x_get_messages_for_agent__mutmut_14"] = x_get_messages_for_agent__mutmut_14  # type: ignore # mutmut generated
mutants_x_get_messages_for_agent__mutmut["x_get_messages_for_agent__mutmut_15"] = x_get_messages_for_agent__mutmut_15  # type: ignore # mutmut generated
mutants_x_get_messages_for_agent__mutmut["x_get_messages_for_agent__mutmut_16"] = x_get_messages_for_agent__mutmut_16  # type: ignore # mutmut generated
mutants_x_get_messages_for_agent__mutmut["x_get_messages_for_agent__mutmut_17"] = x_get_messages_for_agent__mutmut_17  # type: ignore # mutmut generated
mutants_x_get_messages_for_agent__mutmut["x_get_messages_for_agent__mutmut_18"] = x_get_messages_for_agent__mutmut_18  # type: ignore # mutmut generated
mutants_x_get_messages_for_agent__mutmut["x_get_messages_for_agent__mutmut_19"] = x_get_messages_for_agent__mutmut_19  # type: ignore # mutmut generated
mutants_x_get_messages_for_agent__mutmut["x_get_messages_for_agent__mutmut_20"] = x_get_messages_for_agent__mutmut_20  # type: ignore # mutmut generated
mutants_x_get_messages_for_agent__mutmut["x_get_messages_for_agent__mutmut_21"] = x_get_messages_for_agent__mutmut_21  # type: ignore # mutmut generated
mutants_x_get_messages_for_agent__mutmut["x_get_messages_for_agent__mutmut_22"] = x_get_messages_for_agent__mutmut_22  # type: ignore # mutmut generated
mutants_x_get_messages_for_agent__mutmut["x_get_messages_for_agent__mutmut_23"] = x_get_messages_for_agent__mutmut_23  # type: ignore # mutmut generated
mutants_x_get_messages_for_agent__mutmut["x_get_messages_for_agent__mutmut_24"] = x_get_messages_for_agent__mutmut_24  # type: ignore # mutmut generated
mutants_x_get_messages_for_agent__mutmut["x_get_messages_for_agent__mutmut_25"] = x_get_messages_for_agent__mutmut_25  # type: ignore # mutmut generated
mutants_x_get_messages_for_agent__mutmut["x_get_messages_for_agent__mutmut_26"] = x_get_messages_for_agent__mutmut_26  # type: ignore # mutmut generated
mutants_x_get_messages_for_agent__mutmut["x_get_messages_for_agent__mutmut_27"] = x_get_messages_for_agent__mutmut_27  # type: ignore # mutmut generated
mutants_x_get_messages_for_agent__mutmut["x_get_messages_for_agent__mutmut_28"] = x_get_messages_for_agent__mutmut_28  # type: ignore # mutmut generated
mutants_x_get_messages_for_agent__mutmut["x_get_messages_for_agent__mutmut_29"] = x_get_messages_for_agent__mutmut_29  # type: ignore # mutmut generated
mutants_x_get_messages_for_agent__mutmut["x_get_messages_for_agent__mutmut_30"] = x_get_messages_for_agent__mutmut_30  # type: ignore # mutmut generated
mutants_x_get_messages_for_agent__mutmut["x_get_messages_for_agent__mutmut_31"] = x_get_messages_for_agent__mutmut_31  # type: ignore # mutmut generated
mutants_x_get_messages_for_agent__mutmut["x_get_messages_for_agent__mutmut_32"] = x_get_messages_for_agent__mutmut_32  # type: ignore # mutmut generated
mutants_x_get_messages_for_agent__mutmut["x_get_messages_for_agent__mutmut_33"] = x_get_messages_for_agent__mutmut_33  # type: ignore # mutmut generated
mutants_x_get_messages_for_agent__mutmut["x_get_messages_for_agent__mutmut_34"] = x_get_messages_for_agent__mutmut_34  # type: ignore # mutmut generated
mutants_x_get_messages_for_agent__mutmut["x_get_messages_for_agent__mutmut_35"] = x_get_messages_for_agent__mutmut_35  # type: ignore # mutmut generated
mutants_x_get_messages_for_agent__mutmut["x_get_messages_for_agent__mutmut_36"] = x_get_messages_for_agent__mutmut_36  # type: ignore # mutmut generated
mutants_x_get_messages_for_agent__mutmut["x_get_messages_for_agent__mutmut_37"] = x_get_messages_for_agent__mutmut_37  # type: ignore # mutmut generated
mutants_x_get_messages_for_agent__mutmut["x_get_messages_for_agent__mutmut_38"] = x_get_messages_for_agent__mutmut_38  # type: ignore # mutmut generated
mutants_x_get_messages_for_agent__mutmut["x_get_messages_for_agent__mutmut_39"] = x_get_messages_for_agent__mutmut_39  # type: ignore # mutmut generated
mutants_x_get_messages_for_agent__mutmut["x_get_messages_for_agent__mutmut_40"] = x_get_messages_for_agent__mutmut_40  # type: ignore # mutmut generated
mutants_x_get_messages_for_agent__mutmut["x_get_messages_for_agent__mutmut_41"] = x_get_messages_for_agent__mutmut_41  # type: ignore # mutmut generated
mutants_x_get_messages_for_agent__mutmut["x_get_messages_for_agent__mutmut_42"] = x_get_messages_for_agent__mutmut_42  # type: ignore # mutmut generated
mutants_x_get_messages_for_agent__mutmut["x_get_messages_for_agent__mutmut_43"] = x_get_messages_for_agent__mutmut_43  # type: ignore # mutmut generated
mutants_x_get_messages_for_agent__mutmut["x_get_messages_for_agent__mutmut_44"] = x_get_messages_for_agent__mutmut_44  # type: ignore # mutmut generated


@router.get("/discover")
@rate_limit(rate=200, per=60)
async def discover_agents(
    request: Request,
    capability: str | None = Query(None, description="Filter by capability"),
    agent_type: str | None = Query(None, description="Filter by agent type"),
    min_health_score: float = Query(0.0, description="Minimum health score"),
    limit: int = Query(50, description="Maximum results"),
) -> dict[str, Any]:
    """Discover agents by criteria"""
    try:
        if not state.agent_registry:
            raise HTTPException(status_code=503, detail="Agent registry not available")
        query: dict[str, Any] = {}
        if capability:
            query["capabilities"] = [capability]
        if agent_type:
            query["agent_type"] = agent_type
        if min_health_score > 0:
            query["min_health_score"] = min_health_score
        if limit:
            query["limit"] = limit
        agents = await state.agent_registry.discover_agents(query)
        return {
            "agents": [agent.to_dict() for agent in agents],
            "count": len(agents),
            "query": query,
            "timestamp": datetime.now(UTC).isoformat(),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error discovering agents: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/subscribe")
@rate_limit(rate=50, per=60)
async def subscribe_to_topic(request: Request, req: SubscribeRequest) -> dict[str, Any]:
    """Subscribe agent to topic"""
    try:
        if state.message_storage:
            {
                "agent_id": req.agent_id,
                "topic": req.topic,
                "filter": req.filter,
                "subscribed_at": datetime.now(UTC).isoformat(),
            }
            logger.info("Agent %s subscribed to topic %s", req.agent_id, req.topic)
        return {
            "status": "success",
            "agent_id": req.agent_id,
            "topic": req.topic,
            "subscribed_at": datetime.now(UTC).isoformat(),
        }
    except Exception as e:
        logger.error("Error subscribing to topic: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/broadcast")
@rate_limit(rate=50, per=60)
async def broadcast_message(request_http: Request, request: BroadcastRequest) -> dict[str, Any]:
    """Broadcast message to multiple agents"""
    try:
        if not state.communication_manager:
            raise HTTPException(status_code=503, detail="Communication manager not available")
        if not state.agent_registry:
            raise HTTPException(status_code=503, detail="Agent registry not available")
        from ..protocols.communication import AgentMessage, Priority

        try:
            message_type = MessageType(request.message_type)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid message type: {request.message_type}") from None
        try:
            priority = Priority(request.priority.lower())
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid priority: {request.priority}") from None
        query: dict[str, Any] = {}
        if request.agent_type:
            query["agent_type"] = request.agent_type
        if request.capabilities:
            query["capabilities"] = request.capabilities
        agents = await state.agent_registry.discover_agents(query)
        if not agents:
            return {
                "status": "success",
                "message": "No matching agents found",
                "recipients": [],
                "count": 0,
                "broadcast_at": datetime.now(UTC).isoformat(),
            }
        recipients = []
        for agent in agents:
            message = AgentMessage(
                sender_id="agent-coordinator",
                receiver_id=agent.agent_id,
                message_type=message_type,
                priority=priority,
                payload=request.payload,
            )
            message_data = {
                "sender_id": message.sender_id,
                "receiver_id": message.receiver_id,
                "message_type": message.message_type.value,
                "priority": message.priority.value,
                "payload": json.dumps(message.payload),
                "protocol": "broadcast",
                "timestamp": datetime.now(UTC).isoformat(),
            }
            if state.message_storage:
                await state.message_storage.store_message(message.id, message_data)
                recipients.append(agent.agent_id)
            if state.communication_manager:
                try:
                    await state.communication_manager.send_message("broadcast", message)
                except Exception:
                    pass
        return {
            "status": "success",
            "message": f"Broadcast sent to {len(recipients)} agents",
            "recipients": recipients,
            "count": len(recipients),
            "broadcast_at": datetime.now(UTC).isoformat(),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error broadcasting message: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/id/{message_id}")
@rate_limit(rate=200, per=60)
async def get_message(request: Request, message_id: str) -> dict[str, Any]:
    """Get a specific message by ID"""
    try:
        if not state.message_storage:
            raise HTTPException(status_code=503, detail="Message storage not available")
        message = await state.message_storage.get_message(message_id)
        if not message:
            raise HTTPException(status_code=404, detail=f"Message {message_id} not found")
        return {"status": "success", "message": message, "timestamp": datetime.now(UTC).isoformat()}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error retrieving message %s: %s", message_id, e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/load-balancer/stats")
@rate_limit(rate=200, per=60)
async def get_load_balancer_stats(request: Request) -> dict[str, Any]:
    """Get load balancer statistics"""
    try:
        if not state.load_balancer:
            raise HTTPException(status_code=503, detail="Load balancer not available")
        stats = state.load_balancer.get_load_balancing_stats()
        return {"status": "success", "stats": stats, "timestamp": datetime.now(UTC).isoformat()}
    except Exception as e:
        logger.error("Error getting load balancer stats: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/registry/stats")
@rate_limit(rate=200, per=60)
async def get_registry_stats(request: Request) -> dict[str, Any]:
    """Get agent registry statistics"""
    try:
        if not state.agent_registry:
            raise HTTPException(status_code=503, detail="Agent registry not available")
        stats = await state.agent_registry.get_registry_stats()
        return {"status": "success", "stats": stats, "timestamp": datetime.now(UTC).isoformat()}
    except Exception as e:
        logger.error("Error getting registry stats: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/agents/service/{service}")
@rate_limit(rate=200, per=60)
async def get_agents_by_service(request: Request, service: str) -> dict[str, Any]:
    """Get agents that provide a specific service"""
    try:
        if not state.agent_registry:
            raise HTTPException(status_code=503, detail="Agent registry not available")
        agents = await state.agent_registry.get_agents_by_service(service)
        return {
            "status": "success",
            "service": service,
            "agents": [agent.to_dict() for agent in agents],
            "count": len(agents),
            "timestamp": datetime.now(UTC).isoformat(),
        }
    except Exception as e:
        logger.error("Error getting agents by service: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/agents/capability/{capability}")
@rate_limit(rate=200, per=60)
async def get_agents_by_capability(request: Request, capability: str) -> dict[str, Any]:
    """Get agents that have a specific capability"""
    try:
        if not state.agent_registry:
            raise HTTPException(status_code=503, detail="Agent registry not available")
        agents = await state.agent_registry.get_agents_by_capability(capability)
        return {
            "status": "success",
            "capability": capability,
            "agents": [agent.to_dict() for agent in agents],
            "count": len(agents),
            "timestamp": datetime.now(UTC).isoformat(),
        }
    except Exception as e:
        logger.error("Error getting agents by capability: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.put("/load-balancer/strategy")
@rate_limit(rate=50, per=60)
async def set_load_balancing_strategy(
    request: Request, strategy: str = Query(..., description="Load balancing strategy")
) -> dict[str, Any]:
    """Set load balancing strategy"""
    try:
        if not state.load_balancer:
            raise HTTPException(status_code=503, detail="Load balancer not available")
        try:
            load_balancing_strategy = LoadBalancingStrategy(strategy.lower())
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid strategy: {strategy}") from None
        state.load_balancer.set_strategy(load_balancing_strategy)
        return {
            "status": "success",
            "message": f"Load balancing strategy set to {strategy}",
            "strategy": strategy,
            "updated_at": datetime.now(UTC).isoformat(),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error setting load balancing strategy: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/peers/add")
@rate_limit(rate=50, per=60)
async def add_peer(
    request: Request,
    agent_id: str = Query(..., description="Agent ID"),
    peer_id: str = Query(..., description="Peer agent ID"),
) -> dict[str, Any]:
    """Add a peer connection for an agent"""
    try:
        if not state.peer_storage:
            raise HTTPException(status_code=503, detail="Peer storage not available")
        success = await state.peer_storage.add_peer(agent_id, peer_id, {"connected_at": datetime.now(UTC).isoformat()})
        if success:
            return {
                "status": "success",
                "message": f"Peer {peer_id} added for agent {agent_id}",
                "agent_id": agent_id,
                "peer_id": peer_id,
                "connected_at": datetime.now(UTC).isoformat(),
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to add peer")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error adding peer: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/peers/remove")
@rate_limit(rate=50, per=60)
async def remove_peer(
    request: Request,
    agent_id: str = Query(..., description="Agent ID"),
    peer_id: str = Query(..., description="Peer agent ID"),
) -> dict[str, Any]:
    """Remove a peer connection for an agent"""
    try:
        if not state.peer_storage:
            raise HTTPException(status_code=503, detail="Peer storage not available")
        success = await state.peer_storage.remove_peer(agent_id, peer_id)
        if success:
            return {
                "status": "success",
                "message": f"Peer {peer_id} removed for agent {agent_id}",
                "agent_id": agent_id,
                "peer_id": peer_id,
                "removed_at": datetime.now(UTC).isoformat(),
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to remove peer")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error removing peer: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/peers/{agent_id}")
@rate_limit(rate=200, per=60)
async def get_agent_peers(request: Request, agent_id: str) -> dict[str, Any]:
    """Get all peers for a specific agent"""
    try:
        if not state.peer_storage:
            raise HTTPException(status_code=503, detail="Peer storage not available")
        peers = await state.peer_storage.get_agent_peers(agent_id)
        return {
            "status": "success",
            "agent_id": agent_id,
            "peers": peers,
            "count": len(peers),
            "timestamp": datetime.now(UTC).isoformat(),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error retrieving peers for agent %s: %s", agent_id, e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/peers")
@rate_limit(rate=200, per=60)
async def get_all_peers(request: Request) -> dict[str, Any]:
    """Get all peer connections in the system"""
    try:
        if not state.peer_storage:
            raise HTTPException(status_code=503, detail="Peer storage not available")
        connections = await state.peer_storage.get_all_peer_connections()
        total_peers = sum(len(peers) for peers in connections.values())
        return {
            "status": "success",
            "connections": connections,
            "total_agents": len(connections),
            "total_peers": total_peers,
            "timestamp": datetime.now(UTC).isoformat(),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error retrieving all peer connections: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e
