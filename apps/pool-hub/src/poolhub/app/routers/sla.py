"""
SLA API Endpoints for Pool-Hub
Provides endpoints for SLA metrics and capacity planning.
"""

from datetime import UTC, datetime, timedelta
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from aitbc.aitbc_logging import get_logger

from ...database import get_session as get_db
from ...models import CapacitySnapshot
from ...services.sla_collector import SLACollector

logger = get_logger(__name__)
from .parameters import _governance_auth

router = APIRouter(prefix="/sla", tags=["SLA"])


class SLAMetricResponse(BaseModel):
    id: UUID
    miner_id: str
    metric_type: str
    metric_value: float
    threshold: float
    is_violation: bool
    timestamp: datetime
    # The column is named ``meta_data`` -- plain ``metadata`` reads
    # ``DeclarativeBase.metadata`` (a MetaData object) under from_attributes
    # and fails validation. validation_alias reads the real attribute while
    # serialization_alias keeps ``metadata`` as the JSON key.
    metadata: dict[str, str] = Field(default_factory=dict, validation_alias="meta_data", serialization_alias="metadata")

    model_config = ConfigDict(from_attributes=True)


class SLAViolationResponse(BaseModel):
    id: UUID
    miner_id: str
    violation_type: str
    severity: str
    metric_value: float
    threshold: float
    created_at: datetime
    resolved_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class CapacitySnapshotResponse(BaseModel):
    id: UUID
    total_miners: int
    active_miners: int
    total_parallel_capacity: int
    total_queue_length: int
    capacity_utilization_pct: float
    forecast_capacity: int
    recommended_scaling: str
    scaling_reason: str
    timestamp: datetime

    model_config = ConfigDict(from_attributes=True)


def get_sla_collector(db: Annotated[AsyncSession, Depends(get_db)]) -> SLACollector:
    return SLACollector(db)


@router.get("/metrics/{miner_id}", response_model=list[SLAMetricResponse])
async def get_miner_sla_metrics(
    miner_id: str,
    sla_collector: Annotated[SLACollector, Depends(get_sla_collector)],
    hours: Annotated[int, Query(ge=1, le=168)] = 24,
    limit: Annotated[int, Query(ge=1, le=500)] = 500,
) -> list[SLAMetricResponse]:
    """Get SLA metrics for a specific miner"""
    try:
        metrics = await sla_collector.get_sla_metrics(miner_id=miner_id, hours=hours, limit=limit)
        return metrics  # type: ignore[return-value]
    except Exception as e:
        logger.error("Error getting SLA metrics for miner %s: %s", miner_id, e)
        logger.exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/metrics", response_model=list[SLAMetricResponse])
async def get_all_sla_metrics(
    sla_collector: Annotated[SLACollector, Depends(get_sla_collector)],
    hours: Annotated[int, Query(ge=1, le=168)] = 24,
    limit: Annotated[int, Query(ge=1, le=500)] = 500,
) -> list[SLAMetricResponse]:
    """Get SLA metrics across all miners"""
    try:
        metrics = await sla_collector.get_sla_metrics(miner_id=None, hours=hours, limit=limit)
        return metrics  # type: ignore[return-value]
    except Exception as e:
        logger.error("Error getting SLA metrics: %s", e)
        logger.exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/violations", response_model=list[SLAViolationResponse])
async def get_sla_violations(
    db: Annotated[AsyncSession, Depends(get_db)],
    miner_id: str | None = None,
    resolved: bool = False,
    limit: Annotated[int, Query(ge=1, le=500)] = 500,
) -> list[SLAViolationResponse]:
    """Get SLA violations"""
    try:
        sla_collector = SLACollector(db)
        violations = await sla_collector.get_sla_violations(miner_id=miner_id, resolved=resolved, limit=limit)
        return violations  # type: ignore[return-value]
    except Exception as e:
        logger.error("Error getting SLA violations: %s", e)
        logger.exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post("/metrics/collect")
