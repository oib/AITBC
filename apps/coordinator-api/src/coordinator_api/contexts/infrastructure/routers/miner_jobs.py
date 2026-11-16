from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, col, select
from aitbc_shared import JobPayment

from aitbc.aitbc_logging import get_logger
from aitbc.exceptions import AITBCError
from aitbc.rate_limiting import rate_limit

from ....auth import MinerDep
from ....custom_types import job_state_filter_help, parse_job_state_filter
from ....schemas import JobFailSubmit, MinerRegister
from ....services import JobService, MinerService
from ....contexts.reputation.services.reputation_service import ReputationService
from ...payments.acceptance import DISPUTED, PENDING_ACCEPTANCE
from ....storage import get_session

logger = get_logger(__name__)
# No tags here: miner.py includes this router into its own tags=["miner"]
# router, and APIRouter.tags concatenate on include_router — setting them
# again would publish every route with a duplicated "miner" tag.
router = APIRouter()

# Expected failure surface for the miner endpoints -- this router moves
# money (escrow release/refund, bond slashing, settlement retry), so the
# tuple is deliberately wider than the baseline: filesystem/JSON,
# data-shape (pydantic ValidationError is a ValueError), runtime,
# SQLAlchemy session errors, lazy in-function imports (reputation,
# bond-slashing, payment services), decimal parse failures
# (InvalidOperation is an ArithmeticError, not a ValueError), timestamp
# overflows, the aitbc error hierarchy, and HTTPException -- several arms
# below have no explicit ``except HTTPException`` and previously folded it
# into their error payload, so it stays in the tuple to keep money-path
# semantics identical. Handlers that DO re-raise HTTPException keep their
# explicit arms ahead of this tuple. BaseExceptions still propagate.
_OPS_ERRORS = (
    OSError,
    ValueError,
    KeyError,
    IndexError,
    TypeError,
    AttributeError,
    RuntimeError,
    OverflowError,
    ImportError,
    SQLAlchemyError,
    AITBCError,
    InvalidOperation,
    HTTPException,
)


@router.post("/miners/{miner_id}/jobs", summary="List jobs for a miner")
@rate_limit(rate=200, per=60)
async def list_miner_jobs(
    request: Request,
    miner_id: str,
    session: Annotated[Session, Depends(get_session)],
    user: MinerDep,
    limit: int = Query(default=20, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    job_type: str | None = None,
    min_reward: Decimal | None = None,
    job_status: str | None = None,
) -> dict[str, Any]:
    """List jobs assigned to a specific miner"""
    filters = {}
    if job_type:
        filters["job_type"] = job_type
    if job_status:
        # Parsed before the broad try below so an invalid value answers 400
        # instead of being swallowed into the generic error payload.
        try:
            state = parse_job_state_filter(job_status)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"invalid job_status filter {job_status!r} ({job_state_filter_help()})",
            ) from None
        if state is not None:
            filters["state"] = state.value
    if miner_id != user["sub"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="miner_id does not match authenticated miner")
    try:
        service = JobService(session)
        jobs = await run_in_threadpool(service.list_jobs, assigned_miner_id=miner_id, limit=limit, offset=offset, **filters)
        return {
            "jobs": service.to_views(jobs),
            "total": len(jobs),
            "limit": limit,
            "offset": offset,
            "miner_id": miner_id,
        }
    except _OPS_ERRORS as e:
        logger.error("Error listing miner jobs: %s", e)
        return {"jobs": [], "total": 0, "limit": limit, "offset": offset, "miner_id": miner_id, "error": "Failed to list jobs"}


