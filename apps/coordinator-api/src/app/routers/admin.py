from sqlalchemy.orm import Session
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status, Request, Header
from sqlmodel import select
from slowapi import Limiter
from slowapi.util import get_remote_address
from datetime import datetime

from ..deps import require_admin_key
from ..services import JobService, MinerService
from ..storage import Annotated[Session, Depends(get_session)], get_session
from ..utils.cache import cached, get_cache_config
from ..config import settings
from aitbc.logging import get_logger

logger = get_logger(__name__)
limiter = Limiter(key_func=get_remote_address)
router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/debug-settings", summary="Debug settings")
async def debug_settings() -> dict:  # type: ignore[arg-type]
    return {
        "admin_api_keys": settings.admin_api_keys,
        "client_api_keys": settings.client_api_keys,
        "miner_api_keys": settings.miner_api_keys,
        "app_env": settings.app_env
    }


@router.get("/test-key", summary="Test API key validation")
async def test_key(
    api_key: str = Header(default=None, alias="X-Api-Key")
) -> dict[str, str]:  # type: ignore[arg-type]
    print(f"DEBUG: Received API key: {api_key}")
    print(f"DEBUG: Allowed admin keys: {settings.admin_api_keys}")
    
    if not api_key or api_key not in settings.admin_api_keys:
        print(f"DEBUG: API key validation failed!")
        raise HTTPException(status_code=401, detail="invalid api key")
    
    print(f"DEBUG: API key validation successful!")
    return {"message": "API key is valid", "key": api_key}


@router.get("/stats", summary="Get coordinator stats")
@limiter.limit(lambda: settings.rate_limit_admin_stats)
@cached(**get_cache_config("job_list"))  # Cache admin stats for 1 minute
async def get_stats(
    request: Request,
    session: Annotated[Session, Depends(get_session)] = Depends(), 
    api_key: str = Header(default=None, alias="X-Api-Key")
) -> dict[str, int]:  # type: ignore[arg-type]
    # Temporary debug: bypass dependency and validate directly
    print(f"DEBUG: Received API key: {api_key}")
    print(f"DEBUG: Allowed admin keys: {settings.admin_api_keys}")
    
    if not api_key or api_key not in settings.admin_api_keys:
        raise HTTPException(status_code=401, detail="invalid api key")
    
    print(f"DEBUG: API key validation successful!")
    
    service = JobService(session)
    from sqlmodel import func, select
    from ..domain import Job

    total_jobs = session.execute(select(func.count()).select_from(Job)).one()
    active_jobs = session.execute(select(func.count()).select_from(Job).where(Job.state.in_(["QUEUED", "RUNNING"]))).one()

    miner_service = MinerService(session)
    miners = miner_service.list_records()
    avg_job_duration = (
        sum(miner.average_job_duration_ms for miner in miners if miner.average_job_duration_ms) / max(len(miners), 1)
    )
    return {
        "total_jobs": int(total_jobs or 0),
        "active_jobs": int(active_jobs or 0),
        "online_miners": miner_service.online_count(),
        "avg_miner_job_duration_ms": avg_job_duration,
    }


@router.get("/jobs", summary="List jobs")
async def list_jobs(session: Annotated[Session, Depends(get_session)] = Depends(), admin_key: str = Depends(require_admin_key())) -> dict[str, list[dict]]:  # type: ignore[arg-type]
    from ..domain import Job

    jobs = session.execute(select(Job).order_by(Job.requested_at.desc()).limit(100)).all()
    return {
        "items": [
            {
                "job_id": job.id,
                "state": job.state,
                "client_id": job.client_id,
                "assigned_miner_id": job.assigned_miner_id,
                "requested_at": job.requested_at.isoformat(),
            }
            for job in jobs
        ]
    }


@router.get("/miners", summary="List miners")
async def list_miners(session: Annotated[Session, Depends(get_session)] = Depends(), admin_key: str = Depends(require_admin_key())) -> dict[str, list[dict]]:  # type: ignore[arg-type]
    miner_service = MinerService(session)
    miners = [
        {
            "miner_id": record.id,
            "status": record.status,
            "inflight": record.inflight,
            "concurrency": record.concurrency,
            "region": record.region,
            "last_heartbeat": record.last_heartbeat.isoformat(),
            "average_job_duration_ms": record.average_job_duration_ms,
            "jobs_completed": record.jobs_completed,
            "jobs_failed": record.jobs_failed,
            "last_receipt_id": record.last_receipt_id,
        }
        for record in miner_service.list_records()
    ]
    return {"items": miners}


