from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from aitbc import get_logger
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response
from fastapi.responses import JSONResponse

from .. import state
from ..auth.jwt_handler import api_key_manager, jwt_handler
from ..auth.middleware import get_current_user, require_role
from ..auth.permissions import Permission, Role, permission_manager
from ..ai.advanced_ai import ai_integration
from ..ai.realtime_learning import learning_system
from ..consensus.distributed_consensus import distributed_consensus
from ..models import AgentRegistrationRequest, AgentStatusUpdate, MessageRequest, TaskSubmission, BroadcastRequest
from ..monitoring.alerting import alert_manager
from ..monitoring.prometheus_metrics import metrics_registry, performance_monitor
from ..protocols.communication import MessageType, create_protocol
from ..protocols.message_types import create_task_message
from ..routing.agent_discovery import create_agent_info
from ..routing.load_balancer import LoadBalancingStrategy, TaskPriority

logger = get_logger(__name__)
router = APIRouter()

# Send message
@router.post("/messages/send")
async def send_message(request: MessageRequest):
    """Send message to agent"""
    try:
        if not state.communication_manager:
            raise HTTPException(status_code=503, detail="Communication manager not available")

        from ..protocols.communication import AgentMessage, Priority

        # Validate protocol
        valid_protocols = ["hierarchical", "peer_to_peer", "broadcast"]
        protocol = request.protocol.lower()
        if protocol not in valid_protocols:
            raise HTTPException(status_code=400, detail=f"Invalid protocol: {request.protocol}. Valid protocols: {', '.join(valid_protocols)}")

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

        # Create message
        message = AgentMessage(
            sender_id="agent-coordinator",
            receiver_id=request.receiver_id,
            message_type=message_type,
            priority=priority,
            payload=request.payload
        )

        # Send message with specified protocol
        success = await state.communication_manager.send_message(protocol, message)

        if success:
            # Store message in Redis for history
            if state.message_storage:
                message_data = {
                    "message_id": message.id,
                    "sender_id": message.sender_id,
                    "receiver_id": message.receiver_id,
                    "message_type": message.message_type.value,
                    "priority": message.priority.value,
                    "payload": json.dumps(message.payload),
                    "protocol": protocol,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
                await state.message_storage.store_message(message.id, message_data)

            return {
                "status": "success",
                "message": "Message sent successfully",
                "message_id": message.id,
                "receiver_id": request.receiver_id,
                "protocol": protocol,
                "sent_at": datetime.now(timezone.utc).isoformat()
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to send message")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending message: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Broadcast message
@router.post("/messages/broadcast")
async def broadcast_message(request: BroadcastRequest):
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
                "broadcast_at": datetime.now(timezone.utc).isoformat()
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

            success = await state.communication_manager.send_message("broadcast", message)
            if success:
                recipients.append(agent.agent_id)

        return {
            "status": "success",
            "message": f"Broadcast sent to {len(recipients)} agents",
            "recipients": recipients,
            "count": len(recipients),
            "broadcast_at": datetime.now(timezone.utc).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error broadcasting message: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Get message history
@router.get("/messages/history")
async def get_message_history(
    sender_id: Optional[str] = Query(None, description="Filter by sender ID"),
    receiver_id: Optional[str] = Query(None, description="Filter by receiver ID"),
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

        return {
            "status": "success",
            "messages": messages,
            "count": len(messages),
            "limit": limit,
            "offset": offset,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving message history: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Get specific message
@router.get("/messages/{message_id}")
async def get_message(message_id: str):
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
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving message {message_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Load balancer statistics
@router.get("/load-balancer/stats")
async def get_load_balancer_stats():
    """Get load balancer statistics"""
    try:
        if not state.load_balancer:
            raise HTTPException(status_code=503, detail="Load balancer not available")
        
        stats = state.load_balancer.get_load_balancing_stats()
        
        return {
            "status": "success",
            "stats": stats,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error getting load balancer stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Registry statistics
@router.get("/registry/stats")
async def get_registry_stats():
    """Get agent registry statistics"""
    try:
        if not state.agent_registry:
            raise HTTPException(status_code=503, detail="Agent registry not available")
        
        stats = await state.agent_registry.get_registry_stats()
        
        return {
            "status": "success",
            "stats": stats,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error getting registry stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Get agents by service
@router.get("/agents/service/{service}")
async def get_agents_by_service(service: str):
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
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error getting agents by service: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Get agents by capability
@router.get("/agents/capability/{capability}")
async def get_agents_by_capability(capability: str):
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
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error getting agents by capability: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Set load balancing strategy
@router.put("/load-balancer/strategy")
async def set_load_balancing_strategy(strategy: str = Query(..., description="Load balancing strategy")):
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
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error setting load balancing strategy: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Peer management endpoints
@router.post("/peers/add")
async def add_peer(agent_id: str = Query(..., description="Agent ID"), peer_id: str = Query(..., description="Peer agent ID")):
    """Add a peer connection for an agent"""
    try:
        from ..storage.message_storage import PeerStorage
        
        if not state.peer_storage:
            raise HTTPException(status_code=503, detail="Peer storage not available")

        success = await state.peer_storage.add_peer(agent_id, peer_id, {"connected_at": datetime.now(timezone.utc).isoformat()})

        if success:
            return {
                "status": "success",
                "message": f"Peer {peer_id} added for agent {agent_id}",
                "agent_id": agent_id,
                "peer_id": peer_id,
                "connected_at": datetime.now(timezone.utc).isoformat()
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to add peer")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding peer: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/peers/remove")
async def remove_peer(agent_id: str = Query(..., description="Agent ID"), peer_id: str = Query(..., description="Peer agent ID")):
    """Remove a peer connection for an agent"""
    try:
        from ..storage.message_storage import PeerStorage
        
        if not state.peer_storage:
            raise HTTPException(status_code=503, detail="Peer storage not available")

        success = await state.peer_storage.remove_peer(agent_id, peer_id)

        if success:
            return {
                "status": "success",
                "message": f"Peer {peer_id} removed for agent {agent_id}",
                "agent_id": agent_id,
                "peer_id": peer_id,
                "removed_at": datetime.now(timezone.utc).isoformat()
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to remove peer")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error removing peer: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/peers/{agent_id}")
async def get_agent_peers(agent_id: str):
    """Get all peers for a specific agent"""
    try:
        from ..storage.message_storage import PeerStorage
        
        if not state.peer_storage:
            raise HTTPException(status_code=503, detail="Peer storage not available")

        peers = await state.peer_storage.get_agent_peers(agent_id)

        return {
            "status": "success",
            "agent_id": agent_id,
            "peers": peers,
            "count": len(peers),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving peers for agent {agent_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/peers")
async def get_all_peers():
    """Get all peer connections in the system"""
    try:
        from ..storage.message_storage import PeerStorage
        
        if not state.peer_storage:
            raise HTTPException(status_code=503, detail="Peer storage not available")

        connections = await state.peer_storage.get_all_peer_connections()

        total_peers = sum(len(peers) for peers in connections.values())

        return {
            "status": "success",
            "connections": connections,
            "total_agents": len(connections),
            "total_peers": total_peers,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving all peer connections: {e}")
        raise HTTPException(status_code=500, detail=str(e))
