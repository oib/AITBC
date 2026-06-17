from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from aitbc.aitbc_logging import get_logger
from aitbc.rate_limiting import rate_limit

from ..deps import get_miner_id, require_miner_key
from ..schemas import AssignedJob, JobFailSubmit, JobResultSubmit, JobState, MinerHeartbeat, MinerRegister, PollRequest
from ..services import JobService, MinerService
from ..services.receipts import ReceiptService
from ..storage import get_session

logger = get_logger(__name__)
router = APIRouter(tags=["miner"])


@router.post("/miners/register", summary="Register or update miner")
@rate_limit(rate=50, per=60)
async def register(
    req: MinerRegister,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    miner_id: Annotated[str, Depends(get_miner_id())],
    api_key: Annotated[str, Depends(require_miner_key())],
) -> dict[str, Any]:
    service = MinerService(session)
    record = service.register(miner_id, req)
    return {"status": "ok", "session_token": record.session_token}


@router.post("/miners/heartbeat", summary="Send miner heartbeat")
@rate_limit(rate=100, per=60)
async def heartbeat(
    req: MinerHeartbeat,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    miner_id: Annotated[str, Depends(get_miner_id())],
    api_key: Annotated[str, Depends(require_miner_key())],
) -> dict[str, str]:
    try:
        MinerService(session).heartbeat(miner_id, req)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="miner not registered") from None
    return {"status": "ok"}


@router.post("/miners/poll", response_model=AssignedJob, summary="Poll for next job")
@rate_limit(rate=100, per=60)
async def poll(
    request: Request,
    req: PollRequest,
    session: Annotated[Session, Depends(get_session)],
    api_key: Annotated[str, Depends(require_miner_key())],
    miner_id: Annotated[str, Depends(get_miner_id())],
) -> AssignedJob | Response:
    job = MinerService(session).poll(miner_id, req.max_wait_seconds)
    if job is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    return job  # type: ignore[no-any-return]


@router.post("/miners/{job_id}/result", summary="Submit job result")
@rate_limit(rate=50, per=60)
async def submit_result(
    request: Request,
    job_id: str,
    req: JobResultSubmit,
    session: Annotated[Session, Depends(get_session)],
    miner_id: Annotated[str, Depends(get_miner_id())],
) -> dict[str, Any]:
    job_service = JobService(session)
    miner_service = MinerService(session)
    receipt_service = ReceiptService(session)  # type: ignore[arg-type]
    try:
        job = job_service.get_job(job_id)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found") from None
    job.result = req.result
    job.state = JobState.completed
    job.error = None
    metrics = dict(req.metrics or {})
    duration_ms = metrics.get("duration_ms")
    if duration_ms is None and job.requested_at:
        now = datetime.now(UTC)
        requested_at = job.requested_at if job.requested_at.tzinfo else job.requested_at.replace(tzinfo=UTC)
        duration_ms = int((now - requested_at).total_seconds() * 1000)
        metrics["duration_ms"] = duration_ms
    receipt = receipt_service.create_receipt(job, miner_id, req.result, metrics)
    job.receipt = receipt
    job.receipt_id = receipt["receipt_id"] if receipt else None
    session.add(job)
    session.commit()
    if job.payment_id and job.payment_status == "escrowed":
        from ..contexts.payments.services.payments import PaymentService

        payment_service = PaymentService(session)
        success = await payment_service.release_payment(job.id, job.payment_id, reason="Job completed successfully")
        if success:
            job.payment_status = "released"
            session.commit()
            logger.info("Auto-released payment %s for completed job %s", job.payment_id, job.id)
        else:
            logger.error("Failed to auto-release payment %s for job %s", job.payment_id, job.id)
    miner_service.release(
        miner_id, success=True, duration_ms=duration_ms, receipt_id=receipt["receipt_id"] if receipt else None
    )
    return {"status": "ok", "receipt": receipt}


@router.post("/miners/{job_id}/fail", summary="Submit job failure")
@rate_limit(rate=50, per=60)
async def submit_failure(
    request: Request,
    job_id: str,
    req: JobFailSubmit,
    session: Annotated[Session, Depends(get_session)],
    miner_id: Annotated[str, Depends(get_miner_id())],
) -> dict[str, str]:
    try:
        service = JobService(session)
        service.fail_job(job_id, miner_id, req.error_message)
        return {"status": "ok"}
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found") from None


@router.post("/miners/{miner_id}/jobs", summary="List jobs for a miner")
@rate_limit(rate=200, per=60)
async def list_miner_jobs(
    request: Request,
    miner_id: str,
    session: Annotated[Session, Depends(get_session)],
    api_key: Annotated[str, Depends(require_miner_key())],
    limit: int = 20,
    offset: int = 0,
    job_type: str | None = None,
    min_reward: float | None = None,
    job_status: str | None = None,
) -> dict[str, Any]:
    """List jobs assigned to a specific miner"""
    try:
        service = JobService(session)
        filters = {}
        if job_type:
            filters["job_type"] = job_type
        if job_status:
            try:
                filters["state"] = JobState(job_status.upper())
            except ValueError:
                pass
        jobs = service.list_jobs(client_id=miner_id, limit=limit, offset=offset, **filters)
        return {
            "jobs": [service.to_view(job) for job in jobs],
            "total": len(jobs),
            "limit": limit,
            "offset": offset,
            "miner_id": miner_id,
        }
    except Exception as e:
        logger.error("Error listing miner jobs: %s", e)
        return {"jobs": [], "total": 0, "limit": limit, "offset": offset, "miner_id": miner_id, "error": "Failed to list jobs"}


