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
from ..models import AgentRegistrationRequest, AgentStatusUpdate, MessageRequest, TaskSubmission
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
        
        # Send message
        success = await state.communication_manager.send_message("hierarchical", message)
        
        if success:
            return {
                "status": "success",
                "message": "Message sent successfully",
                "message_id": message.id,
                "receiver_id": request.receiver_id,
                "sent_at": datetime.now(timezone.utc).isoformat()
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to send message")
            
    except Exception as e:
        logger.error(f"Error sending message: {e}")
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
