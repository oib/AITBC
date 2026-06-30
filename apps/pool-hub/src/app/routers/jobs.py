"""Job distribution routes for Pool Hub"""

from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from aitbc.rate_limiting import rate_limit

from ..registry import MinerRegistry
from ..registry.miner_registry import JobAssignment
from ..scoring import ScoringEngine

router = APIRouter(prefix="/jobs", tags=["jobs"])


class JobRequest(BaseModel):
    """Job request from coordinator"""

    job_id: str
    prompt: str
    model: str
    params: dict[str, Any] = {}
    priority: int = 0
    deadline: datetime | None = None
    reward: float = 0.0


class JobResult(BaseModel):
    """Job result from miner"""

    job_id: str
    miner_id: str
    status: str  # completed, failed
    result: str | None = None
    error: str | None = None
    metrics: dict[str, Any] = {}


def get_registry() -> MinerRegistry:
    return MinerRegistry()


def get_scoring() -> ScoringEngine:
    return ScoringEngine()


@router.post("/assign", response_model=JobAssignment)
@rate_limit(rate=50, per=60)
async def assign_job(
    request: Request,
    job: JobRequest,
    registry: Annotated[MinerRegistry, Depends(get_registry)],
    scoring: Annotated[ScoringEngine, Depends(get_scoring)],
) -> JobAssignment:
    """Assign a job to the best available miner."""
    # Find available miners with required capability
    available = await registry.list(status="available", capability=job.model, limit=100)

    if not available:
        raise HTTPException(status_code=503, detail="No miners available for this model")

    # Score and rank miners
    scored = await scoring.rank_miners(available, job)

    # Select best miner
    best_miner = scored[0]

    # Assign job
    await registry.assign_job(job_id=job.job_id, miner_id=best_miner.miner_id, deadline=job.deadline)

    return JobAssignment(
        job_id=job.job_id,
        miner_id=best_miner.miner_id,
        pool_id=best_miner.pool_id,
        model=job.model,
        assigned_at=datetime.now(UTC),
        deadline=job.deadline,
    )


@router.post("/result")
@rate_limit(rate=50, per=60)
async def submit_result(
    request: Request,
    result: JobResult,
    registry: Annotated[MinerRegistry, Depends(get_registry)],
    scoring: Annotated[ScoringEngine, Depends(get_scoring)],
) -> dict[str, Any]:
    """Submit job result and update miner stats (v0.6.7: reward distribution)."""
    miner = await registry.get(result.miner_id)
    if not miner:
        raise HTTPException(status_code=404, detail="Miner not found")

    # Update job status
    await registry.complete_job(job_id=result.job_id, miner_id=result.miner_id, status=result.status, metrics=result.metrics)

    # Update miner score based on result
    if result.status == "completed":
        await scoring.record_success(result.miner_id, result.metrics)
    else:
        await scoring.record_failure(result.miner_id, result.error)

    # v0.6.7: Reward distribution (feature-flagged)
    reward_tx_hash: str | None = None
    if result.status == "completed":
        try:
            from poolhub.clients.blockchain import PoolHubBlockchainClient
            from poolhub.settings import settings

            if settings.enable_reward_distribution:
                from aitbc.rewards import REWARD_PER_SHARE

                blockchain_client = PoolHubBlockchainClient(
                    rpc_url=settings.blockchain_rpc_url,
                    chain_id=settings.default_chain_id,
                )
                # Record contribution in reward policy
                shares = int(result.metrics.get("compute_seconds", REWARD_PER_SHARE))
                score = await scoring.calculate_score(miner)
                blockchain_client.record_contribution(miner_id=result.miner_id, score=score, shares=shares)
                # Submit reward transaction
                if miner.wallet_address:
                    tx_result = await blockchain_client.submit_reward_transaction(
                        miner_address=miner.wallet_address,
                        amount=shares,
                        job_id=result.job_id,
                    )
                    reward_tx_hash = tx_result.get("tx_hash")
        except Exception as e:
            import logging

            logging.getLogger(__name__).warning("Reward distribution failed: %s", e)

    return {"status": "recorded", "reward_tx_hash": reward_tx_hash}


@router.get("/pending", response_model=list[JobAssignment])
@rate_limit(rate=200, per=60)
async def get_pending_jobs(
    request: Request,
    pool_id: str | None,
    registry: Annotated[MinerRegistry, Depends(get_registry)],
    limit: int = 50,
) -> list[JobAssignment]:
    """Get pending jobs waiting for assignment."""
    return await registry.get_pending_jobs(pool_id=pool_id, limit=limit)


@router.get("/{job_id}", response_model=JobAssignment)
@rate_limit(rate=200, per=60)
async def get_job_status(
    request: Request, job_id: str, registry: Annotated[MinerRegistry, Depends(get_registry)]
) -> JobAssignment:
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
    registry: Annotated[MinerRegistry, Depends(get_registry)],
    scoring: Annotated[ScoringEngine, Depends(get_scoring)],
) -> dict[str, str]:
    """Reassign a failed or timed-out job to another miner."""
    job = await registry.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status not in ["failed", "timeout"]:
        raise HTTPException(status_code=400, detail="Can only reassign failed or timed-out jobs")

    # Find new miner (exclude previous)
    available = await registry.list(status="available", capability=job.model, exclude_miner=job.miner_id, limit=100)

    if not available:
        raise HTTPException(status_code=503, detail="No alternative miners available")

    scored = await scoring.rank_miners(available, job)
    new_miner = scored[0]

    await registry.reassign_job(job_id, new_miner.miner_id)

    return {"job_id": job_id, "new_miner_id": new_miner.miner_id, "status": "reassigned"}