@router.post("/miners/{miner_id}/earnings", summary="Get miner earnings")
@rate_limit(rate=200, per=60)
async def get_miner_earnings(
    request: Request,
    miner_id: str,
    session: Annotated[Session, Depends(get_session)],
    api_key: Annotated[str, Depends(require_miner_key())],
    from_time: str | None = None,
    to_time: str | None = None,
) -> dict[str, Any]:
    """Get earnings for a specific miner"""
    try:
        earnings_data = {
            "miner_id": miner_id,
            "total_earnings": 0.0,
            "pending_earnings": 0.0,
            "completed_jobs": 0,
            "currency": "AITBC",
            "from_time": from_time,
            "to_time": to_time,
            "earnings_history": [],
        }
        return earnings_data
    except Exception as e:
        logger.error("Error getting miner earnings: %s", e)
        return {
            "miner_id": miner_id,
            "total_earnings": 0.0,
            "pending_earnings": 0.0,
            "completed_jobs": 0,
            "currency": "AITBC",
            "error": str(e),
        }


@router.put("/miners/{miner_id}/capabilities", summary="Update miner capabilities")
@rate_limit(rate=50, per=60)
async def update_miner_capabilities(
    request: Request,
    miner_id: str,
    req: MinerRegister,
    session: Annotated[Session, Depends(get_session)],
    api_key: Annotated[str, Depends(require_miner_key())],
) -> dict[str, Any]:
    """Update capabilities for a registered miner"""
    try:
        service = MinerService(session)
        record = service.register(miner_id, req)
        return {
            "miner_id": miner_id,
            "status": "updated",
            "capabilities": req.capabilities,
            "session_token": record.session_token,
        }
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="miner not found") from None
    except Exception as e:
        logger.error("Error updating miner capabilities: %s", e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)) from e


@router.delete("/miners/{miner_id}", summary="Deregister miner")
@rate_limit(rate=50, per=60)
async def deregister_miner(
    request: Request,
    miner_id: str,
    session: Annotated[Session, Depends(get_session)],
    api_key: Annotated[str, Depends(require_miner_key())],
) -> dict[str, str]:
    """Deregister a miner from the coordinator"""
    try:
        service = MinerService(session)
        service.deregister(miner_id)
        return {"miner_id": miner_id, "status": "deregistered"}
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="miner not found") from None
    except Exception as e:
        logger.error("Error deregistering miner: %s", e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)) from e


@router.post("/miners/{miner_id}/jobs/{job_id}/fail", summary="Report job failure")
@rate_limit(rate=50, per=60)
async def fail_job(
    request: Request,
    miner_id: str,
    job_id: str,
    fail_req: JobFailSubmit,
    session: Annotated[Session, Depends(get_session)],
    api_key: Annotated[str, Depends(require_miner_key())],
) -> dict[str, str]:
    """Report job failure"""
    try:
        job_service = JobService(session)
        job_service.fail_job(job_id, fail_req.error_message)
        return {"job_id": job_id, "status": "failed"}
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found") from None
    except Exception as e:
        logger.error("Error failing job %s: %s", job_id, e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)) from e


class FailJobRequest(BaseModel):
    error_message: str


class CompleteJobRequest(BaseModel):
    output: dict[str, Any]
    receipt: dict[str, Any] | None = None


@router.post("/miners/{miner_id}/jobs/{job_id}/complete", summary="Complete job execution")
@rate_limit(rate=50, per=60)
async def complete_job(
    request: Request,
    miner_id: str,
    job_id: str,
    complete_req: CompleteJobRequest,
    session: Annotated[Session, Depends(get_session)],
    api_key: Annotated[str, Depends(require_miner_key())],
) -> dict[str, Any]:
    """
    Complete a job by submitting execution results.

    This endpoint allows miners to submit the results of AI job execution,
    including the output and a verification receipt.
    """
    try:
        job_service = JobService(session)
        result = {"output": complete_req.output, "receipt": complete_req.receipt or {}}
        job = job_service.execute_job(job_id, result)
        logger.info(
            "Job %s completed by miner %s",
            job_id,
            miner_id,
            extra={"job_id": job_id, "miner_id": miner_id, "output_size": len(str(complete_req.output))},
        )
        return {
            "job_id": job_id,
            "status": "completed",
            "state": job.state.value,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            "receipt_hash": complete_req.receipt.get("hash", "")[:16] if complete_req.receipt else None,
        }
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found") from None
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except Exception as e:
        logger.error("Error completing job %s: %s", job_id, e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)) from e