async def collect_sla_metrics(
    sla_collector: Annotated[SLACollector, Depends(get_sla_collector)], _: Annotated[dict[str, Any], Depends(_governance_auth)]
) -> dict[str, Any]:
    """Trigger SLA metrics collection for all miners"""
    try:
        results = await sla_collector.collect_all_miner_metrics()
        return results
    except Exception as e:
        logger.error("Error collecting SLA metrics: %s", e)
        logger.exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/capacity/snapshots", response_model=list[CapacitySnapshotResponse])
async def get_capacity_snapshots(
    db: Annotated[AsyncSession, Depends(get_db)],
    hours: Annotated[int, Query(ge=1, le=168)] = 24,
    limit: Annotated[int, Query(ge=1, le=500)] = 500,
) -> list[CapacitySnapshotResponse]:
    """Get capacity planning snapshots"""
    try:
        hours_value = hours
        cutoff = datetime.now(UTC) - timedelta(hours=hours_value)
        stmt = (
            select(CapacitySnapshot)
            .where(CapacitySnapshot.timestamp >= cutoff)
            .order_by(desc(CapacitySnapshot.timestamp))
            .limit(limit)
        )
        result = await db.execute(stmt)
        snapshots = result.scalars().all()
        return snapshots  # type: ignore[return-value]
    except Exception as e:
        logger.error("Error getting capacity snapshots: %s", e)
        logger.exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


# #1395 (POOLHUB-FAB-1): these endpoints used to return hardcoded constants
# labeled ``source: coordinator_api`` without calling anything, and the
# alerts-configure endpoint acknowledged a "configured" state that was never
# persisted. There is no forecasting engine and no alert-config store, so the
# honest answer is 501 — the same contract edge/gpu use for defined-but-
# unimplemented routes. Real capacity data is available at
# GET /v1/sla/capacity/snapshots.
_CAPACITY_NOT_IMPLEMENTED = (
    "capacity forecasting is not implemented: pool-hub has no forecast engine and "
    "coordinator-api exposes no capacity-forecast endpoint; see GET /v1/sla/capacity/snapshots "
    "for recorded capacity snapshots"
)
_ALERTS_NOT_IMPLEMENTED = (
    "capacity alert configuration is not implemented: pool-hub has no alert-config store, "
    "so accepting a configuration here would acknowledge state that is never persisted"
)


@router.get("/capacity/forecast")
def get_capacity_forecast(
    hours_ahead: Annotated[int, Query(ge=1, le=8760)] = 168,
) -> dict[str, Any]:
    """Capacity forecast — not implemented (see _CAPACITY_NOT_IMPLEMENTED)."""
    raise HTTPException(status_code=501, detail=_CAPACITY_NOT_IMPLEMENTED)


@router.get("/capacity/recommendations")
def get_scaling_recommendations() -> dict[str, Any]:
    """Auto-scaling recommendations — not implemented (see _CAPACITY_NOT_IMPLEMENTED)."""
    raise HTTPException(status_code=501, detail=_CAPACITY_NOT_IMPLEMENTED)


@router.post("/capacity/alerts/configure")
def configure_capacity_alerts(
    alert_config: dict[str, Any],
    _: Annotated[dict[str, Any], Depends(_governance_auth)],
) -> dict[str, Any]:
    """Configure capacity alerts — not implemented (see _ALERTS_NOT_IMPLEMENTED)."""
    raise HTTPException(status_code=501, detail=_ALERTS_NOT_IMPLEMENTED)


@router.get("/status")
async def get_sla_status(db: Annotated[AsyncSession, Depends(get_db)]) -> dict[str, Any]:
    """Get overall SLA status"""
    try:
        sla_collector = SLACollector(db)
        active_violations = await sla_collector.get_sla_violations(resolved=False)
        recent_metrics = await sla_collector.get_sla_metrics(hours=1)
        if any(v.severity == "critical" for v in active_violations):
            status = "critical"
        elif any(v.severity == "high" for v in active_violations):
            status = "degraded"
        else:
            status = "healthy"
        return {
            "status": status,
            "active_violations": len(active_violations),
            "recent_metrics_count": len(recent_metrics),
            "timestamp": datetime.now(UTC).isoformat(),
        }
    except Exception as e:
        logger.error("Error getting SLA status: %s", e)
        logger.exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e