@router.post("/miners/{miner_id}/earnings", summary="Get miner earnings")
@rate_limit(rate=200, per=60)
async def get_miner_earnings(
    request: Request,
    miner_id: str,
    session: Annotated[Session, Depends(get_session)],
    user: MinerDep,
    from_time: str | None = None,
    to_time: str | None = None,
) -> dict[str, Any]:
    """Get earnings for a specific miner"""
    if miner_id != user["sub"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="miner_id does not match authenticated miner")
    try:
        from decimal import Decimal
        from ...infrastructure.services.jobs import JobService

        job_service = JobService(session)
        start = datetime.fromisoformat(from_time).replace(tzinfo=None) if from_time else None
        end = datetime.fromisoformat(to_time).replace(tzinfo=None) if to_time else None
        completed_jobs = await run_in_threadpool(
            job_service.list_jobs,
            assigned_miner_id=miner_id,
            state="COMPLETED",
            limit=None,
            offset=0,
            completed_from=start,
            completed_to=end,
        )

        total_earnings = Decimal("0")
        pending_earnings = Decimal("0")
        paid_earnings = Decimal("0")
        history: list[dict[str, Any]] = []

        payment_ids = [j.payment_id for j in completed_jobs if j.payment_id]
        payments = {}
        if payment_ids:
            payments = {
                p.id: p
                for p in (
                    await run_in_threadpool(
                        lambda: session.execute(select(JobPayment).where(col(JobPayment.id).in_(payment_ids))).scalars().all()
                    )
                )
            }
        for job in completed_jobs:
            payment = payments.get(job.payment_id) if job.payment_id else None
            amount = payment.amount if payment else Decimal("0")
            token = payment.currency if payment else (job.payment_token or "AITBC")
            payment_status = payment.status if payment is not None else (job.payment_status or "unknown")
            if payment_status == "released":
                paid_earnings += amount
                total_earnings += amount
            elif payment_status in {"escrowed", PENDING_ACCEPTANCE, DISPUTED}:
                # G3: money that is locked but not yet paid out, whether it is still
                # running, waiting on the customer, or before an arbiter.
                pending_earnings += amount
            history.append(
                {
                    "job_id": job.id,
                    "amount": str(amount),
                    "currency": token,
                    "payment_status": payment_status,
                }
            )

        return {
            "miner_id": miner_id,
            # Strings, like earnings_history[].amount above: these are Decimal sums
            # of Numeric(20, 8) columns and float() would round them.
            "total_earnings": str(total_earnings),
            "pending_earnings": str(pending_earnings),
            "paid_earnings": str(paid_earnings),
            "completed_jobs": len(completed_jobs),
            "currency": "AITBC",
            "from_time": from_time,
            "to_time": to_time,
            "earnings_history": history[:20],
        }
    except HTTPException:
        raise
    except _OPS_ERRORS as e:
        logger.error("Error getting miner earnings: %s", e)
        raise HTTPException(status_code=500, detail="failed to compute miner earnings") from e


@router.put("/miners/{miner_id}/capabilities", summary="Update miner capabilities")
@rate_limit(rate=50, per=60)
async def update_miner_capabilities(
    request: Request,
    miner_id: str,
    req: MinerRegister,
    session: Annotated[Session, Depends(get_session)],
    user: MinerDep,
) -> dict[str, Any]:
    """Update capabilities for a registered miner"""
    if miner_id != user["sub"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="miner_id does not match authenticated miner")
    try:
        service = MinerService(session)
        record = await run_in_threadpool(service.register, user["sub"], req)
        return {
            "miner_id": miner_id,
            "status": "updated",
            "capabilities": req.capabilities,
            "session_token": record.session_token,
        }
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="miner not found") from None
    except _OPS_ERRORS as e:
        logger.error("Error updating miner capabilities: %s", e)
        logger.exception("Unhandled exception")

        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error") from e


@router.delete("/miners/{miner_id}", summary="Deregister miner")
@rate_limit(rate=50, per=60)
async def deregister_miner(
    request: Request,
    miner_id: str,
    session: Annotated[Session, Depends(get_session)],
    user: MinerDep,
) -> dict[str, str]:
    """Deregister a miner from the coordinator"""
    if miner_id != user["sub"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="miner_id does not match authenticated miner")
    try:
        service = MinerService(session)
        await run_in_threadpool(service.deregister, miner_id)
        return {"miner_id": miner_id, "status": "deregistered"}
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="miner not found") from None
    except _OPS_ERRORS as e:
        logger.error("Error deregistering miner: %s", e)
        logger.exception("Unhandled exception")

        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error") from e