@router.get("/status", summary="Get system status", response_model=None)
async def get_system_status(
    request: Request,
    session: Annotated[Session, Depends(get_session)] = Depends(), 
    admin_key: str = Depends(require_admin_key())
) -> dict[str, any]:  # type: ignore[arg-type]
    """Get comprehensive system status for admin dashboard"""
    try:
        # Get job statistics
        service = JobService(session)
        from sqlmodel import func, select
        from ..domain import Job

        total_jobs = session.execute(select(func.count()).select_from(Job)).one()
        active_jobs = session.execute(select(func.count()).select_from(Job).where(Job.state.in_(["QUEUED", "RUNNING"]))).one()
        completed_jobs = session.execute(select(func.count()).select_from(Job).where(Job.state == "COMPLETED")).one()
        failed_jobs = session.execute(select(func.count()).select_from(Job).where(Job.state == "FAILED")).one()

        # Get miner statistics
        miner_service = MinerService(session)
        miners = miner_service.list_records()
        online_miners = miner_service.online_count()
        
        # Calculate job statistics
        avg_job_duration = (
            sum(miner.average_job_duration_ms for miner in miners if miner.average_job_duration_ms) / max(len(miners), 1)
        )
        
        # Get system info
        import psutil
        import sys
        from datetime import datetime
        
        system_info = {
            "cpu_percent": psutil.cpu_percent(interval=1),
            "memory_percent": psutil.virtual_memory().percent,
            "disk_percent": psutil.disk_usage('/').percent,
            "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            "timestamp": datetime.utcnow().isoformat()
        }
        
        return {
            "jobs": {
                "total": int(total_jobs or 0),
                "active": int(active_jobs or 0),
                "completed": int(completed_jobs or 0),
                "failed": int(failed_jobs or 0)
            },
            "miners": {
                "total": len(miners),
                "online": online_miners,
                "offline": len(miners) - online_miners,
                "avg_job_duration_ms": avg_job_duration
            },
            "system": system_info,
            "status": "healthy" if online_miners > 0 else "degraded"
        }
        
    except Exception as e:
        logger.error(f"Failed to get system status: {e}")
        return {
            "status": "error",
            "error": str(e),
        }


# Agent endpoints temporarily added to admin router
@router.post("/agents/networks", response_model=dict, status_code=201)
async def create_agent_network(network_data: dict):
    """Create a new agent network for collaborative processing"""
    
    try:
        # Validate required fields
        if not network_data.get("name"):
            raise HTTPException(status_code=400, detail="Network name is required")
        
        if not network_data.get("agents"):
            raise HTTPException(status_code=400, detail="Agent list is required")
        
        # Create network record (simplified for now)
        network_id = f"network_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
        
        network_response = {
            "id": network_id,
            "name": network_data["name"],
            "description": network_data.get("description", ""),
            "agents": network_data["agents"],
            "coordination_strategy": network_data.get("coordination", "centralized"),
            "status": "active",
            "created_at": datetime.utcnow().isoformat(),
            "owner_id": "temp_user"
        }
        
        logger.info(f"Created agent network: {network_id}")
        return network_response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create agent network: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/agents/executions/{execution_id}/receipt")
async def get_execution_receipt(execution_id: str):
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
                    "timestamp": datetime.utcnow().isoformat()
                }
            ],
            "minted_amount": 1000,
            "recorded_at": datetime.utcnow().isoformat(),
            "verified": True,
            "block_hash": "0xmock_block_hash",
            "transaction_hash": "0xmock_tx_hash"
        }
        
        logger.info(f"Generated receipt for execution: {execution_id}")
        return receipt_data
        
    except Exception as e:
        logger.error(f"Failed to get execution receipt: {e}")
        raise HTTPException(status_code=500, detail=str(e))
