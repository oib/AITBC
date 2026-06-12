from __future__ import annotations
from datetime import UTC, datetime
from typing import Annotated
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session
from sqlmodel import select
from aitbc import get_logger
from aitbc.rate_limiting import rate_limit
from ..config import settings
from ..deps import require_admin_key
from ..services import JobService, MinerService
from ..storage import get_session
from ..utils.cache import cached, get_cache_config
logger = get_logger(__name__)
router = APIRouter(prefix='/admin', tags=['admin'])

@router.get('/debug-settings', summary='Debug settings')
@rate_limit(rate=100, per=60)
async def debug_settings(request: Request) -> dict:

    def mask_keys(keys: list[str]) -> list[str]:
        return [key[:8] + '...' if len(key) > 8 else '***' for key in keys]
    return {'admin_api_keys': mask_keys(settings.admin_api_keys), 'client_api_keys': mask_keys(settings.client_api_keys), 'miner_api_keys': mask_keys(settings.miner_api_keys), 'app_env': settings.app_env}

@router.post('/debug/create-test-miner', summary='Create a test miner for debugging')
@rate_limit(rate=10, per=60)
async def create_test_miner(request: Request, session: Annotated[Session, Depends(get_session)], admin_key: str=Depends(require_admin_key())) -> dict[str, str]:
    """Create a test miner for debugging marketplace sync"""
    try:
        from uuid import uuid4
        from ..domain import Miner
        miner_id = 'debug-test-miner'
        session_token = uuid4().hex
        existing_miner = session.get(Miner, miner_id)
        if existing_miner:
            existing_miner.status = 'ONLINE'
            existing_miner.last_heartbeat = datetime.now(UTC)
            existing_miner.session_token = session_token
            session.add(existing_miner)
            session.commit()
            return {'status': 'updated', 'miner_id': miner_id, 'message': 'Existing miner updated to ONLINE'}
        miner = Miner(id=miner_id, capabilities={'gpu_memory': 8192, 'models': ['qwen3:8b'], 'pricing_per_hour': 0.5, 'gpu': 'RTX 4090', 'gpu_memory_gb': 8192, 'gpu_count': 1, 'cuda_version': '12.0', 'supported_models': ['qwen3:8b']}, concurrency=1, region='test-region', session_token=session_token, status='ONLINE', inflight=0, last_heartbeat=datetime.now(UTC))
        session.add(miner)
        session.commit()
        session.refresh(miner)
        logger.info('Created test miner: %s', miner_id)
        return {'status': 'created', 'miner_id': miner_id, 'session_token': session_token, 'message': 'Test miner created successfully'}
    except Exception:
        logger.error('Failed to create test miner')
        raise HTTPException(status_code=500, detail='Failed to create test miner')

@router.get('/test-key', summary='Test API key validation')
@rate_limit(rate=100, per=60)
async def test_key(request: Request, api_key: str=Header(default=None, alias='X-Api-Key')) -> dict[str, str]:
    masked_key = api_key[:8] + '...' if api_key else 'None'
    logger.debug('Received API key: %s', masked_key)
    logger.debug('Allowed admin keys count: %s', len(settings.admin_api_keys))
    if not api_key or api_key not in settings.admin_api_keys:
        logger.debug('API key validation failed!')
        raise HTTPException(status_code=401, detail='invalid api key')
    logger.debug('API key validation successful!')
    return {'message': 'API key is valid', 'key': masked_key}

@router.get('/stats', summary='Get coordinator stats')
@rate_limit(rate=100, per=60)
@cached(**get_cache_config('job_list'))
async def get_stats(request: Request, session: Annotated[Session, Depends(get_session)], api_key: str=Header(default=None, alias='X-Api-Key')) -> dict[str, int]:
    logger.debug('API key validation check')
    logger.debug('Allowed admin keys count: %d', len(settings.admin_api_keys))
    if not api_key or api_key not in settings.admin_api_keys:
        raise HTTPException(status_code=401, detail='invalid api key')
    logger.debug('API key validation successful!')
    JobService(session)
    from sqlmodel import func, select
    from ..domain import Job
    total_jobs = session.execute(select(func.count()).select_from(Job)).one()
    active_jobs = session.execute(select(func.count()).select_from(Job).where(Job.state.in_(['QUEUED', 'RUNNING']))).one()
    miner_service = MinerService(session)
    miners = miner_service.list_records()
    avg_job_duration = sum((miner.average_job_duration_ms for miner in miners if miner.average_job_duration_ms)) / max(len(miners), 1)
    return {'total_jobs': int(total_jobs or 0), 'active_jobs': int(active_jobs or 0), 'online_miners': miner_service.online_count(), 'avg_miner_job_duration_ms': avg_job_duration}

