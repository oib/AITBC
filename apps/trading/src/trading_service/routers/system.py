"""System endpoints for the Trading Service."""

from fastapi import APIRouter
from fastapi.responses import JSONResponse, PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel
from sqlalchemy import text

from aitbc.aitbc_logging import get_logger
from aitbc.health_checks import create_simple_health_response

from ..storage import get_session

router = APIRouter(tags=["system"], dependencies=[])
logger = get_logger(__name__)


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    service: str


@router.get("/health")
async def health() -> HealthResponse:
    """Health check endpoint."""
    return HealthResponse(**create_simple_health_response("trading"))


@router.get("/ready", response_model=None)
async def ready() -> dict[str, str] | JSONResponse:
    """Readiness check - verifies database connectivity."""
    try:
        async with get_session() as session:
            await session.execute(text("SELECT 1"))
        return {"status": "ready", "service": "trading"}
    except Exception as e:
        logger.error("Readiness check failed: %s", e)
        return JSONResponse(status_code=503, content={"status": "not_ready", "service": "trading", "error": str(e)})


@router.get("/live")
async def live() -> dict[str, str]:
    """Liveness check - verifies service is not stuck."""
    return {"status": "alive", "service": "trading"}


@router.get("/v1/trading/status")
async def trading_status() -> dict[str, str]:
    """Get trading status."""
    return {"status": "operational", "service": "trading", "message": "Trading service is running"}


@router.get("/metrics", response_class=PlainTextResponse)
async def metrics() -> PlainTextResponse:
    """Prometheus metrics endpoint."""
    return PlainTextResponse(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
