# mypy: ignore-errors
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from aitbc import get_logger
from aitbc.rate_limiting import rate_limit

from .. import state
from ..models import AgentRegistrationRequest, AgentStatusUpdate
from ..routing.agent_discovery import create_agent_info

logger = get_logger(__name__)
router = APIRouter()

# Agent registration
@router.post("/agents/register")
@rate_limit(rate=50, per=60)
async def register_agent(
    request_http: Request, request: AgentRegistrationRequest
):
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
                "registered_at": datetime.now(UTC).isoformat()
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
@rate_limit(rate=200, per=60)
async def discover_agents(
    request: Request, query: dict[str, Any]
):
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
            "timestamp": datetime.now(UTC).isoformat()
        }

    except Exception as e:
        logger.error(f"Error discovering agents: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Get agent by ID
@router.get("/agents/{agent_id}")
@rate_limit(rate=200, per=60)
async def get_agent(
    request: Request, agent_id: str
):
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
            "timestamp": datetime.now(UTC).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting agent: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Update agent status
@router.put("/agents/{agent_id}/status")
@rate_limit(rate=50, per=60)
async def update_agent_status(
    request: Request, agent_id: str, request_status: AgentStatusUpdate
):
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
                "updated_at": datetime.now(UTC).isoformat()
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to update agent status")

    except Exception as e:
        logger.error(f"Error updating agent status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Agent heartbeat
@router.post("/agents/{agent_id}/heartbeat")
@rate_limit(rate=100, per=60)
async def agent_heartbeat(
    request: Request, agent_id: str
):
    """Receive heartbeat from agent"""
    try:
        if not state.agent_registry:
            raise HTTPException(status_code=503, detail="Agent registry not available")

        from ..routing.agent_discovery import AgentStatus

        # Update heartbeat timestamp and mark as active
        success = await state.agent_registry.update_agent_status(
            agent_id,
            AgentStatus.ACTIVE,
            {}
        )

        if success:
            return {
                "status": "success",
                "message": f"Heartbeat received from {agent_id}",
                "agent_id": agent_id,
                "heartbeat_at": datetime.now(UTC).isoformat()
            }
        else:
            raise HTTPException(status_code=404, detail="Agent not found")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing heartbeat: {e}")
        raise HTTPException(status_code=500, detail=str(e))
