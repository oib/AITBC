"""
Multi-modal RL Router
Handles multi-modal reinforcement learning endpoints by proxying to AI service
"""
import logging
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel

from aitbc import AITBCHTTPClient, NetworkError
from aitbc.rate_limiting import rate_limit

logger = logging.getLogger(__name__)
router = APIRouter(prefix='/multi-modal-rl', tags=['multi-modal-rl'])

class JobCreate(BaseModel):
    """Job creation model"""
    task_type: str
    task_data: dict = {}
    payment_amount: float = 0.0
    payment_currency: str = 'aitbc_token'
    priority: int = 0

def get_ai_service_url() -> str:
    """Get AI service URL from settings"""
    try:
        from ..config import settings  # type: ignore[import-not-found]
        return settings.ai_service_url.rstrip('/')  # type: ignore[no-any-return]
    except Exception:
        return 'http://localhost:8106'

@router.post('/jobs')
@rate_limit(rate=20, per=60)
async def submit_job(request: Request, req: JobCreate, client_id: str='default_client') -> dict[str, Any]:
    """Submit a job for execution (proxies to AI service)"""
    try:
        ai_url = get_ai_service_url()
        client = AITBCHTTPClient(timeout=10.0)
        job_data = req.model_dump()
        job_data['client_id'] = client_id
        response = client.post(f'{ai_url}/jobs', json=job_data)
        return response  # type: ignore[no-any-return]
    except NetworkError as e:
        logger.error('AI service connection failed: %s', e)
        return {'error': 'AI service connection failed'}
    except Exception as e:
        logger.error('Failed to submit job: %s', e)
        return {'error': 'Failed to submit job'}

@router.get('/jobs/{job_id}')
@rate_limit(rate=200, per=60)
async def get_job(request: Request, job_id: str, client_id: str='default_client') -> dict[str, Any]:
    """Get job status (proxies to AI service)"""
    try:
        ai_url = get_ai_service_url()
        client = AITBCHTTPClient(timeout=10.0)
        response = client.get(f'{ai_url}/jobs/{job_id}', params={'client_id': client_id})
        return response  # type: ignore[no-any-return]
    except NetworkError as e:
        logger.error('AI service connection failed: %s', e)
        return {'error': 'AI service connection failed'}
    except Exception as e:
        logger.error('Failed to get job: %s', e)
        return {'error': 'Failed to get job'}

@router.get('/jobs/{job_id}/result')
@rate_limit(rate=200, per=60)
async def get_job_result(request: Request, job_id: str, client_id: str='default_client') -> dict[str, Any]:
    """Get job result (proxies to AI service)"""
    try:
        ai_url = get_ai_service_url()
        client = AITBCHTTPClient(timeout=10.0)
        response = client.get(f'{ai_url}/jobs/{job_id}/result', params={'client_id': client_id})
        return response  # type: ignore[no-any-return]
    except NetworkError as e:
        logger.error('AI service connection failed: %s', e)
        return {'error': 'AI service connection failed'}
    except Exception as e:
        logger.error('Failed to get job result: %s', e)
        return {'error': 'Failed to get job result'}

@router.post('/jobs/{job_id}/cancel')
@rate_limit(rate=20, per=60)
async def cancel_job(request: Request, job_id: str, client_id: str='default_client') -> dict[str, Any]:
    """Cancel a job (proxies to AI service)"""
    try:
        ai_url = get_ai_service_url()
        client = AITBCHTTPClient(timeout=10.0)
        response = client.post(f'{ai_url}/jobs/{job_id}/cancel', params={'client_id': client_id})
        return response  # type: ignore[no-any-return]
    except NetworkError as e:
        logger.error('AI service connection failed: %s', e)
        return {'error': 'AI service connection failed'}
    except Exception as e:
        logger.error('Failed to cancel job: %s', e)
        return {'error': 'Failed to cancel job'}

@router.get('/jobs')
@rate_limit(rate=200, per=60)
async def list_jobs(request: Request, client_id: str='default_client', limit: int=10, state: str | None=None) -> dict[str, Any]:
    """List jobs with filtering (proxies to AI service)"""
    try:
        ai_url = get_ai_service_url()
        client = AITBCHTTPClient(timeout=10.0)
        params = {'client_id': client_id, 'limit': limit}
        if state:
            params['state'] = state
        response = client.get(f'{ai_url}/jobs', params=params)
        return response  # type: ignore[no-any-return]
    except NetworkError as e:
        logger.error('AI service connection failed: %s', e)
        return {'error': 'AI service connection failed'}
    except Exception as e:
        logger.error('Failed to list jobs: %s', e)
        return {'error': 'Failed to list jobs'}

@router.get('/health')
@rate_limit(rate=1000, per=60)
async def health(request: Request) -> dict[str, Any]:
    """Health check for multi-modal RL router"""
    try:
        ai_url = get_ai_service_url()
        client = AITBCHTTPClient(timeout=5.0)
        response = client.get(f'{ai_url}/health')
        return {'status': 'healthy', 'router': 'multi-modal-rl', 'ai_service': response}
    except NetworkError:
        return {'status': 'degraded', 'router': 'multi-modal-rl', 'ai_service': 'unreachable', 'note': 'AI service not available on this node'}
    except Exception as e:
        logger.error('AI service check failed: %s', e)
        return {'status': 'degraded', 'router': 'multi-modal-rl', 'ai_service': 'error', 'note': 'AI service check failed'}
