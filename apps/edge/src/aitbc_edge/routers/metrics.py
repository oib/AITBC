# mypy: ignore-errors
"""Metrics operations router for Edge API Service"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..services.metrics_service import MetricsService

router = APIRouter()


class RecordMetricsRequest(BaseModel):
    """Request model for recording metrics"""
    gpu_id: str
    metrics: dict


def get_metrics_service() -> MetricsService:
    """Dependency injection for metrics service"""
    return MetricsService()


@router.post("/")
async def record_metrics(request: RecordMetricsRequest, svc: MetricsService = Depends(get_metrics_service)):
    """Record edge metrics"""
    result = await svc.record_metrics(request.gpu_id, request.metrics)
    return result


@router.get("/")
async def list_metrics(gpu_id: str = Query(None), limit: int = Query(100), svc: MetricsService = Depends(get_metrics_service)):
    """List metrics, optionally filtered by gpu_id"""
    metrics = await svc.list_metrics(gpu_id, limit)
    return {"metrics": metrics, "total": len(metrics)}


@router.get("/{metric_id}")
async def get_metrics(metric_id: str, svc: MetricsService = Depends(get_metrics_service)):
    """Get metric details"""
    metric = await svc.get_metrics(metric_id)
    if metric is None:
        raise HTTPException(status_code=404, detail=f"Metric {metric_id} not found")
    return metric


@router.delete("/{metric_id}")
async def delete_metrics(metric_id: str, svc: MetricsService = Depends(get_metrics_service)):
    """Delete metric"""
    success = await svc.delete_metrics(metric_id)
    if success:
        return {"message": f"Metric {metric_id} deleted"}
    else:
        raise HTTPException(status_code=404, detail=f"Metric {metric_id} not found")
