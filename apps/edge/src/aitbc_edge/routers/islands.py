"""Island operations router for Edge API Service"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..services.island_service import IslandService

router = APIRouter()


class JoinIslandRequest(BaseModel):
    """Request model for joining an island"""

    island_id: str
    island_name: str
    chain_id: str | list[str]
    role: str = Field(default="compute-provider")
    is_hub: bool = Field(default=False)
    region: str | None = Field(default=None)


class LeaveIslandRequest(BaseModel):
    """Request model for leaving an island"""

    island_id: str


class BridgeRequestRequest(BaseModel):
    """Request model for requesting a bridge"""

    target_island_id: str


def get_island_service() -> IslandService:
    """Dependency injection for island service"""
    return IslandService()


@router.post("/join")
async def join_island(
    request: JoinIslandRequest, svc: Annotated[IslandService, Depends(get_island_service)]
) -> dict[str, Any]:
    """Join an island"""
    result = await svc.join_island(
        island_id=request.island_id,
        island_name=request.island_name,
        chain_id=request.chain_id,
        role=request.role,
        is_hub=request.is_hub,
        region=request.region,
    )
    return result


@router.post("/leave")
async def leave_island(
    request: LeaveIslandRequest, svc: Annotated[IslandService, Depends(get_island_service)]
) -> dict[str, Any]:
    """Leave an island"""
    result = await svc.leave_island(request.island_id)
    return result


@router.get("/")
async def list_islands(svc: Annotated[IslandService, Depends(get_island_service)]) -> dict[str, Any]:
    """List all islands"""
    islands = await svc.list_islands()
    return {"islands": islands, "total": len(islands)}


@router.get("/{island_id}")
async def get_island(island_id: str, svc: Annotated[IslandService, Depends(get_island_service)]) -> dict[str, Any]:
    """Get island details"""
    island = await svc.get_island(island_id)
    if island is None:
        raise HTTPException(status_code=404, detail=f"Island {island_id} not found")
    return island


@router.get("/by-region/{region}")
async def list_memberships_by_region(
    region: str, svc: Annotated[IslandService, Depends(get_island_service)]
) -> dict[str, Any]:
    """List island memberships for a specific region (multi-region edge nodes)."""
    memberships = await svc.list_memberships_by_region(region)
    return {
        "region": region,
        "memberships": [
            {
                "island_id": m.island_id,
                "island_name": m.island_name,
                "chain_id": m.chain_id,
                "role": m.role,
                "status": m.status.value,
                "region": m.extra_data.get("region"),
            }
            for m in memberships
        ],
        "total": len(memberships),
    }


@router.post("/bridge")
async def request_bridge(
    request: BridgeRequestRequest, svc: Annotated[IslandService, Depends(get_island_service)]
) -> dict[str, Any]:
    """Request bridge to another island"""
    result = await svc.request_bridge(request.target_island_id)
    return result
