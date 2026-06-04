import json
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from aitbc import get_logger
from aitbc.rate_limiting import rate_limit

from .. import state
from ..encryption import EncryptedMessage, get_encryptor
from ..models import BroadcastRequest, MessageRequest
from ..protocols.communication import MessageType
from ..routing.load_balancer import LoadBalancingStrategy

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1/agent", tags=["agent-messaging"])


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

# Send encrypted message
@router.post("/messages/send")
@rate_limit(rate=50, per=60)
async def send_encrypted_message(request: Request, req: SendMessageRequest):
    """Send encrypted message to agent"""
    try:
        encryptor = get_encryptor()

        # Prepare message content
        message_content = {
            "content": req.content,
            "message_type": req.message_type,
            "timestamp": datetime.now(UTC).isoformat()
        }

        if req.encrypt:
            # Encrypt message
            encrypted_msg = encryptor.encrypt_message(
                message=message_content,
                sender_id=req.sender,
                recipient_id=req.recipient
            )

            if not encrypted_msg:
                raise HTTPException(status_code=500, detail="Failed to encrypt message")

            message_data = encrypted_msg.to_dict()
            message_data["encrypted"] = True
        else:
            # Send unencrypted
            message_data = {
                "sender": req.sender,
                "recipient": req.recipient,
                "content": req.content,
                "message_type": req.message_type,
                "encrypted": False,
                "priority": req.priority,
                "timestamp": datetime.now(UTC).isoformat()
            }

        # Store in message storage
        if state.message_storage:
            message_id = f"msg_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}_{req.sender[:8]}"
            await state.message_storage.store_message(message_id, message_data)

        return {
            "status": "success",
            "message_id": message_id if state.message_storage else "in-memory",
            "sender": req.sender,
            "recipient": req.recipient,
            "encrypted": req.encrypt,
            "sent_at": datetime.now(UTC).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending encrypted message: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Get inbox
@router.get("/messages/inbox")
@rate_limit(rate=200, per=60)
async def get_inbox(
    request: Request,
    agent_id: str = Query(..., description="Agent ID"),
    limit: int = Query(100, description="Maximum messages"),
    unread_only: bool = Query(False, description="Only unread messages")
):
    """Get agent's inbox"""
    try:
        if not state.message_storage:
            # Return empty inbox if no storage
            return {
                "agent_id": agent_id,
                "messages": [],
                "count": 0,
                "timestamp": datetime.now(UTC).isoformat()
            }

        messages = await state.message_storage.get_messages_by_receiver(agent_id, limit, 0)

        # Filter for unread if requested
        if unread_only:
            messages = [m for m in messages if not m.get("read", False)]

        return {
            "agent_id": agent_id,
            "messages": messages,
            "count": len(messages),
            "timestamp": datetime.now(UTC).isoformat()
        }

    except Exception as e:
        logger.error(f"Error getting inbox: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Discover agents
@router.get("/discover")
@rate_limit(rate=200, per=60)
async def discover_agents(
    request: Request,
    capability: str | None = Query(None, description="Filter by capability"),
    agent_type: str | None = Query(None, description="Filter by agent type"),
    min_health_score: float = Query(0.0, description="Minimum health score"),
    limit: int = Query(50, description="Maximum results")
):
    """Discover agents by criteria"""
    try:
        if not state.agent_registry:
            raise HTTPException(status_code=503, detail="Agent registry not available")

        query = {}
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
            "timestamp": datetime.now(UTC).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error discovering agents: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Subscribe to topic
@router.post("/subscribe")
@rate_limit(rate=50, per=60)
async def subscribe_to_topic(request: Request, req: SubscribeRequest):
    """Subscribe agent to topic"""
    try:
        # Store subscription in Redis
        if state.message_storage:
            subscription_data = {
                "agent_id": req.agent_id,
                "topic": req.topic,
                "filter": req.filter,
                "subscribed_at": datetime.now(UTC).isoformat()
            }
            subscription_key = f"subscription:{req.agent_id}:{req.topic}"
            # Note: This would need a store_subscription method in message_storage
            # For now, just return success
            logger.info(f"Agent {req.agent_id} subscribed to topic {req.topic}")

        return {
            "status": "success",
            "agent_id": req.agent_id,
            "topic": req.topic,
            "subscribed_at": datetime.now(UTC).isoformat()
        }

    except Exception as e:
        logger.error(f"Error subscribing to topic: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Broadcast message
@router.post("/messages/broadcast")
@rate_limit(rate=50, per=60)
async def broadcast_message(
    request_http: Request, request: BroadcastRequest
):
    """Broadcast message to multiple agents"""
    try:
        if not state.communication_manager:
            raise HTTPException(status_code=503, detail="Communication manager not available")

        if not state.agent_registry:
            raise HTTPException(status_code=503, detail="Agent registry not available")

        from ..protocols.communication import AgentMessage, Priority

        # Convert message type
        try:
            message_type = MessageType(request.message_type)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid message type: {request.message_type}")

        # Convert priority
        try:
            priority = Priority(request.priority.lower())
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid priority: {request.priority}")

        # Build discovery query for filtering
        query = {}
        if request.agent_type:
            query["agent_type"] = request.agent_type
        if request.capabilities:
            query["capabilities"] = request.capabilities

        # Discover target agents
        agents = await state.agent_registry.discover_agents(query)

        if not agents:
            return {
                "status": "success",
                "message": "No matching agents found",
                "recipients": [],
                "count": 0,
                "broadcast_at": datetime.now(UTC).isoformat()
            }

        # Send broadcast to each agent
        recipients = []
        for agent in agents:
            message = AgentMessage(
                sender_id="agent-coordinator",
                receiver_id=agent.agent_id,
                message_type=message_type,
                priority=priority,
                payload=request.payload
            )

            # Store in Redis first (always)
            message_data = {
                "sender_id": message.sender_id,
                "receiver_id": message.receiver_id,
                "message_type": message.message_type.value,
                "priority": message.priority.value,
                "payload": json.dumps(message.payload),
                "protocol": "broadcast",
                "timestamp": datetime.now(UTC).isoformat()
            }

            if state.message_storage:
                await state.message_storage.store_message(message.id, message_data)
                recipients.append(agent.agent_id)

            # Optionally try to send via protocol (for real-time notification)
            if state.communication_manager:
                try:
                    await state.communication_manager.send_message("broadcast", message)
                except Exception:
                    pass  # Protocol send is optional

        return {
            "status": "success",
            "message": f"Broadcast sent to {len(recipients)} agents",
            "recipients": recipients,
            "count": len(recipients),
            "broadcast_at": datetime.now(UTC).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error broadcasting message: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Get message history
@router.get("/messages/history")
@rate_limit(rate=200, per=60)
async def get_message_history(
    request: Request,
    sender_id: str | None = Query(None, description="Filter by sender ID"),
    receiver_id: str | None = Query(None, description="Filter by receiver ID"),
    limit: int = Query(100, description="Maximum number of messages"),
    offset: int = Query(0, description="Offset for pagination")
):
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

        # Get total count
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
            "timestamp": datetime.now(UTC).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving message history: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Get specific message
@router.get("/messages/{message_id}")
@rate_limit(rate=200, per=60)
async def get_message(
    request: Request, message_id: str
):
    """Get a specific message by ID"""
    try:
        if not state.message_storage:
            raise HTTPException(status_code=503, detail="Message storage not available")

        message = await state.message_storage.get_message(message_id)

        if not message:
            raise HTTPException(status_code=404, detail=f"Message {message_id} not found")

        return {
            "status": "success",
            "message": message,
            "timestamp": datetime.now(UTC).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving message {message_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Load balancer statistics
@router.get("/load-balancer/stats")
@rate_limit(rate=200, per=60)
async def get_load_balancer_stats(
    request: Request
):
    """Get load balancer statistics"""
    try:
        if not state.load_balancer:
            raise HTTPException(status_code=503, detail="Load balancer not available")

        stats = state.load_balancer.get_load_balancing_stats()

        return {
            "status": "success",
            "stats": stats,
            "timestamp": datetime.now(UTC).isoformat()
        }

    except Exception as e:
        logger.error(f"Error getting load balancer stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Registry statistics
@router.get("/registry/stats")
@rate_limit(rate=200, per=60)
async def get_registry_stats(
    request: Request
):
    """Get agent registry statistics"""
    try:
        if not state.agent_registry:
            raise HTTPException(status_code=503, detail="Agent registry not available")

        stats = await state.agent_registry.get_registry_stats()

        return {
            "status": "success",
            "stats": stats,
            "timestamp": datetime.now(UTC).isoformat()
        }

    except Exception as e:
        logger.error(f"Error getting registry stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Get agents by service
@router.get("/agents/service/{service}")
@rate_limit(rate=200, per=60)
async def get_agents_by_service(
    request: Request, service: str
):
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
            "timestamp": datetime.now(UTC).isoformat()
        }

    except Exception as e:
        logger.error(f"Error getting agents by service: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Get agents by capability
@router.get("/agents/capability/{capability}")
@rate_limit(rate=200, per=60)
async def get_agents_by_capability(
    request: Request, capability: str
):
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
            "timestamp": datetime.now(UTC).isoformat()
        }

    except Exception as e:
        logger.error(f"Error getting agents by capability: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Set load balancing strategy
@router.put("/load-balancer/strategy")
@rate_limit(rate=50, per=60)
async def set_load_balancing_strategy(
    request: Request, strategy: str = Query(..., description="Load balancing strategy")
):
    """Set load balancing strategy"""
    try:
        if not state.load_balancer:
            raise HTTPException(status_code=503, detail="Load balancer not available")

        try:
            load_balancing_strategy = LoadBalancingStrategy(strategy.lower())
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid strategy: {strategy}")

        state.load_balancer.set_strategy(load_balancing_strategy)

        return {
            "status": "success",
            "message": f"Load balancing strategy set to {strategy}",
            "strategy": strategy,
            "updated_at": datetime.now(UTC).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error setting load balancing strategy: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Peer management endpoints
@router.post("/peers/add")
@rate_limit(rate=50, per=60)
async def add_peer(
    request: Request, agent_id: str = Query(..., description="Agent ID"), peer_id: str = Query(..., description="Peer agent ID")
):
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
                "connected_at": datetime.now(UTC).isoformat()
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to add peer")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding peer: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/peers/remove")
@rate_limit(rate=50, per=60)
async def remove_peer(
    request: Request, agent_id: str = Query(..., description="Agent ID"), peer_id: str = Query(..., description="Peer agent ID")
):
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
                "removed_at": datetime.now(UTC).isoformat()
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to remove peer")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error removing peer: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/peers/{agent_id}")
@rate_limit(rate=200, per=60)
async def get_agent_peers(
    request: Request, agent_id: str
):
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
            "timestamp": datetime.now(UTC).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving peers for agent {agent_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/peers")
@rate_limit(rate=200, per=60)
async def get_all_peers(
    request: Request
):
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
            "timestamp": datetime.now(UTC).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving all peer connections: {e}")
        raise HTTPException(status_code=500, detail=str(e))
