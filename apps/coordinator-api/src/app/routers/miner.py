from sqlalchemy.orm import Session
from typing import Annotated
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response, status, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from ..deps import require_miner_key, get_miner_id
from ..schemas import AssignedJob, JobFailSubmit, JobResultSubmit, JobState, MinerHeartbeat, MinerRegister, PollRequest
from ..services import JobService, MinerService
from ..services.receipts import ReceiptService
from ..config import settings
from ..storage import Annotated[Session, Depends(get_session)], get_session
from aitbc.logging import get_logger

logger = get_logger(__name__)
limiter = Limiter(key_func=get_remote_address)
router = APIRouter(tags=["miner"])


@router.post("/miners/register", summary="Register or update miner")
@limiter.limit(lambda: settings.rate_limit_miner_register)
async def register(
    req: MinerRegister,
    request: Request,
    session: Annotated[Session, Depends(get_session)] = Depends(),
    miner_id: str = Depends(get_miner_id()),
    api_key: str = Depends(require_miner_key()),
) -> dict[str, Any]:  # type: ignore[arg-type]
    service = MinerService(session)
    record = service.register(miner_id, req)
    return {"status": "ok", "session_token": record.session_token}

@router.post("/miners/heartbeat", summary="Send miner heartbeat")
@limiter.limit(lambda: settings.rate_limit_miner_heartbeat)
async def heartbeat(
    req: MinerHeartbeat,
    request: Request,
    session: Annotated[Session, Depends(get_session)] = Depends(),
    miner_id: str = Depends(get_miner_id()),
    api_key: str = Depends(require_miner_key()),
) -> dict[str, str]:  # type: ignore[arg-type]
    try:
        MinerService(session).heartbeat(miner_id, req)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="miner not registered")
    return {"status": "ok"}


# NOTE: until scheduling is fully implemented the poll endpoint performs a simple FIFO assignment.
@router.post("/miners/poll", response_model=AssignedJob, summary="Poll for next job")
async def poll(
    req: PollRequest,
    session: Annotated[Session, Depends(get_session)] = Depends(),
    miner_id: str = Depends(require_miner_key()),
) -> AssignedJob | Response:  # type: ignore[arg-type]
    job = MinerService(session).poll(miner_id, req.max_wait_seconds)
    if job is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    return job


@router.post("/miners/{job_id}/result", summary="Submit job result")
async def submit_result(
    job_id: str,
    req: JobResultSubmit,
    session: Annotated[Session, Depends(get_session)] = Depends(),
    miner_id: str = Depends(require_miner_key()),
) -> dict[str, Any]:  # type: ignore[arg-type]
    job_service = JobService(session)
    miner_service = MinerService(session)
    receipt_service = ReceiptService(session)
    try:
        job = job_service.get_job(job_id)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found")

    job.result = req.result
    job.state = JobState.completed
    job.error = None

    metrics = dict(req.metrics or {})
    duration_ms = metrics.get("duration_ms")
    if duration_ms is None and job.requested_at:
        duration_ms = int((datetime.utcnow() - job.requested_at).total_seconds() * 1000)
        metrics["duration_ms"] = duration_ms

    receipt = receipt_service.create_receipt(job, miner_id, req.result, metrics)
    job.receipt = receipt
    job.receipt_id = receipt["receipt_id"] if receipt else None
    session.add(job)
    session.commit()
    
    # Auto-release payment if job has payment
    if job.payment_id and job.payment_status == "escrowed":
        from ..services.payments import PaymentService
        payment_service = PaymentService(session)
        success = await payment_service.release_payment(
            job.id,
            job.payment_id,
            reason="Job completed successfully"
        )
        if success:
            job.payment_status = "released"
            session.commit()
            logger.info(f"Auto-released payment {job.payment_id} for completed job {job.id}")
        else:
            logger.error(f"Failed to auto-release payment {job.payment_id} for job {job.id}")
    
    miner_service.release(
        miner_id,
        success=True,
        duration_ms=duration_ms,
        receipt_id=receipt["receipt_id"] if receipt else None,
    )
    return {"status": "ok", "receipt": receipt}


