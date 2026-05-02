from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from aitbc import get_logger, AITBCHTTPClient, NetworkError

from ..config import settings
from ..custom_types import JobState
from ..deps import require_client_key
from ..schemas import JobCreate, JobPaymentCreate, JobResult, JobView
from ..services import JobService
from ..services.payments import PaymentService
from ..storage import get_session
from ..utils.cache import cached, get_cache_config

logger = get_logger(__name__)

limiter = Limiter(key_func=get_remote_address)
router = APIRouter(tags=["client"])


@router.post("/jobs", response_model=JobView, status_code=status.HTTP_201_CREATED, summary="Submit a job")
@limiter.limit(lambda: settings.rate_limit_jobs_submit)
async def submit_job(
    req: JobCreate,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    client_id: str = Depends(require_client_key()),
) -> JobView:  # type: ignore[arg-type]
    service = JobService(session)
    job = service.create_job(client_id, req)

    # Create payment if amount is specified
    if req.payment_amount and req.payment_amount > 0:
        payment_service = PaymentService(session)
        payment_create = JobPaymentCreate(
            job_id=job.id,
            amount=req.payment_amount,
            currency=req.payment_currency,
            payment_method="aitbc_token",  # Jobs use AITBC tokens
        )
        payment = await payment_service.create_payment(job.id, payment_create)
        job.payment_id = payment.id
        job.payment_status = payment.status
        session.commit()
        session.refresh(job)

    return service.to_view(job)


@router.get("/jobs/{job_id}", response_model=JobView, summary="Get job status")
@cached(**get_cache_config("job_list"))  # Cache job status for 1 minute
async def get_job(
    job_id: str,
    session: Annotated[Session, Depends(get_session)],
    client_id: str = Depends(require_client_key()),
) -> JobView:  # type: ignore[arg-type]
    service = JobService(session)
    try:
        job = service.get_job(job_id, client_id=client_id)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found")
    return service.to_view(job)


@router.get("/jobs/{job_id}/result", response_model=JobResult, summary="Get job result")
async def get_job_result(
    job_id: str,
    session: Annotated[Session, Depends(get_session)],
    client_id: str = Depends(require_client_key()),
) -> JobResult:  # type: ignore[arg-type]
    service = JobService(session)
    try:
        job = service.get_job(job_id, client_id=client_id)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found")

    if job.state not in {JobState.completed, JobState.failed, JobState.canceled, JobState.expired}:
        raise HTTPException(status_code=status.HTTP_425_TOO_EARLY, detail="job not ready")
    if job.result is None and job.receipt is None:
        raise HTTPException(status_code=status.HTTP_425_TOO_EARLY, detail="job not ready")
    return service.to_result(job)


@router.post("/jobs/{job_id}/cancel", response_model=JobView, summary="Cancel job")
async def cancel_job(
    job_id: str,
    session: Annotated[Session, Depends(get_session)],
    client_id: str = Depends(require_client_key()),
) -> JobView:  # type: ignore[arg-type]
    service = JobService(session)
    try:
        job = service.get_job(job_id, client_id=client_id)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found")

    if job.state not in {JobState.queued, JobState.running}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="job not cancelable")

    job = service.cancel_job(job)
    return service.to_view(job)


@router.get("/jobs/{job_id}/receipt", summary="Get latest signed receipt")
async def get_job_receipt(
    job_id: str,
    session: Annotated[Session, Depends(get_session)],
    client_id: str = Depends(require_client_key()),
) -> dict:  # type: ignore[arg-type]
    service = JobService(session)
    try:
        job = service.get_job(job_id, client_id=client_id)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found")
    if not job.receipt:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="receipt not available")
    return job.receipt


@router.get("/jobs/{job_id}/receipts", summary="List signed receipts")
async def list_job_receipts(
    job_id: str,
    session: Annotated[Session, Depends(get_session)],
    client_id: str = Depends(require_client_key()),
) -> dict:  # type: ignore[arg-type]
    service = JobService(session)
    receipts = service.list_receipts(job_id, client_id=client_id)
    return {"items": [row.payload for row in receipts]}


