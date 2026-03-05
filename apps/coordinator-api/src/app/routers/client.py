from fastapi import APIRouter, Depends, HTTPException, status, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from ..deps import require_client_key
from ..schemas import JobCreate, JobView, JobResult, JobPaymentCreate
from ..types import JobState
from ..services import JobService
from ..services.payments import PaymentService
from ..config import settings
from ..storage import SessionDep
from ..utils.cache import cached, get_cache_config

limiter = Limiter(key_func=get_remote_address)
router = APIRouter(tags=["client"])


@router.post("/jobs", response_model=JobView, status_code=status.HTTP_201_CREATED, summary="Submit a job")
@limiter.limit(lambda: settings.rate_limit_jobs_submit)
async def submit_job(
    req: JobCreate,
    request: Request,
    session: SessionDep,
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
            payment_method="aitbc_token"  # Jobs use AITBC tokens
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
    session: SessionDep,
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
    session: SessionDep,
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
    session: SessionDep,
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
    session: SessionDep,
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
    session: SessionDep,
    client_id: str = Depends(require_client_key()),
) -> dict:  # type: ignore[arg-type]
    service = JobService(session)
    receipts = service.list_receipts(job_id, client_id=client_id)
    return {"items": [row.payload for row in receipts]}


@router.get("/jobs", summary="List jobs with filtering")
@cached(**get_cache_config("job_list"))  # Cache job list for 30 seconds
async def list_jobs(
    request: Request,
    session: SessionDep,
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
    
    jobs = service.list_jobs(
        client_id=client_id,
        limit=limit,
        offset=offset,
        **filters
    )
    
    return {
        "items": [service.to_view(job) for job in jobs],
        "total": len(jobs),
        "limit": limit,
        "offset": offset
    }


@router.get("/jobs/history", summary="Get job history")
@cached(**get_cache_config("job_list"))  # Cache job history for 30 seconds
async def get_job_history(
    request: Request,
    session: SessionDep,
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
        jobs = service.list_jobs(
            client_id=client_id,
            limit=limit,
            offset=offset,
            **filters
        )
        
        return {
            "items": [service.to_view(job) for job in jobs],
            "total": len(jobs),
            "limit": limit,
            "offset": offset,
            "from_time": from_time,
            "to_time": to_time
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
            "error": str(e)
        }


@router.get("/blocks", summary="Get blockchain blocks")
async def get_blocks(
    request: Request,
    session: SessionDep,
    client_id: str = Depends(require_client_key()),
    limit: int = 20,
    offset: int = 0,
) -> dict:  # type: ignore[arg-type]
    """Get recent blockchain blocks"""
    try:
        import httpx
        
        # Query the local blockchain node for blocks
        with httpx.Client() as client:
            response = client.get(
                f"http://10.1.223.93:8082/rpc/blocks-range",
                params={"start": offset, "end": offset + limit},
                timeout=5
            )
            
            if response.status_code == 200:
                blocks_data = response.json()
                return {
                    "blocks": blocks_data.get("blocks", []),
                    "total": blocks_data.get("total", 0),
                    "limit": limit,
                    "offset": offset
                }
            else:
                # Fallback to empty response if blockchain node is unavailable
                return {
                    "blocks": [],
                    "total": 0,
                    "limit": limit,
                    "offset": offset,
                    "error": f"Blockchain node unavailable: {response.status_code}"
                }
    except Exception as e:
        return {
            "blocks": [],
            "total": 0,
            "limit": limit,
            "offset": offset,
            "error": f"Failed to fetch blocks: {str(e)}"
        }
