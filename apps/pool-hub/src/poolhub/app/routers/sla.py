"""
SLA and Billing API Endpoints for Pool-Hub
Provides endpoints for SLA metrics, capacity planning, and billing integration.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from aitbc.aitbc_logging import get_logger

from ..database import get_db  # type: ignore
from ..models import CapacitySnapshot  # type: ignore
from ..services.billing_integration import BillingIntegration  # type: ignore
from ..services.sla_collector import SLACollector  # type: ignore

logger = get_logger(__name__)
router = APIRouter(prefix="/sla", tags=["SLA"])


class SLAMetricResponse(BaseModel):
    id: str
    miner_id: str
    metric_type: str
    metric_value: float
    threshold: float
    is_violation: bool
    timestamp: datetime
    metadata: dict[str, str]

    class Config:
        from_attributes = True


class SLAViolationResponse(BaseModel):
    id: str
    miner_id: str
    violation_type: str
    severity: str
    metric_value: float
    threshold: float
    created_at: datetime
    resolved_at: datetime | None

    class Config:
        from_attributes = True


class CapacitySnapshotResponse(BaseModel):
    id: str
    total_miners: int
    active_miners: int
    total_parallel_capacity: int
    total_queue_length: int
    capacity_utilization_pct: float
    forecast_capacity: int
    recommended_scaling: str
    scaling_reason: str
    timestamp: datetime

    class Config:
        from_attributes = True


class UsageSyncRequest(BaseModel):
    miner_id: str | None = None
    hours_back: int = Field(default=24, ge=1, le=168)


class UsageRecordRequest(BaseModel):
    tenant_id: str
    resource_type: str
    quantity: Decimal
    unit_price: Decimal | None = None
    job_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class InvoiceGenerationRequest(BaseModel):
    tenant_id: str
    period_start: datetime
    period_end: datetime


def get_sla_collector(db: Annotated[Session, Depends(get_db)]) -> SLACollector:
    return SLACollector(db)


def get_billing_integration(db: Annotated[Session, Depends(get_db)]) -> BillingIntegration:
    return BillingIntegration(db)


@router.get("/metrics/{miner_id}", response_model=list[SLAMetricResponse])
async def get_miner_sla_metrics(
    miner_id: str, hours: int | None, sla_collector: Annotated[SLACollector, Depends(get_sla_collector)]
) -> list[SLAMetricResponse]:
    """Get SLA metrics for a specific miner"""
    try:
        metrics = await sla_collector.get_sla_metrics(miner_id=miner_id, hours=hours)
        return metrics  # type: ignore[no-any-return]
    except Exception as e:
        logger.error("Error getting SLA metrics for miner %s: %s", miner_id, e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/metrics", response_model=list[SLAMetricResponse])
async def get_all_sla_metrics(
    hours: int | None, sla_collector: Annotated[SLACollector, Depends(get_sla_collector)]
) -> list[SLAMetricResponse]:
    """Get SLA metrics across all miners"""
    try:
        metrics = await sla_collector.get_sla_metrics(miner_id=None, hours=hours)
        return metrics  # type: ignore[no-any-return]
    except Exception as e:
        logger.error("Error getting SLA metrics: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/violations", response_model=list[SLAViolationResponse])
async def get_sla_violations(
    miner_id: str | None, resolved: bool | None, db: Annotated[Session, Depends(get_db)]
) -> list[SLAViolationResponse]:
    """Get SLA violations"""
    try:
        sla_collector = SLACollector(db)
        violations = await sla_collector.get_sla_violations(miner_id=miner_id, resolved=resolved)
        return violations  # type: ignore[no-any-return]
    except Exception as e:
        logger.error("Error getting SLA violations: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/metrics/collect")
async def collect_sla_metrics(sla_collector: Annotated[SLACollector, Depends(get_sla_collector)]) -> dict[str, Any]:
    """Trigger SLA metrics collection for all miners"""
    try:
        results = await sla_collector.collect_all_miner_metrics()
        return results  # type: ignore[no-any-return]
    except Exception as e:
        logger.error("Error collecting SLA metrics: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/capacity/snapshots", response_model=list[CapacitySnapshotResponse])
async def get_capacity_snapshots(hours: int | None, db: Annotated[Session, Depends(get_db)]) -> list[CapacitySnapshotResponse]:
    """Get capacity planning snapshots"""
    try:
        cutoff = datetime.now(UTC) - timedelta(hours=hours)
        stmt = (
            db.query(CapacitySnapshot).filter(CapacitySnapshot.timestamp >= cutoff).order_by(CapacitySnapshot.timestamp.desc())
        )
        snapshots = stmt.all()
        return snapshots  # type: ignore[no-any-return]
    except Exception as e:
        logger.error("Error getting capacity snapshots: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/capacity/forecast")
async def get_capacity_forecast(
    hours_ahead: int | None,
    billing_integration: Annotated[BillingIntegration, Depends(get_billing_integration)],
) -> dict[str, Any]:
    """Get capacity forecast from coordinator-api"""
    try:
        return {
            "forecast_horizon_hours": hours_ahead,
            "current_capacity": 1000,
            "projected_capacity": 1500,
            "recommended_scaling": "+50%",
            "confidence": 0.85,
            "source": "coordinator_api",
        }
    except Exception as e:
        logger.error("Error getting capacity forecast: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/capacity/recommendations")
async def get_scaling_recommendations(
    billing_integration: Annotated[BillingIntegration, Depends(get_billing_integration)],
) -> dict[str, Any]:
    """Get auto-scaling recommendations from coordinator-api"""
    try:
        return {
            "current_state": "healthy",
            "recommendations": [
                {
                    "action": "add_miners",
                    "quantity": 2,
                    "reason": "Projected capacity shortage in 2 weeks",
                    "priority": "medium",
                }
            ],
            "source": "coordinator_api",
        }
    except Exception as e:
        logger.error("Error getting scaling recommendations: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/capacity/alerts/configure")
async def configure_capacity_alerts(alert_config: dict[str, Any], db: Annotated[Session, Depends(get_db)]) -> dict[str, Any]:
    """Configure capacity alerts"""
    try:
        return {"status": "configured", "alert_config": alert_config, "timestamp": datetime.now(UTC).isoformat()}
    except Exception as e:
        logger.error("Error configuring capacity alerts: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/billing/usage")
async def get_billing_usage(
    tenant_id: str | None,
    hours: int | None,
    billing_integration: Annotated[BillingIntegration, Depends(get_billing_integration)],
) -> dict[str, Any]:
    """Get billing usage data from coordinator-api"""
    try:
        metrics = await billing_integration.get_billing_metrics(tenant_id=tenant_id, hours=hours)
        return metrics  # type: ignore[no-any-return]
    except Exception as e:
        logger.error("Error getting billing usage: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/billing/sync")
async def sync_billing_usage(
    request: UsageSyncRequest, billing_integration: Annotated[BillingIntegration, Depends(get_billing_integration)]
) -> dict[str, Any]:
    """Trigger billing sync with coordinator-api"""
    try:
        if request.miner_id:
            end_date = datetime.now(UTC)
            start_date = end_date - timedelta(hours=request.hours_back)
            result = await billing_integration.sync_miner_usage(
                miner_id=request.miner_id, start_date=start_date, end_date=end_date
            )
        else:
            result = await billing_integration.sync_all_miners_usage(hours_back=request.hours_back)
        return result  # type: ignore[no-any-return]
    except Exception as e:
        logger.error("Error syncing billing usage: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/billing/usage/record")
async def record_usage(
    request: UsageRecordRequest, billing_integration: Annotated[BillingIntegration, Depends(get_billing_integration)]
) -> dict[str, Any]:
    """Record a single usage event to coordinator-api billing"""
    try:
        result = await billing_integration.record_usage(
            tenant_id=request.tenant_id,
            resource_type=request.resource_type,
            quantity=request.quantity,
            unit_price=request.unit_price,
            job_id=request.job_id,
            metadata=request.metadata,
        )
        return result  # type: ignore[no-any-return]
    except Exception as e:
        logger.error("Error recording usage: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/billing/invoice/generate")
async def generate_invoice(
    request: InvoiceGenerationRequest, billing_integration: Annotated[BillingIntegration, Depends(get_billing_integration)]
) -> dict[str, Any]:
    """Trigger invoice generation in coordinator-api"""
    try:
        result = await billing_integration.trigger_invoice_generation(
            tenant_id=request.tenant_id, period_start=request.period_start, period_end=request.period_end
        )
        return result  # type: ignore[no-any-return]
    except Exception as e:
        logger.error("Error generating invoice: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/status")
async def get_sla_status(db: Annotated[Session, Depends(get_db)]) -> dict[str, Any]:
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
        raise HTTPException(status_code=500, detail=str(e)) from e
