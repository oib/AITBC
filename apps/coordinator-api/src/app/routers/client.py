from fastapi import APIRouter, Depends, HTTPException, status

from ..deps import require_client_key
from ..models import JobCreate, JobView, JobResult
from ..services import JobService
from ..storage import SessionDep

router = APIRouter(tags=["client"])

@router.post("/jobs", response_model=JobView, status_code=status.HTTP_201_CREATED, summary="Submit a job")
async def submit_job(
    req: JobCreate,
    session: SessionDep,
    client_id: str = Depends(require_client_key()),
) -> JobView:  # type: ignore[arg-type]
    service = JobService(session)
    job = service.create_job(client_id, req)
    return service.to_view(job)


@router.get("/jobs/{job_id}", response_model=JobView, summary="Get job status")
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
