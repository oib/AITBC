"""Job distribution routes for Pool Hub"""

from fastapi import APIRouter, HTTPException, Depends, Query
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel

from ..registry import MinerRegistry
from ..scoring import ScoringEngine

router = APIRouter(prefix="/jobs", tags=["jobs"])


class JobRequest(BaseModel):
    """Job request from coordinator"""
    job_id: str
    prompt: str
    model: str
    params: dict = {}
    priority: int = 0
    deadline: Optional[datetime] = None
    reward: float = 0.0


class JobAssignment(BaseModel):
    """Job assignment response"""
    job_id: str
    miner_id: str
    pool_id: str
    assigned_at: datetime
    deadline: Optional[datetime]


class JobResult(BaseModel):
    """Job result from miner"""
    job_id: str
    miner_id: str
    status: str  # completed, failed
    result: Optional[str] = None
    error: Optional[str] = None
    metrics: dict = {}


def get_registry() -> MinerRegistry:
    return MinerRegistry()


def get_scoring() -> ScoringEngine:
    return ScoringEngine()


@router.post("/assign", response_model=JobAssignment)
async def assign_job(
    job: JobRequest,
    registry: MinerRegistry = Depends(get_registry),
    scoring: ScoringEngine = Depends(get_scoring)
):
    """Assign a job to the best available miner."""
    # Find available miners with required capability
    available = await registry.list(
        status="available",
        capability=job.model,
        limit=100
    )
    
    if not available:
        raise HTTPException(
            status_code=503,
            detail="No miners available for this model"
        )
    
    # Score and rank miners
    scored = await scoring.rank_miners(available, job)
    
    # Select best miner
    best_miner = scored[0]
    
    # Assign job
    assignment = await registry.assign_job(
        job_id=job.job_id,
        miner_id=best_miner.miner_id,
        deadline=job.deadline
    )
    
    return JobAssignment(
        job_id=job.job_id,
        miner_id=best_miner.miner_id,
        pool_id=best_miner.pool_id,
        assigned_at=datetime.utcnow(),
        deadline=job.deadline
    )


@router.post("/result")
async def submit_result(
    result: JobResult,
    registry: MinerRegistry = Depends(get_registry),
    scoring: ScoringEngine = Depends(get_scoring)
):
    """Submit job result and update miner stats."""
    miner = await registry.get(result.miner_id)
    if not miner:
        raise HTTPException(status_code=404, detail="Miner not found")
    
    # Update job status
    await registry.complete_job(
        job_id=result.job_id,
        miner_id=result.miner_id,
        status=result.status,
        metrics=result.metrics
    )
    
    # Update miner score based on result
    if result.status == "completed":
        await scoring.record_success(result.miner_id, result.metrics)
    else:
        await scoring.record_failure(result.miner_id, result.error)
    
    return {"status": "recorded"}


@router.get("/pending")
async def get_pending_jobs(
    pool_id: Optional[str] = Query(None),
    limit: int = Query(50, le=100),
    registry: MinerRegistry = Depends(get_registry)
):
    """Get pending jobs waiting for assignment."""
    return await registry.get_pending_jobs(pool_id=pool_id, limit=limit)


@router.get("/{job_id}")
async def get_job_status(
    job_id: str,
    registry: MinerRegistry = Depends(get_registry)
):
    """Get job assignment status."""
    job = await registry.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post("/{job_id}/reassign")
async def reassign_job(
    job_id: str,
    registry: MinerRegistry = Depends(get_registry),
    scoring: ScoringEngine = Depends(get_scoring)
):
    """Reassign a failed or timed-out job to another miner."""
    job = await registry.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if job.status not in ["failed", "timeout"]:
        raise HTTPException(
            status_code=400,
            detail="Can only reassign failed or timed-out jobs"
        )
    
    # Find new miner (exclude previous)
    available = await registry.list(
        status="available",
        capability=job.model,
        exclude_miner=job.miner_id,
        limit=100
    )
    
    if not available:
        raise HTTPException(
            status_code=503,
            detail="No alternative miners available"
        )
    
    scored = await scoring.rank_miners(available, job)
    new_miner = scored[0]
    
    await registry.reassign_job(job_id, new_miner.miner_id)
    
    return {
        "job_id": job_id,
        "new_miner_id": new_miner.miner_id,
        "status": "reassigned"
    }
