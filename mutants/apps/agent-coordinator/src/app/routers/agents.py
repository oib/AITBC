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


from mutmut.mutation.trampoline import wrap_in_trampoline as _mutmut_mutated, MutantDict


@router.post("/agents/register")
@rate_limit(rate=50, per=60)
async def register_agent(request_http: Request, request: AgentRegistrationRequest) -> dict[str, Any]:
    """Register a new agent"""
    try:
        if not state.agent_registry:
            raise HTTPException(status_code=503, detail="Agent registry not available")
        try:
            agent_info = create_agent_info(
                agent_id=request.agent_id,
                agent_type=request.agent_type,
                capabilities=request.capabilities,
                services=request.services,
                endpoints=request.endpoints,
            )
            agent_info.metadata = request.metadata
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e)) from None
        success = await state.agent_registry.register_agent(agent_info)
        if success:
            return {
                "status": "success",
                "message": f"Agent {request.agent_id} registered successfully",
                "agent_id": request.agent_id,
                "registered_at": datetime.now(UTC).isoformat(),
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to register agent")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error registering agent: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/agents/discover")
@rate_limit(rate=200, per=60)
async def discover_agents(request: Request, query: dict[str, Any]) -> dict[str, Any]:
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
            "timestamp": datetime.now(UTC).isoformat(),
        }
    except Exception as e:
        logger.error("Error discovering agents: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/agents/{agent_id}")
@rate_limit(rate=200, per=60)
async def get_agent(request: Request, agent_id: str) -> dict[str, Any]:
    """Get agent information by ID"""
    try:
        if not state.agent_registry:
            raise HTTPException(status_code=503, detail="Agent registry not available")
        agent = await state.agent_registry.get_agent_by_id(agent_id)
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")
        return {"status": "success", "agent": agent.to_dict(), "timestamp": datetime.now(UTC).isoformat()}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error getting agent: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.put("/agents/{agent_id}/status")
@rate_limit(rate=50, per=60)
async def update_agent_status(request: Request, agent_id: str, request_status: AgentStatusUpdate) -> dict[str, Any]:
    """Update agent status"""
    try:
        if not state.agent_registry:
            raise HTTPException(status_code=503, detail="Agent registry not available")
        from ..routing.agent_discovery import AgentStatus

        success = await state.agent_registry.update_agent_status(
            agent_id, AgentStatus(request_status.status), request_status.load_metrics
        )
        if success:
            return {
                "status": "success",
                "message": f"Agent {agent_id} status updated",
                "agent_id": agent_id,
                "new_status": request_status.status,
                "updated_at": datetime.now(UTC).isoformat(),
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to update agent status")
    except Exception as e:
        logger.error("Error updating agent status: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/agents/{agent_id}/heartbeat")
@rate_limit(rate=100, per=60)
async def agent_heartbeat(request: Request, agent_id: str) -> dict[str, Any]:
    """Receive heartbeat from agent"""
    try:
        if not state.agent_registry:
            raise HTTPException(status_code=503, detail="Agent registry not available")
        from ..routing.agent_discovery import AgentStatus

        success = await state.agent_registry.update_agent_status(agent_id, AgentStatus.ACTIVE, {})
        if success:
            return {
                "status": "success",
                "message": f"Heartbeat received from {agent_id}",
                "agent_id": agent_id,
                "heartbeat_at": datetime.now(UTC).isoformat(),
            }
        else:
            raise HTTPException(status_code=404, detail="Agent not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error processing heartbeat: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e
