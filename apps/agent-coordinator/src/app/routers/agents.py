from datetime import datetime, UTC
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

# Agent registration
@router.post("/agents/register")
async def register_agent(request: AgentRegistrationRequest):
    """Register a new agent"""
    try:
        if not state.agent_registry:
            raise HTTPException(status_code=503, detail="Agent registry not available")
        
        # Create agent info with validation
        try:
            agent_info = create_agent_info(
                agent_id=request.agent_id,
                agent_type=request.agent_type,
                capabilities=request.capabilities,
                services=request.services,
                endpoints=request.endpoints
            )
            agent_info.metadata = request.metadata
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
        
        # Register agent
        success = await state.agent_registry.register_agent(agent_info)
        
        if success:
            return {
                "status": "success",
                "message": f"Agent {request.agent_id} registered successfully",
                "agent_id": request.agent_id,
                "registered_at": datetime.now(datetime.UTC).isoformat()
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to register agent")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error registering agent: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Agent discovery
@router.post("/agents/discover")
async def discover_agents(query: Dict[str, Any]):
    """Discover agents based on criteria"""
    try:
        if not state.agent_registry:
            raise HTTPException(status_code=503, detail="Agent registry not available")
        
        agents = await state.agent_registry.discover_agents(query)
        
        return {
            "status": "success",
            "query": query,
            "agents": [agent.to_dict() for agent in agents],
            "count": len(agents),
            "timestamp": datetime.now(datetime.UTC).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error discovering agents: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Get agent by ID
@router.get("/agents/{agent_id}")
async def get_agent(agent_id: str):
    """Get agent information by ID"""
    try:
        if not state.agent_registry:
            raise HTTPException(status_code=503, detail="Agent registry not available")
        
        agent = await state.agent_registry.get_agent_by_id(agent_id)
        
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")
        
        return {
            "status": "success",
            "agent": agent.to_dict(),
            "timestamp": datetime.now(datetime.UTC).isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting agent: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Update agent status
@router.put("/agents/{agent_id}/status")
async def update_agent_status(agent_id: str, request: AgentStatusUpdate):
    """Update agent status"""
    try:
        if not state.agent_registry:
            raise HTTPException(status_code=503, detail="Agent registry not available")
        
        from ..routing.agent_discovery import AgentStatus
        
        success = await state.agent_registry.update_agent_status(
            agent_id,
            AgentStatus(request.status),
            request.load_metrics
        )
        
        if success:
            return {
                "status": "success",
                "message": f"Agent {agent_id} status updated",
                "agent_id": agent_id,
                "new_status": request.status,
                "updated_at": datetime.now(datetime.UTC).isoformat()
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to update agent status")
            
    except Exception as e:
        logger.error(f"Error updating agent status: {e}")
        raise HTTPException(status_code=500, detail=str(e))
