"""Router for Hermes self-healing and health monitoring API."""

from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from aitbc import get_logger

logger = get_logger(__name__)

from ....deps import require_admin_key
from ....schemas.hermes_health import (
    ErrorReport,
    HealthCheck,
    RecoveryResult,
)
from ....storage import get_session
from ..services.health_service_db import health_service

router = APIRouter(prefix="/hermes/health", tags=["hermes Health Monitoring"])


@router.post("/report")
async def report_health(
    health_check: HealthCheck,
    session: Annotated[Session, Depends(get_session)],
    current_user: str = Depends(require_admin_key()),
) -> dict:
    """Report health status for an agent or service."""
    try:
        key = health_service.report_health(health_check, session)
        return {"status": "success", "key": key}
    except Exception as e:
        logger.error(f"Error reporting health: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/error")
async def report_error(
    error_report: ErrorReport,
    session: Annotated[Session, Depends(get_session)],
    current_user: str = Depends(require_admin_key()),
) -> dict:
    """Report an error for self-healing analysis."""
    try:
        error_id = health_service.report_error(error_report, session)
        return {"status": "success", "error_id": error_id}
    except Exception as e:
        logger.error(f"Error reporting error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def get_health_status(
    session: Annotated[Session, Depends(get_session)],
    current_user: str = Depends(require_admin_key()),
    agent_id: Optional[str] = None,
    service_name: Optional[str] = None,
) -> List[HealthCheck]:
    """Get health status with optional filtering."""
    try:
        return health_service.get_health_status(agent_id, service_name)
    except Exception as e:
        logger.error(f"Error getting health status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/recovery-history")
async def get_recovery_history(
    session: Annotated[Session, Depends(get_session)],
    current_user: str = Depends(require_admin_key()),
    agent_id: Optional[str] = None,
    limit: int = 100,
) -> List[RecoveryResult]:
    """Get recovery history with optional filtering."""
    try:
        return health_service.get_recovery_history(agent_id, limit)
    except Exception as e:
        logger.error(f"Error getting recovery history: {e}")
        raise HTTPException(status_code=500, detail=str(e))
