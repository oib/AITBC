"""
Island-related RPC endpoints.
"""

from typing import Any, Dict
from fastapi import HTTPException
from pydantic import BaseModel

from ..logger import get_logger
from ..services.island_manager import get_island_manager

_logger = get_logger(__name__)


class JoinIslandRequest(BaseModel):
    """Request model for joining an island"""
    island_id: str
    island_name: str
    chain_id: str
    role: str = "compute-provider"
    is_hub: bool = False


class JoinIslandResponse(BaseModel):
    """Response model for joining an island"""
    success: bool
    island_id: str
    status: str
    message: str


class LeaveIslandRequest(BaseModel):
    """Request model for leaving an island"""
    island_id: str


class LeaveIslandResponse(BaseModel):
    """Response model for leaving an island"""
    success: bool
    island_id: str
    status: str
    message: str


class BridgeRequestRequest(BaseModel):
    """Request model for requesting a bridge"""
    target_island_id: str


class BridgeRequestResponse(BaseModel):
    """Response model for bridge request"""
    success: bool
    request_id: str
    target_island_id: str
    status: str
    message: str


async def join_island(request: JoinIslandRequest) -> JoinIslandResponse:
    """
    Join an island for edge compute operations.
    Calls IslandManager.join_island to register the node as a member of the specified island.
    """
    island_manager = get_island_manager()
    if island_manager is None:
        raise HTTPException(status_code=503, detail="Island manager not available")
    
    success = island_manager.join_island(
        island_id=request.island_id,
        island_name=request.island_name,
        chain_id=request.chain_id,
        is_hub=request.is_hub
    )
    
    if success:
        return JoinIslandResponse(
            success=True,
            island_id=request.island_id,
            status="joined",
            message=f"Successfully joined island {request.island_id}"
        )
    else:
        return JoinIslandResponse(
            success=False,
            island_id=request.island_id,
            status="failed",
            message=f"Failed to join island {request.island_id} (may already be a member)"
        )


async def leave_island(request: LeaveIslandRequest) -> LeaveIslandResponse:
    """
    Leave an island.
    Calls IslandManager.leave_island to remove the node from the specified island.
    """
    island_manager = get_island_manager()
    if island_manager is None:
        raise HTTPException(status_code=503, detail="Island manager not available")
    
    success = island_manager.leave_island(request.island_id)
    
    if success:
        return LeaveIslandResponse(
            success=True,
            island_id=request.island_id,
            status="left",
            message=f"Successfully left island {request.island_id}"
        )
    else:
        return LeaveIslandResponse(
            success=False,
            island_id=request.island_id,
            status="failed",
            message=f"Failed to leave island {request.island_id} (may not be a member)"
        )


async def list_islands() -> Dict[str, Any]:
    """
    List all islands that the node is a member of.
    Calls IslandManager.get_all_islands to retrieve island memberships.
    """
    island_manager = get_island_manager()
    if island_manager is None:
        raise HTTPException(status_code=503, detail="Island manager not available")
    
    islands = island_manager.get_all_islands()
    
    return {
        "islands": [
            {
                "island_id": island.island_id,
                "island_name": island.island_name,
                "chain_id": island.chain_id,
                "status": island.status.value,
                "role": getattr(island, 'role', 'unknown'),
                "peer_count": island.peer_count,
                "is_hub": island.is_hub,
                "joined_at": island.joined_at
            }
            for island in islands
        ],
        "total": len(islands)
    }


async def get_island(island_id: str) -> Dict[str, Any]:
    """
    Get details about a specific island.
    Calls IslandManager.get_island_info to retrieve island membership details.
    """
    island_manager = get_island_manager()
    if island_manager is None:
        raise HTTPException(status_code=503, detail="Island manager not available")
    
    island = island_manager.get_island_info(island_id)
    
    if island is None:
        raise HTTPException(status_code=404, detail=f"Island {island_id} not found")
    
    return {
        "island_id": island.island_id,
        "island_name": island.island_name,
        "chain_id": island.chain_id,
        "status": island.status.value,
        "role": getattr(island, 'role', 'unknown'),
        "peer_count": island.peer_count,
        "is_hub": island.is_hub,
        "joined_at": island.joined_at
    }


async def request_bridge(request: BridgeRequestRequest) -> BridgeRequestResponse:
    """
    Request a bridge to another island for cross-island communication.
    Calls IslandManager.request_bridge to initiate a bridge request.
    """
    island_manager = get_island_manager()
    if island_manager is None:
        raise HTTPException(status_code=503, detail="Island manager not available")
    
    request_id = island_manager.request_bridge(request.target_island_id)
    
    if request_id:
        return BridgeRequestResponse(
            success=True,
            request_id=request_id,
            target_island_id=request.target_island_id,
            status="pending",
            message=f"Bridge request {request_id} submitted for {request.target_island_id}"
        )
    else:
        return BridgeRequestResponse(
            success=False,
            request_id="",
            target_island_id=request.target_island_id,
            status="failed",
            message=f"Failed to request bridge to {request.target_island_id} (may already be a member)"
        )
