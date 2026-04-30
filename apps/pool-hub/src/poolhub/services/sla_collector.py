"""
SLA Metrics Collection Service for Pool-Hub
Collects and tracks SLA metrics for miners including uptime, response time, job completion rate, and capacity availability.
"""

import asyncio
from datetime import datetime, UTC, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Any

from aitbc import get_logger
from sqlalchemy import and_, desc, func, select
from sqlalchemy.orm import Session

from ..models import (
    Miner,
    MinerStatus,
    SLAMetric,
    SLAViolation,
    Feedback,
    MatchRequest,
    MatchResult,
    CapacitySnapshot,
)

logger = get_logger(__name__)


class SLACollector:
    """Service for collecting and tracking SLA metrics for miners"""

    def __init__(self, db: Session):
        self.db = db
        self.sla_thresholds = {
            "uptime_pct": 95.0,
            "response_time_ms": 1000.0,
            "completion_rate_pct": 90.0,
            "capacity_availability_pct": 80.0,
        }

    async def record_sla_metric(
        self,
        miner_id: str,
        metric_type: str,
        metric_value: float,
        metadata: Optional[Dict[str, str]] = None,
    ) -> SLAMetric:
        """Record an SLA metric for a miner"""

        threshold = self.sla_thresholds.get(metric_type, 100.0)
        is_violation = self._check_violation(metric_type, metric_value, threshold)

        # Create SLA metric record
        sla_metric = SLAMetric(
            miner_id=miner_id,
            metric_type=metric_type,
            metric_value=metric_value,
            threshold=threshold,
            is_violation=is_violation,
            timestamp=datetime.now(datetime.UTC),
            meta_data=metadata or {},
        )

        self.db.add(sla_metric)
        await self.db.commit()

        # Create violation record if threshold breached
        if is_violation:
            await self._record_violation(
                miner_id, metric_type, metric_value, threshold, metadata
            )

        logger.info(
            f"Recorded SLA metric: miner={miner_id}, type={metric_type}, "
            f"value={metric_value}, violation={is_violation}"
        )

        return sla_metric

    async def collect_miner_uptime(self, miner_id: str) -> float:
        """Calculate miner uptime percentage based on heartbeat intervals"""

        # Get miner status
        stmt = select(MinerStatus).where(MinerStatus.miner_id == miner_id)
        miner_status = (await self.db.execute(stmt)).scalar_one_or_none()

        if not miner_status:
            return 0.0

        # Calculate uptime based on last heartbeat
        if miner_status.last_heartbeat_at:
            time_since_heartbeat = (
                datetime.now(datetime.UTC) - miner_status.last_heartbeat_at
            ).total_seconds()

            # Consider miner down if no heartbeat for 5 minutes
            if time_since_heartbeat > 300:
                uptime_pct = 0.0
            else:
                uptime_pct = 100.0 - (time_since_heartbeat / 300.0) * 100.0
                uptime_pct = max(0.0, min(100.0, uptime_pct))
        else:
            uptime_pct = 0.0

        # Update miner status with uptime
        miner_status.uptime_pct = uptime_pct
        self.db.commit()

        # Record SLA metric
        await self.record_sla_metric(
            miner_id, "uptime_pct", uptime_pct, {"method": "heartbeat_based"}
        )

        return uptime_pct

    async def collect_response_time(self, miner_id: str) -> Optional[float]:
        """Calculate average response time for a miner from match results"""

        # Get recent match results for this miner
        stmt = (
            select(MatchResult)
            .where(MatchResult.miner_id == miner_id)
            .order_by(desc(MatchResult.created_at))
            .limit(100)
        )
        results = (await self.db.execute(stmt)).scalars().all()

        if not results:
            return None

        # Calculate average response time (eta_ms)
        response_times = [r.eta_ms for r in results if r.eta_ms is not None]

        if not response_times:
            return None

        avg_response_time = sum(response_times) / len(response_times)

        # Record SLA metric
        await self.record_sla_metric(
            miner_id,
            "response_time_ms",
            avg_response_time,
            {"method": "match_results", "sample_size": len(response_times)},
        )

        return avg_response_time

    async def collect_completion_rate(self, miner_id: str) -> Optional[float]:
        """Calculate job completion rate for a miner from feedback"""

        # Get recent feedback for this miner
        stmt = (
            select(Feedback)
            .where(Feedback.miner_id == miner_id)
            .where(Feedback.created_at >= datetime.now(datetime.UTC) - timedelta(days=7))
            .order_by(Feedback.created_at.desc())
            .limit(100)
        )
        feedback_records = (await self.db.execute(stmt)).scalars().all()

        if not feedback_records:
            return None

        # Calculate completion rate (successful outcomes)
        successful = sum(1 for f in feedback_records if f.outcome == "success")
        completion_rate = (successful / len(feedback_records)) * 100.0

        # Record SLA metric
        await self.record_sla_metric(
            miner_id,
            "completion_rate_pct",
            completion_rate,
            {"method": "feedback", "sample_size": len(feedback_records)},
        )

        return completion_rate

    async def collect_capacity_availability(self) -> Dict[str, Any]:
        """Collect capacity availability metrics across all miners"""

        # Get all miner statuses
        stmt = select(MinerStatus)
        miner_statuses = (await self.db.execute(stmt)).scalars().all()

        if not miner_statuses:
            return {
                "total_miners": 0,
                "active_miners": 0,
                "capacity_availability_pct": 0.0,
            }

        total_miners = len(miner_statuses)
        active_miners = sum(1 for ms in miner_statuses if not ms.busy)
        capacity_availability_pct = (active_miners / total_miners) * 100.0

        # Record capacity snapshot
        snapshot = CapacitySnapshot(
            total_miners=total_miners,
            active_miners=active_miners,
            total_parallel_capacity=sum(
                m.max_parallel for m in (await self.db.execute(select(Miner))).scalars().all()
            ),
            total_queue_length=sum(ms.queue_len for ms in miner_statuses),
            capacity_utilization_pct=100.0 - capacity_availability_pct,
            forecast_capacity=total_miners,  # Would be calculated from forecasting
            recommended_scaling="stable",
            scaling_reason="Capacity within normal range",
            timestamp=datetime.now(datetime.UTC),
            meta_data={"method": "real_time_collection"},
        )

        self.db.add(snapshot)
        await self.db.commit()

        logger.info(
            f"Capacity snapshot: total={total_miners}, active={active_miners}, "
            f"availability={capacity_availability_pct:.2f}%"
        )

        return {
            "total_miners": total_miners,
            "active_miners": active_miners,
            "capacity_availability_pct": capacity_availability_pct,
        }

    async def collect_all_miner_metrics(self) -> Dict[str, Any]:
        """Collect all SLA metrics for all miners"""

        # Get all miners
        stmt = select(Miner)
        miners = self.db.execute(stmt).scalars().all()

        results = {
            "miners_processed": 0,
            "metrics_collected": [],
            "violations_detected": 0,
        }

        for miner in miners:
            try:
                # Collect each metric type
                uptime = await self.collect_miner_uptime(miner.miner_id)
                response_time = await self.collect_response_time(miner.miner_id)
                completion_rate = await self.collect_completion_rate(miner.miner_id)

                results["metrics_collected"].append(
                    {
                        "miner_id": miner.miner_id,
                        "uptime_pct": uptime,
                        "response_time_ms": response_time,
                        "completion_rate_pct": completion_rate,
                    }
                )

                results["miners_processed"] += 1

            except Exception as e:
                logger.error(f"Failed to collect metrics for miner {miner.miner_id}: {e}")

        # Collect capacity metrics
        capacity = await self.collect_capacity_availability()
        results["capacity"] = capacity

        # Count violations in this collection cycle
        stmt = (
            select(func.count(SLAViolation.id))
            .where(SLAViolation.resolved_at.is_(None))
            .where(SLAViolation.created_at >= datetime.now(datetime.UTC) - timedelta(hours=1))
        )
        results["violations_detected"] = self.db.execute(stmt).scalar() or 0

        logger.info(
            f"SLA collection complete: processed={results['miners_processed']}, "
            f"violations={results['violations_detected']}"
        )

        return results

    async def get_sla_metrics(
        self, miner_id: Optional[str] = None, hours: int = 24
    ) -> List[SLAMetric]:
        """Get SLA metrics for a miner or all miners"""

        cutoff = datetime.now(datetime.UTC) - timedelta(hours=hours)

        stmt = select(SLAMetric).where(SLAMetric.timestamp >= cutoff)

        if miner_id:
            stmt = stmt.where(SLAMetric.miner_id == miner_id)

        stmt = stmt.order_by(desc(SLAMetric.timestamp))

        return (await self.db.execute(stmt)).scalars().all()

    async def get_sla_violations(
        self, miner_id: Optional[str] = None, resolved: bool = False
    ) -> List[SLAViolation]:
        """Get SLA violations for a miner or all miners"""

        stmt = select(SLAViolation)

        if miner_id:
            stmt = stmt.where(SLAViolation.miner_id == miner_id)

        if resolved:
            stmt = stmt.where(SLAViolation.resolved_at.isnot_(None))
        else:
            stmt = stmt.where(SLAViolation.resolved_at.is_(None))

        stmt = stmt.order_by(desc(SLAViolation.created_at))

        return (await self.db.execute(stmt)).scalars().all()

    def _check_violation(self, metric_type: str, value: float, threshold: float) -> bool:
        """Check if a metric value violates its SLA threshold"""

        if metric_type in ["uptime_pct", "completion_rate_pct", "capacity_availability_pct"]:
            # Higher is better - violation if below threshold
            return value < threshold
        elif metric_type in ["response_time_ms"]:
            # Lower is better - violation if above threshold
            return value > threshold

        return False

    async def _record_violation(
        self,
        miner_id: str,
        metric_type: str,
        metric_value: float,
        threshold: float,
        metadata: Optional[Dict[str, str]] = None,
    ) -> SLAViolation:
        """Record an SLA violation"""

        # Determine severity
        if metric_type in ["uptime_pct", "completion_rate_pct"]:
            severity = "critical" if metric_value < threshold * 0.8 else "high"
        elif metric_type == "response_time_ms":
            severity = "critical" if metric_value > threshold * 2 else "high"
        else:
            severity = "medium"

        violation = SLAViolation(
            miner_id=miner_id,
            violation_type=metric_type,
            severity=severity,
            metric_value=metric_value,
            threshold=threshold,
            violation_duration_ms=None,  # Will be updated when resolved
            created_at=datetime.now(datetime.UTC),
            meta_data=metadata or {},
        )

        self.db.add(violation)
        await self.db.commit()

        logger.warning(
            f"SLA violation recorded: miner={miner_id}, type={metric_type}, "
            f"severity={severity}, value={metric_value}, threshold={threshold}"
        )

        return violation


class SLACollectorScheduler:
    """Scheduler for automated SLA metric collection"""

    def __init__(self, sla_collector: SLACollector):
        self.sla_collector = sla_collector
        self.logger = get_logger(__name__)
        self.running = False

    async def start(self, collection_interval_seconds: int = 300):
        """Start the SLA collection scheduler"""

        if self.running:
            return

        self.running = True
        self.logger.info("SLA Collector scheduler started")

        # Start collection loop
        asyncio.create_task(self._collection_loop(collection_interval_seconds))

    async def stop(self):
        """Stop the SLA collection scheduler"""

        self.running = False
        self.logger.info("SLA Collector scheduler stopped")

    async def _collection_loop(self, interval_seconds: int):
        """Background task that collects SLA metrics periodically"""

        while self.running:
            try:
                await self.sla_collector.collect_all_miner_metrics()

                # Wait for next collection interval
                await asyncio.sleep(interval_seconds)

            except Exception as e:
                self.logger.error(f"Error in SLA collection loop: {e}")
                await asyncio.sleep(60)  # Retry in 1 minute
