"""Job distribution routes for Pool Hub"""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from aitbc.rate_limiting import rate_limit

from ..registry import MinerRegistry  # type: ignore[import-not-found]
from ..scoring import ScoringEngine  # type: ignore[import-not-found]

router = APIRouter(prefix="/jobs", tags=["jobs"])


class JobRequest(BaseModel):
    """Job request from coordinator"""
    job_id: str
    prompt: str
    model: str
    params: dict = {}
    priority: int = 0
    deadline: datetime | None = None
    reward: float = 0.0


class JobAssignment(BaseModel):
    """Job assignment response"""
    job_id: str
    miner_id: str
    pool_id: str
    assigned_at: datetime
    deadline: datetime | None


class JobResult(BaseModel):
    """Job result from miner"""
    job_id: str
    miner_id: str
    status: str  # completed, failed
    result: str | None = None
    error: str | None = None
    metrics: dict = {}


def get_registry() -> MinerRegistry:
    return MinerRegistry()


def get_scoring() -> ScoringEngine:
    return ScoringEngine()


@router.post("/assign", response_model=JobAssignment)
@rate_limit(rate=50, per=60)
async def assign_job(
    request: Request,
    job: JobRequest,
    registry: MinerRegistry = Depends(get_registry),
    scoring: ScoringEngine = Depends(get_scoring)
) -> JobAssignment:
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
        assigned_at=datetime.now(UTC),
        deadline=job.deadline
    )


@router.post("/result")
@rate_limit(rate=50, per=60)
async def submit_result(
    request: Request,
    result: JobResult,
    registry: MinerRegistry = Depends(get_registry),
    scoring: ScoringEngine = Depends(get_scoring)
) -> dict[str, str]:
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
@rate_limit(rate=200, per=60)
async def get_pending_jobs(
    request: Request,
    pool_id: str | None = Query(None),
    limit: int = Query(50, le=100),
    registry: MinerRegistry = Depends(get_registry)
) -> list:
    """Get pending jobs waiting for assignment."""
    return await registry.get_pending_jobs(pool_id=pool_id, limit=limit)  # type: ignore[no-any-return]


@router.get("/{job_id}")
@rate_limit(rate=200, per=60)
async def get_job_status(
    request: Request,
    job_id: str,
    registry: MinerRegistry = Depends(get_registry)
) -> object:
    """Get job assignment status."""
    job = await registry.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post("/{job_id}/reassign")
@rate_limit(rate=50, per=60)
async def reassign_job(
    request: Request,
    job_id: str,
    registry: MinerRegistry = Depends(get_registry),
    scoring: ScoringEngine = Depends(get_scoring)
) -> dict[str, str]:
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
