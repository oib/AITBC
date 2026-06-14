"""Edge metrics service for Edge API Service"""

from typing import Any
from uuid import uuid4

from sqlmodel import delete, select

from ..schemas.metrics import EdgeMetrics
from ..storage import get_session


class MetricsService:
    """Service for edge metrics operations"""

    async def record_metrics(self, gpu_id: str, metrics: dict[str, Any]) -> dict[str, Any]:
        """Record edge metrics"""
        async with get_session() as session:
            metric_id = f"metric_{uuid4().hex[:8]}"

            metric = EdgeMetrics(
                metric_id=metric_id,
                gpu_id=gpu_id,
                metrics_data=metrics
            )
            session.add(metric)
            await session.commit()

            return {
                "success": True,
                "metric_id": metric_id,
                "message": f"Metrics {metric_id} recorded"
            }

    async def get_metrics(self, metric_id: str) -> dict[str, Any] | None:
        """Get metric details"""
        async with get_session() as session:
            result = await session.execute(select(EdgeMetrics).where(EdgeMetrics.metric_id == metric_id))
            metric = result.scalar_one_or_none()

            if metric:
                return {
                    "metric_id": metric.metric_id,
                    "gpu_id": metric.gpu_id,
                    "metrics_data": metric.metrics_data,
                    "created_at": metric.created_at.isoformat() if metric.created_at else None,
                    "extra_data": metric.extra_data
                }
            return None

    async def list_metrics(self, gpu_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        """List metrics, optionally filtered by gpu_id"""
        async with get_session() as session:
            query = select(EdgeMetrics)

            if gpu_id:
                query = query.where(EdgeMetrics.gpu_id == gpu_id)

            query = query.order_by(EdgeMetrics.created_at.desc())  # type: ignore

            result = await session.execute(query)
            metrics = result.scalars().all()

            return [
                {
                    "metric_id": metric.metric_id,
                    "gpu_id": metric.gpu_id,
                    "metrics_data": metric.metrics_data,
                    "created_at": metric.created_at.isoformat() if metric.created_at else None
                }
                for metric in metrics
            ]

    async def delete_metrics(self, metric_id: str) -> bool:
        """Delete metric"""
        async with get_session() as session:
            stmt = delete(EdgeMetrics).where(EdgeMetrics.metric_id == metric_id)  # type: ignore[arg-type]
            result = await session.execute(stmt)
            await session.commit()
            return bool(result.rowcount > 0)  # type: ignore[attr-defined]
