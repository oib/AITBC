"""
SLA and Billing API Endpoints for Pool-Hub
Provides endpoints for SLA metrics, capacity planning, and billing integration.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from decimal import Decimal

from aitbc import get_logger
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..services.sla_collector import SLACollector
from ..services.billing_integration import BillingIntegration
from ..models import SLAMetric, SLAViolation, CapacitySnapshot

logger = get_logger(__name__)

router = APIRouter(prefix="/sla", tags=["SLA"])


# Request/Response Models
class SLAMetricResponse(BaseModel):
    id: str
    miner_id: str
    metric_type: str
    metric_value: float
    threshold: float
    is_violation: bool
    timestamp: datetime
    metadata: Dict[str, str]

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
    resolved_at: Optional[datetime]

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
    miner_id: Optional[str] = None
    hours_back: int = Field(default=24, ge=1, le=168)


class UsageRecordRequest(BaseModel):
    tenant_id: str
    resource_type: str
    quantity: Decimal
    unit_price: Optional[Decimal] = None
    job_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class InvoiceGenerationRequest(BaseModel):
    tenant_id: str
    period_start: datetime
    period_end: datetime


# Dependency injection
def get_sla_collector(db: Session = Depends(get_db)) -> SLACollector:
    return SLACollector(db)


def get_billing_integration(db: Session = Depends(get_db)) -> BillingIntegration:
    return BillingIntegration(db)


# SLA Metrics Endpoints
@router.get("/metrics/{miner_id}", response_model=List[SLAMetricResponse])
async def get_miner_sla_metrics(
    miner_id: str,
    hours: int = Query(default=24, ge=1, le=168),
    sla_collector: SLACollector = Depends(get_sla_collector),
):
    """Get SLA metrics for a specific miner"""
    try:
        metrics = await sla_collector.get_sla_metrics(miner_id=miner_id, hours=hours)
        return metrics
    except Exception as e:
        logger.error(f"Error getting SLA metrics for miner {miner_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/metrics", response_model=List[SLAMetricResponse])
async def get_all_sla_metrics(
    hours: int = Query(default=24, ge=1, le=168),
    sla_collector: SLACollector = Depends(get_sla_collector),
):
    """Get SLA metrics across all miners"""
    try:
        metrics = await sla_collector.get_sla_metrics(miner_id=None, hours=hours)
        return metrics
    except Exception as e:
        logger.error(f"Error getting SLA metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/violations", response_model=List[SLAViolationResponse])
async def get_sla_violations(
    miner_id: Optional[str] = Query(default=None),
    resolved: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    """Get SLA violations"""
    try:
        sla_collector = SLACollector(db)
        violations = await sla_collector.get_sla_violations(
            miner_id=miner_id, resolved=resolved
        )
        return violations
    except Exception as e:
        logger.error(f"Error getting SLA violations: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/metrics/collect")
async def collect_sla_metrics(
    sla_collector: SLACollector = Depends(get_sla_collector),
):
    """Trigger SLA metrics collection for all miners"""
    try:
        results = await sla_collector.collect_all_miner_metrics()
        return results
    except Exception as e:
        logger.error(f"Error collecting SLA metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Capacity Planning Endpoints
@router.get("/capacity/snapshots", response_model=List[CapacitySnapshotResponse])
async def get_capacity_snapshots(
    hours: int = Query(default=24, ge=1, le=168),
    db: Session = Depends(get_db),
):
    """Get capacity planning snapshots"""
    try:
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        stmt = (
            db.query(CapacitySnapshot)
            .filter(CapacitySnapshot.timestamp >= cutoff)
            .order_by(CapacitySnapshot.timestamp.desc())
        )
        snapshots = stmt.all()
        return snapshots
    except Exception as e:
        logger.error(f"Error getting capacity snapshots: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/capacity/forecast")
async def get_capacity_forecast(
    hours_ahead: int = Query(default=168, ge=1, le=8760),
    billing_integration: BillingIntegration = Depends(get_billing_integration),
):
    """Get capacity forecast from coordinator-api"""
    try:
        # This would call coordinator-api's capacity planning endpoint
        # For now, return a placeholder response
        return {
            "forecast_horizon_hours": hours_ahead,
            "current_capacity": 1000,
            "projected_capacity": 1500,
            "recommended_scaling": "+50%",
            "confidence": 0.85,
            "source": "coordinator_api",
        }
    except Exception as e:
        logger.error(f"Error getting capacity forecast: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/capacity/recommendations")
async def get_scaling_recommendations(
    billing_integration: BillingIntegration = Depends(get_billing_integration),
):
    """Get auto-scaling recommendations from coordinator-api"""
    try:
        # This would call coordinator-api's capacity planning endpoint
        # For now, return a placeholder response
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
        logger.error(f"Error getting scaling recommendations: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/capacity/alerts/configure")
async def configure_capacity_alerts(
    alert_config: Dict[str, Any],
    db: Session = Depends(get_db),
):
    """Configure capacity alerts"""
    try:
        # Store alert configuration (would be persisted to database)
        return {
            "status": "configured",
            "alert_config": alert_config,
            "timestamp": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        logger.error(f"Error configuring capacity alerts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Billing Integration Endpoints
@router.get("/billing/usage")
async def get_billing_usage(
    tenant_id: Optional[str] = Query(default=None),
    hours: int = Query(default=24, ge=1, le=168),
    billing_integration: BillingIntegration = Depends(get_billing_integration),
):
    """Get billing usage data from coordinator-api"""
    try:
        metrics = await billing_integration.get_billing_metrics(
            tenant_id=tenant_id, hours=hours
        )
        return metrics
    except Exception as e:
        logger.error(f"Error getting billing usage: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/billing/sync")
async def sync_billing_usage(
    request: UsageSyncRequest,
    billing_integration: BillingIntegration = Depends(get_billing_integration),
):
    """Trigger billing sync with coordinator-api"""
    try:
        if request.miner_id:
            # Sync specific miner
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(hours=request.hours_back)
            result = await billing_integration.sync_miner_usage(
                miner_id=request.miner_id, start_date=start_date, end_date=end_date
            )
        else:
            # Sync all miners
            result = await billing_integration.sync_all_miners_usage(
                hours_back=request.hours_back
            )
        return result
    except Exception as e:
        logger.error(f"Error syncing billing usage: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/billing/usage/record")
async def record_usage(
    request: UsageRecordRequest,
    billing_integration: BillingIntegration = Depends(get_billing_integration),
):
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
        return result
    except Exception as e:
        logger.error(f"Error recording usage: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/billing/invoice/generate")
async def generate_invoice(
    request: InvoiceGenerationRequest,
    billing_integration: BillingIntegration = Depends(get_billing_integration),
):
    """Trigger invoice generation in coordinator-api"""
    try:
        result = await billing_integration.trigger_invoice_generation(
            tenant_id=request.tenant_id,
            period_start=request.period_start,
            period_end=request.period_end,
        )
        return result
    except Exception as e:
        logger.error(f"Error generating invoice: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Health and Status Endpoints
@router.get("/status")
async def get_sla_status(db: Session = Depends(get_db)):
    """Get overall SLA status"""
    try:
        sla_collector = SLACollector(db)

        # Get recent violations
        active_violations = await sla_collector.get_sla_violations(resolved=False)

        # Get recent metrics
        recent_metrics = await sla_collector.get_sla_metrics(hours=1)

        # Calculate overall status
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
            "timestamp": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        logger.error(f"Error getting SLA status: {e}")
        raise HTTPException(status_code=500, detail=str(e))
