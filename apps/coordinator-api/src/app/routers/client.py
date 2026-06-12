from __future__ import annotations
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from aitbc import AITBCHTTPClient, NetworkError, get_logger
from aitbc.rate_limiting import rate_limit
from ..config import settings
from ..contexts.payments.services.payments import PaymentService
from ..custom_types import JobState
from ..deps import require_client_key
from ..schemas import JobCreate, JobPaymentCreate, JobResult, JobView
from ..services import JobService
from ..storage import get_session
from ..utils.cache import cached, get_cache_config
logger = get_logger(__name__)
router = APIRouter(tags=['client'])

@router.post('/jobs', response_model=JobView, status_code=status.HTTP_201_CREATED, summary='Submit a job')
@rate_limit(rate=50, per=60)
async def submit_job(req: JobCreate, request: Request, session: Annotated[Session, Depends(get_session)], client_id: str=Depends(require_client_key())) -> JobView:
    service = JobService(session)
    job = service.create_job(client_id, req)
    if req.payment_amount and req.payment_amount > 0:
        try:
            payment_service = PaymentService(session)
            payment_create = JobPaymentCreate(job_id=job.id, amount=req.payment_amount, currency=req.payment_currency, payment_method='aitbc_token')
            payment = await payment_service.create_payment(job.id, payment_create)
            job.payment_id = payment.id
            job.payment_status = payment.status
            session.commit()
            session.refresh(job)
            logger.info('Payment created for job %s: %s', job.id, payment.id)
        except Exception as e:
            logger.warning('Payment creation failed for job %s, proceeding without payment: %s', job.id, e)
            job.payment_status = 'skipped'
            session.commit()
            session.refresh(job)
    return service.to_view(job)

@router.get('/jobs/{job_id}', response_model=JobView, summary='Get job status')
@rate_limit(rate=200, per=60)
async def get_job(request: Request, job_id: str, session: Annotated[Session, Depends(get_session)], client_id: str=Depends(require_client_key())) -> JobView:
    service = JobService(session)
    try:
        job = service.get_job(job_id, client_id=client_id)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='job not found')
    return service.to_view(job)

@router.get('/jobs/{job_id}/result', response_model=JobResult, summary='Get job result')
@rate_limit(rate=200, per=60)
async def get_job_result(request: Request, job_id: str, session: Annotated[Session, Depends(get_session)], client_id: str=Depends(require_client_key())) -> JobResult:
    service = JobService(session)
    try:
        job = service.get_job(job_id, client_id=client_id)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='job not found')
    if job.state not in {JobState.completed, JobState.failed, JobState.canceled, JobState.expired}:
        raise HTTPException(status_code=status.HTTP_425_TOO_EARLY, detail='job not ready')
    if job.result is None and job.receipt is None:
        raise HTTPException(status_code=status.HTTP_425_TOO_EARLY, detail='job not ready')
    return service.to_result(job)

@router.post('/jobs/{job_id}/cancel', response_model=JobView, summary='Cancel job')
@rate_limit(rate=50, per=60)
async def cancel_job(request: Request, job_id: str, session: Annotated[Session, Depends(get_session)], client_id: str=Depends(require_client_key())) -> JobView:
    service = JobService(session)
    try:
        job = service.get_job(job_id, client_id=client_id)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='job not found')
    if job.state not in {JobState.queued, JobState.running}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='job not cancelable')
    job = service.cancel_job(job)
    return service.to_view(job)

@router.get('/jobs/{job_id}/receipt', summary='Get latest signed receipt')
@rate_limit(rate=200, per=60)
async def get_job_receipt(request: Request, job_id: str, session: Annotated[Session, Depends(get_session)], client_id: str=Depends(require_client_key())) -> dict:
    service = JobService(session)
    try:
        job = service.get_job(job_id, client_id=client_id)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='job not found')
    if not job.receipt:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='receipt not available')
    return job.receipt

@router.get('/jobs/{job_id}/receipts', summary='List signed receipts')
@rate_limit(rate=200, per=60)
async def list_job_receipts(request: Request, job_id: str, session: Annotated[Session, Depends(get_session)], client_id: str=Depends(require_client_key())) -> dict:
    service = JobService(session)
    receipts = service.list_receipts(job_id, client_id=client_id)
    return {'items': [row.payload for row in receipts]}

@router.get('/jobs', summary='List jobs with filtering')
@rate_limit(rate=200, per=60)
@cached(**get_cache_config('job_list'))
async def list_jobs(request: Request, session: Annotated[Session, Depends(get_session)], client_id: str=Depends(require_client_key()), limit: int=20, offset: int=0, status: str | None=None, job_type: str | None=None) -> dict:
    """List jobs with optional filtering by status and type"""
    service = JobService(session)
    filters = {}
    if status:
        try:
            filters['state'] = JobState(status.upper())
        except ValueError:
            pass
    if job_type:
        filters['job_type'] = job_type
    jobs = service.list_jobs(client_id=client_id, limit=limit, offset=offset, **filters)
    return {'items': [service.to_view(job) for job in jobs], 'total': len(jobs), 'limit': limit, 'offset': offset}

@router.get('/jobs/history', summary='Get job history')
@rate_limit(rate=200, per=60)
@cached(**get_cache_config('job_list'))
async def get_job_history(request: Request, session: Annotated[Session, Depends(get_session)], client_id: str=Depends(require_client_key()), limit: int=20, offset: int=0, status: str | None=None, job_type: str | None=None, from_time: str | None=None, to_time: str | None=None) -> dict:
    """Get job history with time range filtering"""
    service = JobService(session)
    filters = {}
    if status:
        try:
            filters['state'] = JobState(status.upper())
        except ValueError:
            pass
    if job_type:
        filters['job_type'] = job_type
    try:
        jobs = service.list_jobs(client_id=client_id, limit=limit, offset=offset, **filters)
        return {'items': [service.to_view(job) for job in jobs], 'total': len(jobs), 'limit': limit, 'offset': offset, 'from_time': from_time, 'to_time': to_time}
    except Exception:
        return {'items': [], 'total': 0, 'limit': limit, 'offset': offset, 'from_time': from_time, 'to_time': to_time, 'error': 'Failed to list jobs'}

@router.get('/blocks', summary='Get blockchain blocks')
@rate_limit(rate=200, per=60)
async def get_blocks(request: Request, session: Annotated[Session, Depends(get_session)], client_id: str=Depends(require_client_key()), limit: int=20, offset: int=0) -> dict:
    """Get recent blockchain blocks"""
    try:
        client = AITBCHTTPClient(timeout=5.0)
        try:
            blocks_data = client.get(f'{settings.blockchain_rpc_url}/rpc/blocks-range', params={'start': offset, 'end': offset + limit})
            return {'blocks': blocks_data.get('blocks', []), 'total': blocks_data.get('total', 0), 'limit': limit, 'offset': offset}
        except NetworkError as e:
            logger.error('Failed to fetch blocks: %s', e)
            return {'blocks': [], 'total': 0, 'limit': limit, 'offset': offset, 'error': 'Failed to fetch blocks'}
    except Exception:
        return {'blocks': [], 'total': 0, 'limit': limit, 'offset': offset, 'error': 'Failed to fetch blocks'}