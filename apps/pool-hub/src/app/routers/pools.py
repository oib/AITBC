"""Pool management routes for Pool Hub"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from aitbc.rate_limiting import rate_limit

from ..registry import MinerRegistry
from ..registry.miner_registry import MinerInfo, PoolInfo

router = APIRouter(prefix="/pools", tags=["pools"])


class PoolCreate(BaseModel):
    """Pool creation request"""

    pool_id: str
    name: str
    description: str | None = None
    operator: str
    fee_percent: float = 1.0
    min_payout: float = 10.0
    payout_schedule: str = "daily"  # daily, weekly, threshold


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
@rate_limit(rate=50, per=60)
async def create_pool(
    request: Request, pool: PoolCreate, registry: Annotated[MinerRegistry, Depends(get_registry)]
) -> PoolInfo:
    """Create a new mining pool."""
    try:
        created = await registry.create_pool(
            pool_id=pool.pool_id,
            name=pool.name,
            description=pool.description,
            operator=pool.operator,
            fee_percent=pool.fee_percent,
            min_payout=pool.min_payout,
            payout_schedule=pool.payout_schedule,
        )
        return created
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/{pool_id}", response_model=PoolInfo)
@rate_limit(rate=200, per=60)
async def get_pool(request: Request, pool_id: str, registry: Annotated[MinerRegistry, Depends(get_registry)]) -> PoolInfo:
    """Get pool information."""
    pool = await registry.get_pool(pool_id)
    if not pool:
        raise HTTPException(status_code=404, detail="Pool not found")
    return pool


@router.get("/", response_model=list[PoolInfo])
@rate_limit(rate=200, per=60)
async def list_pools(
    request: Request,
    registry: Annotated[MinerRegistry, Depends(get_registry)],
    limit: int = 50,
    offset: int = 0,
) -> list[PoolInfo]:
    """List all pools."""
    return await registry.list_pools(limit=limit, offset=offset)


@router.get("/{pool_id}/stats", response_model=PoolStats)
@rate_limit(rate=200, per=60)
async def get_pool_stats(
    request: Request, pool_id: str, registry: Annotated[MinerRegistry, Depends(get_registry)]
) -> PoolStats:
    """Get pool statistics."""
    pool = await registry.get_pool(pool_id)
    if not pool:
        raise HTTPException(status_code=404, detail="Pool not found")

    stats = await registry.get_pool_stats(pool_id)
    return PoolStats(**stats)


@router.get("/{pool_id}/miners", response_model=list[MinerInfo])
@rate_limit(rate=200, per=60)
async def get_pool_miners(
    request: Request,
    pool_id: str,
    registry: Annotated[MinerRegistry, Depends(get_registry)],
    status: str | None = None,
    limit: int = 50,
) -> list[MinerInfo]:
    """Get miners in a pool."""
    pool = await registry.get_pool(pool_id)
    if not pool:
        raise HTTPException(status_code=404, detail="Pool not found")

    return await registry.list(pool_id=pool_id, status=status, limit=limit)


@router.put("/{pool_id}")
@rate_limit(rate=50, per=60)
async def update_pool(
    request: Request, pool_id: str, updates: dict[str, Any], registry: Annotated[MinerRegistry, Depends(get_registry)]
) -> dict[str, str]:
    """Update pool settings."""
    pool = await registry.get_pool(pool_id)
    if not pool:
        raise HTTPException(status_code=404, detail="Pool not found")

    allowed_fields = ["name", "description", "fee_percent", "min_payout", "payout_schedule"]
    filtered = {k: v for k, v in updates.items() if k in allowed_fields}

    await registry.update_pool(pool_id, filtered)
    return {"status": "updated"}


@router.delete("/{pool_id}")
@rate_limit(rate=50, per=60)
async def delete_pool(
    request: Request, pool_id: str, registry: Annotated[MinerRegistry, Depends(get_registry)]
) -> dict[str, str]:
    """Delete a pool (must have no miners)."""
    pool = await registry.get_pool(pool_id)
    if not pool:
        raise HTTPException(status_code=404, detail="Pool not found")

    miners = await registry.list(pool_id=pool_id, limit=1)
    if miners:
        raise HTTPException(status_code=409, detail="Cannot delete pool with active miners")

    await registry.delete_pool(pool_id)
    return {"status": "deleted"}
