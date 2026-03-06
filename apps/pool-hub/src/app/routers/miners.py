"""Miner management routes for Pool Hub"""

from fastapi import APIRouter, HTTPException, Depends, Query
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel

from ..registry import MinerRegistry
from ..scoring import ScoringEngine

router = APIRouter(prefix="/miners", tags=["miners"])


class MinerRegistration(BaseModel):
    """Miner registration request"""
    miner_id: str
    pool_id: str
    capabilities: List[str]
    gpu_info: dict
    endpoint: Optional[str] = None
    max_concurrent_jobs: int = 1


class MinerStatus(BaseModel):
    """Miner status update"""
    miner_id: str
    status: str  # available, busy, maintenance, offline
    current_jobs: int = 0
    gpu_utilization: float = 0.0
    memory_used_gb: float = 0.0


class MinerInfo(BaseModel):
    """Miner information response"""
    miner_id: str
    pool_id: str
    capabilities: List[str]
    status: str
    score: float
    jobs_completed: int
    uptime_percent: float
    registered_at: datetime
    last_heartbeat: datetime


# Dependency injection
def get_registry() -> MinerRegistry:
    return MinerRegistry()


def get_scoring() -> ScoringEngine:
    return ScoringEngine()


@router.post("/register", response_model=MinerInfo)
async def register_miner(
    registration: MinerRegistration,
    registry: MinerRegistry = Depends(get_registry)
):
    """Register a new miner with the pool hub."""
    try:
        miner = await registry.register(
            miner_id=registration.miner_id,
            pool_id=registration.pool_id,
            capabilities=registration.capabilities,
            gpu_info=registration.gpu_info,
            endpoint=registration.endpoint,
            max_concurrent_jobs=registration.max_concurrent_jobs
        )
        return miner
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{miner_id}/heartbeat")
async def miner_heartbeat(
    miner_id: str,
    status: MinerStatus,
    registry: MinerRegistry = Depends(get_registry)
):
    """Update miner heartbeat and status."""
    miner = await registry.get(miner_id)
    if not miner:
        raise HTTPException(status_code=404, detail="Miner not found")
    
    await registry.update_status(
        miner_id=miner_id,
        status=status.status,
        current_jobs=status.current_jobs,
        gpu_utilization=status.gpu_utilization,
        memory_used_gb=status.memory_used_gb
    )
    return {"status": "ok"}


@router.get("/{miner_id}", response_model=MinerInfo)
async def get_miner(
    miner_id: str,
    registry: MinerRegistry = Depends(get_registry)
):
    """Get miner information."""
    miner = await registry.get(miner_id)
    if not miner:
        raise HTTPException(status_code=404, detail="Miner not found")
    return miner


@router.get("/", response_model=List[MinerInfo])
async def list_miners(
    pool_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    capability: Optional[str] = Query(None),
    limit: int = Query(50, le=100),
    registry: MinerRegistry = Depends(get_registry)
):
    """List miners with optional filters."""
    return await registry.list(
        pool_id=pool_id,
        status=status,
        capability=capability,
        limit=limit
    )


@router.delete("/{miner_id}")
async def unregister_miner(
    miner_id: str,
    registry: MinerRegistry = Depends(get_registry)
):
    """Unregister a miner from the pool hub."""
    miner = await registry.get(miner_id)
    if not miner:
        raise HTTPException(status_code=404, detail="Miner not found")
    
    await registry.unregister(miner_id)
    return {"status": "unregistered"}


@router.get("/{miner_id}/score")
async def get_miner_score(
    miner_id: str,
    registry: MinerRegistry = Depends(get_registry),
    scoring: ScoringEngine = Depends(get_scoring)
):
    """Get miner's current score and ranking."""
    miner = await registry.get(miner_id)
    if not miner:
        raise HTTPException(status_code=404, detail="Miner not found")
    
    score = await scoring.calculate_score(miner)
    rank = await scoring.get_rank(miner_id)
    
    return {
        "miner_id": miner_id,
        "score": score,
        "rank": rank,
        "components": await scoring.get_score_breakdown(miner)
    }


@router.post("/{miner_id}/capabilities")
async def update_capabilities(
    miner_id: str,
    capabilities: List[str],
    registry: MinerRegistry = Depends(get_registry)
):
    """Update miner capabilities."""
    miner = await registry.get(miner_id)
    if not miner:
        raise HTTPException(status_code=404, detail="Miner not found")
    
    await registry.update_capabilities(miner_id, capabilities)
    return {"status": "updated", "capabilities": capabilities}
