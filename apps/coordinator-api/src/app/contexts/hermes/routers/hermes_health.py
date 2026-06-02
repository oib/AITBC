"""Router for Hermes self-healing and health monitoring API."""

from typing import Annotated, Optional, List

from sqlalchemy.orm import Session

from aitbc import get_logger

logger = get_logger(__name__)

from fastapi import APIRouter, Depends, HTTPException, Request

from ....deps import require_admin_key
from ....schemas.hermes_health import (
    HealthCheck,
    HealthStatus,
    ErrorReport,
    RecoveryResult,
)
from ....storage import get_session
from ..services.health_service import health_service

router = APIRouter(prefix="/hermes/health", tags=["hermes Health Monitoring"])


@router.post("/report")
async def report_health(
    health_check: HealthCheck,
    current_user: str = Depends(require_admin_key()),
) -> dict:
    """Report health status for an agent or service."""
    try:
        key = health_service.report_health(health_check, None)
        return {"status": "success", "key": key}
    except Exception as e:
        logger.error(f"Error reporting health: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/error")
async def report_error(
    error_report: ErrorReport,
    current_user: str = Depends(require_admin_key()),
) -> dict:
    """Report an error for self-healing analysis."""
    try:
        error_id = health_service.report_error(error_report, None)
        return {"status": "success", "error_id": error_id}
    except Exception as e:
        logger.error(f"Error reporting error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def get_health_status(
    agent_id: Optional[str] = None,
    service_name: Optional[str] = None,
    current_user: str = Depends(require_admin_key()),
) -> List[HealthCheck]:
    """Get health status with optional filtering."""
    try:
        return health_service.get_health_status(agent_id, service_name)
    except Exception as e:
        logger.error(f"Error getting health status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/recovery-history")
async def get_recovery_history(
    agent_id: Optional[str] = None,
    limit: int = 100,
    current_user: str = Depends(require_admin_key()),
) -> List[RecoveryResult]:
    """Get recovery history with optional filtering."""
    try:
        return health_service.get_recovery_history(agent_id, limit)
    except Exception as e:
        logger.error(f"Error getting recovery history: {e}")
        raise HTTPException(status_code=500, detail=str(e))
