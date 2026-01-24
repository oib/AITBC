"""Pool management routes for Pool Hub"""

from fastapi import APIRouter, HTTPException, Depends, Query
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel

from ..registry import MinerRegistry

router = APIRouter(prefix="/pools", tags=["pools"])


class PoolCreate(BaseModel):
    """Pool creation request"""
    pool_id: str
    name: str
    description: Optional[str] = None
    operator: str
    fee_percent: float = 1.0
    min_payout: float = 10.0
    payout_schedule: str = "daily"  # daily, weekly, threshold


class PoolInfo(BaseModel):
    """Pool information response"""
    pool_id: str
    name: str
    description: Optional[str]
    operator: str
    fee_percent: float
    min_payout: float
    payout_schedule: str
    miner_count: int
    total_hashrate: float
    jobs_completed_24h: int
    earnings_24h: float
    created_at: datetime


class PoolStats(BaseModel):
    """Pool statistics"""
    pool_id: str
    miner_count: int
    active_miners: int
    total_jobs: int
    jobs_24h: int
    total_earnings: float
    earnings_24h: float
    avg_response_time_ms: float
    uptime_percent: float


def get_registry() -> MinerRegistry:
    return MinerRegistry()


@router.post("/", response_model=PoolInfo)
async def create_pool(
    pool: PoolCreate,
    registry: MinerRegistry = Depends(get_registry)
):
    """Create a new mining pool."""
    try:
        created = await registry.create_pool(
            pool_id=pool.pool_id,
            name=pool.name,
            description=pool.description,
            operator=pool.operator,
            fee_percent=pool.fee_percent,
            min_payout=pool.min_payout,
            payout_schedule=pool.payout_schedule
        )
        return created
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{pool_id}", response_model=PoolInfo)
async def get_pool(
    pool_id: str,
    registry: MinerRegistry = Depends(get_registry)
):
    """Get pool information."""
    pool = await registry.get_pool(pool_id)
    if not pool:
        raise HTTPException(status_code=404, detail="Pool not found")
    return pool


@router.get("/", response_model=List[PoolInfo])
async def list_pools(
    limit: int = Query(50, le=100),
    offset: int = Query(0),
    registry: MinerRegistry = Depends(get_registry)
):
    """List all pools."""
    return await registry.list_pools(limit=limit, offset=offset)


@router.get("/{pool_id}/stats", response_model=PoolStats)
async def get_pool_stats(
    pool_id: str,
    registry: MinerRegistry = Depends(get_registry)
):
    """Get pool statistics."""
    pool = await registry.get_pool(pool_id)
    if not pool:
        raise HTTPException(status_code=404, detail="Pool not found")
    
    return await registry.get_pool_stats(pool_id)


@router.get("/{pool_id}/miners")
async def get_pool_miners(
    pool_id: str,
    status: Optional[str] = Query(None),
    limit: int = Query(50, le=100),
    registry: MinerRegistry = Depends(get_registry)
):
    """Get miners in a pool."""
    pool = await registry.get_pool(pool_id)
    if not pool:
        raise HTTPException(status_code=404, detail="Pool not found")
    
    return await registry.list(pool_id=pool_id, status=status, limit=limit)


@router.put("/{pool_id}")
async def update_pool(
    pool_id: str,
    updates: dict,
    registry: MinerRegistry = Depends(get_registry)
):
    """Update pool settings."""
    pool = await registry.get_pool(pool_id)
    if not pool:
        raise HTTPException(status_code=404, detail="Pool not found")
    
    allowed_fields = ["name", "description", "fee_percent", "min_payout", "payout_schedule"]
    filtered = {k: v for k, v in updates.items() if k in allowed_fields}
    
    await registry.update_pool(pool_id, filtered)
    return {"status": "updated"}


@router.delete("/{pool_id}")
async def delete_pool(
    pool_id: str,
    registry: MinerRegistry = Depends(get_registry)
):
    """Delete a pool (must have no miners)."""
    pool = await registry.get_pool(pool_id)
    if not pool:
        raise HTTPException(status_code=404, detail="Pool not found")
    
    miners = await registry.list(pool_id=pool_id, limit=1)
    if miners:
        raise HTTPException(
            status_code=409,
            detail="Cannot delete pool with active miners"
        )
    
    await registry.delete_pool(pool_id)
    return {"status": "deleted"}