@router.post("/miners/{miner_id}/jobs/{job_id}/fail", summary="Report job failure")
@rate_limit(rate=50, per=60)
async def fail_job(
    request: Request,
    miner_id: str,
    job_id: str,
    fail_req: JobFailSubmit,
    session: Annotated[Session, Depends(get_session)],
    user: MinerDep,
) -> dict[str, str]:
    """Report job failure"""
    if miner_id != user["sub"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="miner_id does not match authenticated miner")
    try:
        job_service = JobService(session)
        await run_in_threadpool(job_service.fail_job, job_id, user["sub"], fail_req.error_message)

        # Record the failure in the reputation service.
        try:
            reputation_service = ReputationService(session)
            await reputation_service.record_job_completion(
                agent_id=miner_id,
                job_id=job_id,
                success=False,
                response_time=0.0,
                earnings=Decimal("0"),
            )
        except _OPS_ERRORS as rep_err:
            logger.warning("Failed to record reputation for failed job %s: %s", job_id, rep_err)

        return {"job_id": job_id, "status": "failed"}
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found") from None
    except HTTPException:
        raise
    except _OPS_ERRORS as e:
        logger.error("Error failing job %s: %s", job_id, e)
        logger.exception("Unhandled exception")

        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error") from e


class FailJobRequest(BaseModel):
    error_message: str


# Receipt fields that carry a verdict the release gates trust. Only the
# coordinator sets them (_attach_zk_proof, _attach_tee_attestation,
# _apply_tee_computation_attestation); a miner's own receipt must not.
_MINER_RECEIPT_VERDICT_FIELDS = (
    "zk_status",
    "computation_correct",
    "zk_proof",
    "receipt_binding_proof",
    "tee_status",
    "tee_attestation_id",
)


def _strip_miner_receipt_verdicts(receipt: dict[str, Any] | None) -> dict[str, Any]:
    """Return the miner-supplied receipt without any coordinator-owned verdict field."""
    return {k: v for k, v in (receipt or {}).items() if k not in _MINER_RECEIPT_VERDICT_FIELDS}


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
    user: MinerDep,
) -> dict[str, Any]:
    """
    Complete a job by submitting execution results.

    This endpoint allows miners to submit the results of AI job execution,
    including the output and a verification receipt.
    """
    if miner_id != user["sub"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="miner_id does not match authenticated miner")
    try:
        job_service = JobService(session)
        job = await run_in_threadpool(job_service.get_job, job_id)
        if job.assigned_miner_id != user["sub"]:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="job is assigned to a different miner")
        result = {"output": complete_req.output, "receipt": _strip_miner_receipt_verdicts(complete_req.receipt)}
        job = await run_in_threadpool(job_service.execute_job, job_id, result)

        # Record completion in the reputation service so dispatch can use it.
        receipt = complete_req.receipt or {}
        output = complete_req.output or {}
        response_time = 0.0
        if "execution_time" in output:
            response_time = float(output["execution_time"]) * 1000.0
        elif receipt.get("started_at") and receipt.get("completed_at"):
            response_time = (float(receipt["completed_at"]) - float(receipt["started_at"])) * 1000.0
        # Earnings come from the persisted payment row — the request body's
        # receipt["price"] is caller-controlled and must not feed reputation.
        payment = await run_in_threadpool(session.get, JobPayment, job.payment_id) if job.payment_id else None
        earnings = Decimal(str(payment.amount)) if payment is not None and payment.amount is not None else Decimal("0")
        try:
            reputation_service = ReputationService(session)
            await reputation_service.record_job_completion(
                agent_id=miner_id,
                job_id=job_id,
                success=True,
                response_time=response_time,
                earnings=earnings,
            )
        except _OPS_ERRORS as rep_err:
            logger.warning("Failed to record reputation for job %s: %s", job_id, rep_err)

        logger.info(
            "Job %s completed by miner %s",
            job_id,
            miner_id,
            extra={"job_id": job_id, "miner_id": miner_id, "output_size": len(str(complete_req.output))},
        )
        return {
            "job_id": job_id,
            "status": "completed",
            "state": getattr(job.state, "value", job.state),
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            "receipt_hash": complete_req.receipt.get("hash", "")[:16] if complete_req.receipt else None,
        }
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found") from None
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except HTTPException:
        raise
    except _OPS_ERRORS as e:
        logger.error("Error completing job %s: %s", job_id, e)
        logger.exception("Unhandled exception")

        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error") from e
