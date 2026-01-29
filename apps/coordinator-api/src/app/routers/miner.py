from datetime import datetime
from typing import Any
import logging

from fastapi import APIRouter, Depends, HTTPException, Response, status

from ..deps import require_miner_key
from ..schemas import AssignedJob, JobFailSubmit, JobResultSubmit, JobState, MinerHeartbeat, MinerRegister, PollRequest
from ..services import JobService, MinerService
from ..services.receipts import ReceiptService
from ..storage import SessionDep

logger = logging.getLogger(__name__)

router = APIRouter(tags=["miner"])


@router.post("/miners/register", summary="Register or update miner")
async def register(
    req: MinerRegister,
    session: SessionDep,
    miner_id: str = Depends(require_miner_key()),
) -> dict[str, Any]:  # type: ignore[arg-type]
    service = MinerService(session)
    record = service.register(miner_id, req)
    return {"status": "ok", "session_token": record.session_token}

@router.post("/miners/heartbeat", summary="Send miner heartbeat")
async def heartbeat(
    req: MinerHeartbeat,
    session: SessionDep,
    miner_id: str = Depends(require_miner_key()),
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
    session: SessionDep,
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
    session: SessionDep,
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

    receipt = await receipt_service.create_receipt(job, miner_id, req.result, metrics)
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
    session: SessionDep,
    miner_id: str = Depends(require_miner_key()),
) -> dict[str, str]:  # type: ignore[arg-type]
    job_service = JobService(session)
    miner_service = MinerService(session)
    try:
        job = job_service.get_job(job_id)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found")

    job.state = JobState.failed
    job.error = f"{req.error_code}: {req.error_message}"
    job.assigned_miner_id = miner_id
    session.add(job)
    session.commit()
    
    # Auto-refund payment if job has payment
    if job.payment_id and job.payment_status in ["pending", "escrowed"]:
        from ..services.payments import PaymentService
        payment_service = PaymentService(session)
        success = await payment_service.refund_payment(
            job.id,
            job.payment_id,
            reason=f"Job failed: {req.error_code}: {req.error_message}"
        )
        if success:
            job.payment_status = "refunded"
            session.commit()
            logger.info(f"Auto-refunded payment {job.payment_id} for failed job {job.id}")
        else:
            logger.error(f"Failed to auto-refund payment {job.payment_id} for job {job.id}")
    
    miner_service.release(miner_id, success=False)
    return {"status": "ok"}