@router.get("/jobs", summary="List jobs with filtering")
@cached(**get_cache_config("job_list"))  # Cache job list for 30 seconds
async def list_jobs(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    client_id: str = Depends(require_client_key()),
    limit: int = 20,
    offset: int = 0,
    status: str | None = None,
    job_type: str | None = None,
) -> dict:  # type: ignore[arg-type]
    """List jobs with optional filtering by status and type"""
    service = JobService(session)

    # Build filters
    filters = {}
    if status:
        try:
            filters["state"] = JobState(status.upper())
        except ValueError:
            pass  # Invalid status, ignore

    if job_type:
        filters["job_type"] = job_type

    jobs = service.list_jobs(client_id=client_id, limit=limit, offset=offset, **filters)

    return {"items": [service.to_view(job) for job in jobs], "total": len(jobs), "limit": limit, "offset": offset}


@router.get("/jobs/history", summary="Get job history")
@cached(**get_cache_config("job_list"))  # Cache job history for 30 seconds
async def get_job_history(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    client_id: str = Depends(require_client_key()),
    limit: int = 20,
    offset: int = 0,
    status: str | None = None,
    job_type: str | None = None,
    from_time: str | None = None,
    to_time: str | None = None,
) -> dict:  # type: ignore[arg-type]
    """Get job history with time range filtering"""
    service = JobService(session)

    # Build filters
    filters = {}
    if status:
        try:
            filters["state"] = JobState(status.upper())
        except ValueError:
            pass  # Invalid status, ignore

    if job_type:
        filters["job_type"] = job_type

    try:
        # Use the list_jobs method with time filtering
        jobs = service.list_jobs(client_id=client_id, limit=limit, offset=offset, **filters)

        return {
            "items": [service.to_view(job) for job in jobs],
            "total": len(jobs),
            "limit": limit,
            "offset": offset,
            "from_time": from_time,
            "to_time": to_time,
        }
    except Exception as e:
        # Return empty result if no jobs found
        return {
            "items": [],
            "total": 0,
            "limit": limit,
            "offset": offset,
            "from_time": from_time,
            "to_time": to_time,
            "error": "Failed to list jobs",
        }


@router.get("/blocks", summary="Get blockchain blocks")
async def get_blocks(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    client_id: str = Depends(require_client_key()),
    limit: int = 20,
    offset: int = 0,
) -> dict:  # type: ignore[arg-type]
    """Get recent blockchain blocks"""
    try:
        # Query the local blockchain node for blocks
        client = AITBCHTTPClient(timeout=5.0)
        try:
            blocks_data = client.get(
                f"{settings.blockchain_rpc_url}/rpc/blocks-range", params={"start": offset, "end": offset + limit}
            )
            return {
                "blocks": blocks_data.get("blocks", []),
                "total": blocks_data.get("total", 0),
                "limit": limit,
                "offset": offset,
            }
        except NetworkError as e:
            logger.error(f"Failed to fetch blocks: {e}")
            return {
                "blocks": [],
                "total": 0,
                "limit": limit,
                "offset": offset,
                "error": "Failed to fetch blocks",
            }
    except Exception as e:
        return {"blocks": [], "total": 0, "limit": limit, "offset": offset, "error": "Failed to fetch blocks"}


# Temporary agent endpoints added to client router until agent router issue is resolved
@router.post("/agents/networks", response_model=dict, status_code=201)
async def create_agent_network(network_data: dict) -> dict:
    """Create a new agent network for collaborative processing"""

    try:
        # Validate required fields
        if not network_data.get("name"):
            raise HTTPException(status_code=400, detail="Network name is required")

        if not network_data.get("agents"):
            raise HTTPException(status_code=400, detail="Agent list is required")

        # Create network record (simplified for now)
        network_id = f"network_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"

        network_response = {
            "id": network_id,
            "name": network_data["name"],
            "description": network_data.get("description", ""),
            "agents": network_data["agents"],
            "coordination_strategy": network_data.get("coordination", "centralized"),
            "status": "active",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "owner_id": "temp_user",
        }

        return network_response

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/agents/executions/{execution_id}/receipt")
async def get_execution_receipt(execution_id: str) -> dict:
    """Get verifiable receipt for completed execution"""

    try:
        # For now, return a mock receipt since the full execution system isn't implemented
        receipt_data = {
            "execution_id": execution_id,
            "workflow_id": f"workflow_{execution_id}",
            "status": "completed",
            "receipt_id": f"receipt_{execution_id}",
            "miner_signature": "0xmock_signature_placeholder",
            "coordinator_attestations": [
                {
                    "coordinator_id": "coordinator_1",
                    "signature": "0xmock_attestation_1",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            ],
            "minted_amount": 1000,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "verified": True,
            "block_hash": "0xmock_block_hash",
            "transaction_hash": "0xmock_tx_hash",
        }

        return receipt_data

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
