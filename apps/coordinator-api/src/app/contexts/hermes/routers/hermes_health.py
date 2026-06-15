"""Router for Hermes self-healing and health monitoring API."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from aitbc import get_logger

logger = get_logger(__name__)
from ....deps import require_admin_key  # noqa: E402
from ....schemas.hermes_health import ErrorReport, HealthCheck, RecoveryResult  # noqa: E402
from ....storage import get_session  # noqa: E402
from ..services.health_service_db import health_service  # noqa: E402

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
        logger.error("Error reporting health: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


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
        logger.error("Error reporting error: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/status")
async def get_health_status(
    session: Annotated[Session, Depends(get_session)],
    current_user: str = Depends(require_admin_key()),
    agent_id: str | None = None,
    service_name: str | None = None,
) -> list[HealthCheck]:
    """Get health status with optional filtering."""
    try:
        return health_service.get_health_status(agent_id, service_name)  # type: ignore[arg-type]
    except Exception as e:
        logger.error("Error getting health status: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/recovery-history")
async def get_recovery_history(
    session: Annotated[Session, Depends(get_session)],
    current_user: str = Depends(require_admin_key()),
    agent_id: str | None = None,
    limit: int = 100,
) -> list[RecoveryResult]:
    """Get recovery history with optional filtering."""
    try:
        return health_service.get_recovery_history(agent_id, limit)  # type: ignore[arg-type]
    except Exception as e:
        logger.error("Error getting recovery history: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e
