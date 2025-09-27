from fastapi import APIRouter, Depends, HTTPException, status

from ..deps import require_admin_key
from ..services import JobService, MinerService
from ..storage import SessionDep

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/stats", summary="Get coordinator stats")
async def get_stats(session: SessionDep, admin_key: str = Depends(require_admin_key())) -> dict[str, int]:  # type: ignore[arg-type]
    service = JobService(session)
    from sqlmodel import func, select
    from ..domain import Job

    total_jobs = session.exec(select(func.count()).select_from(Job)).one()
    active_jobs = session.exec(select(func.count()).select_from(Job).where(Job.state.in_(["QUEUED", "RUNNING"]))).one()

    miner_service = MinerService(session)
    miners = miner_service.list_records()
    avg_job_duration = (
        sum(miner.average_job_duration_ms for miner in miners if miner.average_job_duration_ms) / max(len(miners), 1)
    )
    return {
        "total_jobs": int(total_jobs or 0),
        "active_jobs": int(active_jobs or 0),
        "online_miners": miner_service.online_count(),
        "avg_miner_job_duration_ms": avg_job_duration,
    }


@router.get("/jobs", summary="List jobs")
async def list_jobs(session: SessionDep, admin_key: str = Depends(require_admin_key())) -> dict[str, list[dict]]:  # type: ignore[arg-type]
    from ..domain import Job

    jobs = session.exec(select(Job).order_by(Job.requested_at.desc()).limit(100)).all()
    return {
        "items": [
            {
                "job_id": job.id,
                "state": job.state,
                "client_id": job.client_id,
                "assigned_miner_id": job.assigned_miner_id,
                "requested_at": job.requested_at.isoformat(),
            }
            for job in jobs
        ]
    }


@router.get("/miners", summary="List miners")
async def list_miners(session: SessionDep, admin_key: str = Depends(require_admin_key())) -> dict[str, list[dict]]:  # type: ignore[arg-type]
    miner_service = MinerService(session)
    miners = [
        {
            "miner_id": record.miner_id,
            "status": record.status,
            "inflight": record.inflight,
            "concurrency": record.concurrency,
            "region": record.region,
            "last_heartbeat": record.last_heartbeat.isoformat(),
            "average_job_duration_ms": record.average_job_duration_ms,
            "jobs_completed": record.jobs_completed,
            "jobs_failed": record.jobs_failed,
            "last_receipt_id": record.last_receipt_id,
        }
        for record in miner_service.list_records()
    ]
    return {"items": miners}