@router.get('/jobs', summary='List jobs')
@rate_limit(rate=100, per=60)
async def list_jobs(request: Request, session: Annotated[Session, Depends(get_session)], admin_key: str=Depends(require_admin_key())) -> dict[str, list[dict]]:
    from ..domain import Job
    jobs = session.execute(select(Job).order_by(Job.requested_at.desc()).limit(100)).all()
    return {'items': [{'job_id': job.id, 'state': job.state, 'client_id': job.client_id, 'assigned_miner_id': job.assigned_miner_id, 'requested_at': job.requested_at.isoformat()} for job in jobs]}

@router.get('/miners', summary='List miners')
@rate_limit(rate=100, per=60)
async def list_miners(request: Request, session: Annotated[Session, Depends(get_session)], admin_key: str=Depends(require_admin_key())) -> dict[str, list[dict]]:
    from sqlmodel import select
    from ..domain import Miner
    miners = session.execute(select(Miner)).scalars().all()
    miner_list = [{'miner_id': miner.id, 'status': miner.status, 'inflight': miner.inflight, 'concurrency': miner.concurrency, 'region': miner.region, 'last_heartbeat': miner.last_heartbeat.isoformat(), 'average_job_duration_ms': miner.average_job_duration_ms, 'jobs_completed': miner.jobs_completed, 'jobs_failed': miner.jobs_failed, 'last_receipt_id': miner.last_receipt_id} for miner in miners]
    return {'items': miner_list}

@router.get('/status', summary='Get system status', response_model=None)
@rate_limit(rate=100, per=60)
async def get_system_status(request: Request, session: Annotated[Session, Depends(get_session)], admin_key: str=Depends(require_admin_key())) -> dict[str, any]:
    """Get comprehensive system status for admin dashboard"""
    try:
        JobService(session)
        from sqlmodel import func, select
        from ..domain import Job
        total_jobs = session.execute(select(func.count()).select_from(Job)).one()
        active_jobs = session.execute(select(func.count()).select_from(Job).where(Job.state.in_(['QUEUED', 'RUNNING']))).one()
        completed_jobs = session.execute(select(func.count()).select_from(Job).where(Job.state == 'COMPLETED')).one()
        failed_jobs = session.execute(select(func.count()).select_from(Job).where(Job.state == 'FAILED')).one()
        miner_service = MinerService(session)
        miners = miner_service.list_records()
        online_miners = miner_service.online_count()
        avg_job_duration = sum((miner.average_job_duration_ms for miner in miners if miner.average_job_duration_ms)) / max(len(miners), 1)
        import sys
        from datetime import datetime
        import psutil
        system_info = {'cpu_percent': psutil.cpu_percent(interval=1), 'memory_percent': psutil.virtual_memory().percent, 'disk_percent': psutil.disk_usage('/').percent, 'python_version': f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}', 'timestamp': datetime.now(UTC).isoformat()}
        return {'jobs': {'total': int(total_jobs or 0), 'active': int(active_jobs or 0), 'completed': int(completed_jobs or 0), 'failed': int(failed_jobs or 0)}, 'miners': {'total': len(miners), 'online': online_miners, 'offline': len(miners) - online_miners, 'avg_job_duration_ms': avg_job_duration}, 'system': system_info, 'status': 'healthy' if online_miners > 0 else 'degraded'}
    except Exception:
        logger.error('Failed to get system status')
        return {'status': 'error', 'error': 'Failed to get system status'}