@router.post("/miners/{job_id}/fail", summary="Submit job failure")
async def submit_failure(
    job_id: str,
    req: JobFailSubmit,
    session: Annotated[Session, Depends(get_session)] = Depends(),
    miner_id: str = Depends(require_miner_key()),
) -> dict[str, str]:  # type: ignore[arg-type]
    try:
        service = JobService(session)
        service.fail_job(job_id, miner_id, req.error_message)
        return {"status": "ok"}
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found")


@router.post("/miners/{miner_id}/jobs", summary="List jobs for a miner")
async def list_miner_jobs(
    miner_id: str,
    limit: int = 20,
    offset: int = 0,
    job_type: str | None = None,
    min_reward: float | None = None,
    job_status: str | None = None,
    session: Annotated[Session, Depends(get_session)] = Depends() = Annotated[Session, Depends(get_session)],
    api_key: str = Depends(require_miner_key()),
) -> dict[str, Any]:  # type: ignore[arg-type]
    """List jobs assigned to a specific miner"""
    try:
        service = JobService(session)
        
        # Build filters
        filters = {}
        if job_type:
            filters["job_type"] = job_type
        if job_status:
            try:
                filters["state"] = JobState(job_status.upper())
            except ValueError:
                pass  # Invalid status, ignore
        
        # Get jobs for this miner
        jobs = service.list_jobs(
            client_id=miner_id,  # Using client_id as miner_id for now
            limit=limit,
            offset=offset,
            **filters
        )
        
        return {
            "jobs": [service.to_view(job) for job in jobs],
            "total": len(jobs),
            "limit": limit,
            "offset": offset,
            "miner_id": miner_id
        }
    except Exception as e:
        logger.error(f"Error listing miner jobs: {e}")
        return {
            "jobs": [],
            "total": 0,
            "limit": limit,
            "offset": offset,
            "miner_id": miner_id,
            "error": str(e)
        }


@router.post("/miners/{miner_id}/earnings", summary="Get miner earnings")
async def get_miner_earnings(
    miner_id: str,
    from_time: str | None = None,
    to_time: str | None = None,
    session: Annotated[Session, Depends(get_session)] = Depends() = Annotated[Session, Depends(get_session)],
    api_key: str = Depends(require_miner_key()),
) -> dict[str, Any]:  # type: ignore[arg-type]
    """Get earnings for a specific miner"""
    try:
        # For now, return mock earnings data
        # In a full implementation, this would query payment records
        earnings_data = {
            "miner_id": miner_id,
            "total_earnings": 0.0,
            "pending_earnings": 0.0,
            "completed_jobs": 0,
            "currency": "AITBC",
            "from_time": from_time,
            "to_time": to_time,
            "earnings_history": []
        }
        
        return earnings_data
    except Exception as e:
        logger.error(f"Error getting miner earnings: {e}")
        return {
            "miner_id": miner_id,
            "total_earnings": 0.0,
            "pending_earnings": 0.0,
            "completed_jobs": 0,
            "currency": "AITBC",
            "error": str(e)
        }


@router.put("/miners/{miner_id}/capabilities", summary="Update miner capabilities")
async def update_miner_capabilities(
    miner_id: str,
    req: MinerRegister,
    session: Annotated[Session, Depends(get_session)] = Depends() = Annotated[Session, Depends(get_session)],
    api_key: str = Depends(require_miner_key()),
) -> dict[str, Any]:  # type: ignore[arg-type]
    """Update capabilities for a registered miner"""
    try:
        service = MinerService(session)
        record = service.register(miner_id, req)  # Re-use register to update
        return {
            "miner_id": miner_id,
            "status": "updated",
            "capabilities": req.capabilities,
            "session_token": record.session_token
        }
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="miner not found")
    except Exception as e:
        logger.error(f"Error updating miner capabilities: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.delete("/miners/{miner_id}", summary="Deregister miner")
async def deregister_miner(
    miner_id: str,
    session: Annotated[Session, Depends(get_session)] = Depends() = Annotated[Session, Depends(get_session)],
    api_key: str = Depends(require_miner_key()),
) -> dict[str, str]:  # type: ignore[arg-type]
    """Deregister a miner from the coordinator"""
    try:
        service = MinerService(session)
        service.deregister(miner_id)
        return {
            "miner_id": miner_id,
            "status": "deregistered"
        }
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="miner not found")
    except Exception as e:
        logger.error(f"Error deregistering miner: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
