"""Market Analytics Service for real-time metrics and trend analysis."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from statistics import mean
from typing import Any

from sqlmodel import Session, select

from aitbc import get_logger

from ..domain.gpu_marketplace import (
    GPUBooking,
    GPURegistry,
)

logger = get_logger(__name__)


class MarketAnalytics:
    """Real-time market analytics and trend analysis."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_realtime_metrics(self) -> dict[str, Any]:
        """Calculate current market state metrics."""
        try:
            # Get all GPUs
            gpus = self.session.execute(select(GPURegistry)).scalars().all()
            
            # Calculate metrics
            total_gpus = len(gpus)
            available_gpus = [g for g in gpus if g.status == "available"]
            booked_gpus = [g for g in gpus if g.status == "booked"]
            offline_gpus = [g for g in gpus if g.status == "offline"]
            
            # Capacity metrics
            total_capacity = sum(g.capacity for g in gpus)
            available_capacity = sum(g.capacity for g in available_gpus)
            allocated_capacity = sum(g.allocated for g in gpus)
            
            # Pricing metrics
            available_prices = [g.price_per_hour for g in available_gpus if g.price_per_hour]
            avg_price = mean(available_prices) if available_prices else 0.0
            min_price = min(available_prices) if available_prices else 0.0
            max_price = max(available_prices) if available_prices else 0.0
            
            # Utilization metrics
            avg_utilization = mean([g.utilization for g in gpus]) if gpus else 0.0
            
            # Booking metrics
            active_bookings = self.session.execute(
                select(GPUBooking).where(GPUBooking.status == "active")
            ).scalars().all()
            
            return {
                "timestamp": datetime.now(UTC).isoformat(),
                "total_gpus": total_gpus,
                "available_gpus": len(available_gpus),
                "booked_gpus": len(booked_gpus),
                "offline_gpus": len(offline_gpus),
                "total_capacity": total_capacity,
                "available_capacity": available_capacity,
                "allocated_capacity": allocated_capacity,
                "avg_price": round(avg_price, 4),
                "min_price": round(min_price, 4),
                "max_price": round(max_price, 4),
                "avg_utilization": round(avg_utilization, 4),
                "active_bookings": len(active_bookings),
            }
        except Exception as e:
            logger.error(f"Failed to calculate realtime metrics: {e}")
            return {}

    def analyze_trends(self, hours: int = 24) -> dict[str, Any]:
        """Analyze market trends over specified time period."""
        try:
            cutoff_time = datetime.now(UTC) - timedelta(hours=hours)
            
            # Get recent bookings
            recent_bookings = self.session.execute(
                select(GPUBooking).where(GPUBooking.created_at >= cutoff_time)
            ).scalars().all()
            
            # Calculate trend metrics
            bookings_per_hour = len(recent_bookings) / hours if hours > 0 else 0
            
            # Price trend (simplified - would use price_history in production)
            gpus = self.session.execute(select(GPURegistry)).scalars().all()
            avg_price = mean([g.price_per_hour for g in gpus if g.price_per_hour]) if gpus else 0.0
            
            # Utilization trend
            avg_utilization = mean([g.utilization for g in gpus]) if gpus else 0.0
            
            return {
                "period_hours": hours,
                "total_bookings": len(recent_bookings),
                "bookings_per_hour": round(bookings_per_hour, 2),
                "avg_price": round(avg_price, 4),
                "avg_utilization": round(avg_utilization, 4),
                "trend_direction": "increasing" if bookings_per_hour > 1 else "stable",
            }
        except Exception as e:
            logger.error(f"Failed to analyze trends: {e}")
            return {}

    def generate_forecasts(self, hours_ahead: int = 24) -> dict[str, Any]:
        """Generate market forecasts using time series analysis."""
        try:
            # Get current metrics
            current_metrics = self.get_realtime_metrics()
            
            # Simple linear forecast (would use ML in production)
            bookings_per_hour = current_metrics.get("active_bookings", 0) / 24 if current_metrics.get("active_bookings", 0) > 0 else 0
            
            forecasted_bookings = bookings_per_hour * hours_ahead
            
            # Price forecast (stable assumption)
            forecasted_price = current_metrics.get("avg_price", 0.0)
            
            # Utilization forecast
            current_utilization = current_metrics.get("avg_utilization", 0.0)
            forecasted_utilization = min(1.0, current_utilization + 0.05)  # Slight increase
            
            return {
                "forecast_hours": hours_ahead,
                "forecasted_bookings": round(forecasted_bookings, 2),
                "forecasted_price": round(forecasted_price, 4),
                "forecasted_utilization": round(forecasted_utilization, 4),
                "confidence": 0.7,  # Would be calculated from ML model
            }
        except Exception as e:
            logger.error(f"Failed to generate forecasts: {e}")
            return {}

    def track_event(self, event_type: str, resource_id: str, metadata: dict[str, Any] | None = None) -> bool:
        """Track marketplace events for analytics."""
        try:
            # In production, this would store to analytics_event table
            logger.info(f"Event tracked: {event_type} for resource {resource_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to track event: {e}")
            return False
