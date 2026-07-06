"""
SLA Metrics Collection Service for Pool-Hub
Collects and tracks SLA metrics for miners including uptime, response time, job completion rate, and capacity availability.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from aitbc.aitbc_logging import get_logger
from aitbc.async_tasks import create_task_with_logging

from ..models import CapacitySnapshot, Feedback, MatchResult, Miner, MinerStatus, SLAMetric, SLAViolation

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
        self, miner_id: str, metric_type: str, metric_value: float, metadata: dict[str, str] | None = None
    ) -> SLAMetric:
        """Record an SLA metric for a miner"""
        threshold = self.sla_thresholds.get(metric_type, 100.0)
        is_violation = self._check_violation(metric_type, metric_value, threshold)
        sla_metric = SLAMetric(
            miner_id=miner_id,
            metric_type=metric_type,
            metric_value=metric_value,
            threshold=threshold,
            is_violation=is_violation,
            timestamp=datetime.now(UTC),
            meta_data=metadata or {},
        )
        self.db.add(sla_metric)
        await self.db.commit()  # type: ignore[misc, func-returns-value]
        if is_violation:
            await self._record_violation(miner_id, metric_type, metric_value, threshold, metadata)
        logger.info(
            "Recorded SLA metric: miner=%s, type=%s, value=%s, violation=%s", miner_id, metric_type, metric_value, is_violation
        )
        return sla_metric

    async def collect_miner_uptime(self, miner_id: str) -> float:
        """Calculate miner uptime percentage based on heartbeat intervals"""
        stmt = select(MinerStatus).where(MinerStatus.miner_id == miner_id)
        miner_status = (await self.db.execute(stmt)).scalar_one_or_none()  # type: ignore[misc]
        if not miner_status:
            return 0.0
        if miner_status.last_heartbeat_at:
            time_since_heartbeat = (datetime.now(UTC) - miner_status.last_heartbeat_at).total_seconds()
            if time_since_heartbeat > 300:
                uptime_pct = 0.0
            else:
                uptime_pct = 100.0 - time_since_heartbeat / 300.0 * 100.0
                uptime_pct = max(0.0, min(100.0, uptime_pct))
        else:
            uptime_pct = 0.0
        miner_status.uptime_pct = uptime_pct
        self.db.commit()
        await self.record_sla_metric(miner_id, "uptime_pct", uptime_pct, {"method": "heartbeat_based"})
        return uptime_pct

    async def collect_response_time(self, miner_id: str) -> float | None:
        """Calculate average response time for a miner from match results"""
        stmt = select(MatchResult).where(MatchResult.miner_id == miner_id).order_by(desc(MatchResult.created_at)).limit(100)
        results = (await self.db.execute(stmt)).scalars().all()  # type: ignore[misc]
        if not results:
            return None
        response_times = [r.eta_ms for r in results if r.eta_ms is not None]
        if not response_times:
            return None
        avg_response_time: float = sum(response_times) / len(response_times)
        await self.record_sla_metric(
            miner_id,
            "response_time_ms",
            avg_response_time,
            {"method": "match_results", "sample_size": str(len(response_times))},
        )
        return avg_response_time

    async def collect_completion_rate(self, miner_id: str) -> float | None:
        """Calculate job completion rate for a miner from feedback"""
        stmt = (
            select(Feedback)
            .where(Feedback.miner_id == miner_id)
            .where(Feedback.created_at >= datetime.now(UTC) - timedelta(days=7))
            .order_by(Feedback.created_at.desc())
            .limit(100)
        )
        feedback_records = (await self.db.execute(stmt)).scalars().all()  # type: ignore[misc]
        if not feedback_records:
            return None
        successful = sum(1 for f in feedback_records if f.outcome == "success")
        completion_rate = successful / len(feedback_records) * 100.0
        await self.record_sla_metric(
            miner_id, "completion_rate_pct", completion_rate, {"method": "feedback", "sample_size": str(len(feedback_records))}
        )
        return completion_rate

    async def collect_capacity_availability(self) -> dict[str, Any]:
        """Collect capacity availability metrics across all miners"""
        stmt = select(MinerStatus)
        miner_statuses = (await self.db.execute(stmt)).scalars().all()  # type: ignore[misc]
        if not miner_statuses:
            return {"total_miners": 0, "active_miners": 0, "capacity_availability_pct": 0.0}
        total_miners = len(miner_statuses)
        active_miners = sum(1 for ms in miner_statuses if not ms.busy)
        capacity_availability_pct = active_miners / total_miners * 100.0
        snapshot = CapacitySnapshot(
            total_miners=total_miners,
            active_miners=active_miners,
            total_parallel_capacity=sum(m.max_parallel for m in (await self.db.execute(select(Miner))).scalars().all()),  # type: ignore[misc]
            total_queue_length=sum(ms.queue_len for ms in miner_statuses),
            capacity_utilization_pct=100.0 - capacity_availability_pct,
            forecast_capacity=total_miners,
            recommended_scaling="stable",
            scaling_reason="Capacity within normal range",
            timestamp=datetime.now(UTC),
            meta_data={"method": "real_time_collection"},
        )
        self.db.add(snapshot)
        await self.db.commit()  # type: ignore[misc, func-returns-value]
        logger.info(
            "Capacity snapshot: total=%s, active=%s, availability=%s%", total_miners, active_miners, capacity_availability_pct
        )
        return {
            "total_miners": total_miners,
            "active_miners": active_miners,
            "capacity_availability_pct": capacity_availability_pct,
        }

    async def collect_all_miner_metrics(self) -> dict[str, Any]:
        """Collect all SLA metrics for all miners.

        Uses batched queries (O(1) round trips) instead of per-miner loops:
        1. Fetch all miner statuses in one query.
        2. Fetch recent match results for all miners in one query.
        3. Fetch recent feedback for all miners in one query.
        Then aggregate in Python.
        """
        miners = self.db.execute(select(Miner)).scalars().all()
        miner_ids = [m.miner_id for m in miners]
        results: dict[str, Any] = {"miners_processed": 0, "metrics_collected": [], "violations_detected": 0}
        if not miner_ids:
            results["capacity"] = await self.collect_capacity_availability()
            results["violations_detected"] = 0
            return results

        now = datetime.now(UTC)
        week_ago = now - timedelta(days=7)

        # Batch 1: all miner statuses (for uptime)
        status_map: dict[str, MinerStatus] = {
            ms.miner_id: ms
            for ms in (await self.db.execute(select(MinerStatus).where(MinerStatus.miner_id.in_(miner_ids)))).scalars().all()  # type: ignore[misc]
        }

        # Batch 2: recent match results for all miners (for response time)
        match_results = (
            (
                await self.db.execute(
                    select(MatchResult)
                    .where(MatchResult.miner_id.in_(miner_ids))
                    .where(MatchResult.created_at >= week_ago)
                    .order_by(desc(MatchResult.created_at))
                )
            )
            .scalars()
            .all()  # type: ignore[misc]
        )
        # Group by miner_id, keep latest 100 per miner
        match_by_miner: dict[str, list[MatchResult]] = {}
        for mr in match_results:
            match_by_miner.setdefault(mr.miner_id, []).append(mr)
        for mid in list(match_by_miner):
            match_by_miner[mid] = match_by_miner[mid][:100]

        # Batch 3: recent feedback for all miners (for completion rate)
        feedback_records = (
            (
                await self.db.execute(
                    select(Feedback)
                    .where(Feedback.miner_id.in_(miner_ids))
                    .where(Feedback.created_at >= week_ago)
                    .order_by(Feedback.created_at.desc())
                )
            )
            .scalars()
            .all()  # type: ignore[misc]
        )
        feedback_by_miner: dict[str, list[Feedback]] = {}
        for fb in feedback_records:
            feedback_by_miner.setdefault(fb.miner_id, []).append(fb)
        for mid in list(feedback_by_miner):
            feedback_by_miner[mid] = feedback_by_miner[mid][:100]

        # Aggregate in Python (no further DB round trips)
        for miner_id in miner_ids:
            try:
                # Uptime from status
                uptime = self._compute_uptime_from_status(status_map.get(miner_id))
                ms = status_map.get(miner_id)
                if ms:
                    ms.uptime_pct = uptime

                # Response time from match results
                mrs = match_by_miner.get(miner_id, [])
                response_times = [r.eta_ms for r in mrs if r.eta_ms is not None]
                response_time: float | None = sum(response_times) / len(response_times) if response_times else None

                # Completion rate from feedback
                fbs = feedback_by_miner.get(miner_id, [])
                completion_rate: float | None = None
                if fbs:
                    successful = sum(1 for f in fbs if f.outcome == "success")
                    completion_rate = successful / len(fbs) * 100.0

                results["metrics_collected"].append(
                    {
                        "miner_id": miner_id,
                        "uptime_pct": uptime,
                        "response_time_ms": response_time,
                        "completion_rate_pct": completion_rate,
                    }
                )
                results["miners_processed"] += 1
            except Exception as e:
                logger.error("Failed to collect metrics for miner %s: %s", miner_id, e)

        # Commit uptime updates in one transaction
        await self.db.commit()  # type: ignore[misc, func-returns-value]

        capacity = await self.collect_capacity_availability()
        results["capacity"] = capacity
        violation_stmt = (
            select(func.count(SLAViolation.id))
            .where(SLAViolation.resolved_at.is_(None))
            .where(SLAViolation.created_at >= datetime.now(UTC) - timedelta(hours=1))
        )
        results["violations_detected"] = self.db.execute(violation_stmt).scalar() or 0
        logger.info(
            "SLA collection complete: processed=%s, violations=%s", results["miners_processed"], results["violations_detected"]
        )
        return results

    @staticmethod
    def _compute_uptime_from_status(status: MinerStatus | None) -> float:
        """Compute uptime percentage from a MinerStatus record (no DB access)."""
        if not status:
            return 0.0
        if status.last_heartbeat_at:
            time_since_heartbeat = (datetime.now(UTC) - status.last_heartbeat_at).total_seconds()
            if time_since_heartbeat > 300:
                return 0.0
            uptime_pct = 100.0 - time_since_heartbeat / 300.0 * 100.0
            return max(0.0, min(100.0, uptime_pct))
        return 0.0

    async def get_sla_metrics(self, miner_id: str | None = None, hours: int = 24) -> list[SLAMetric]:
        """Get SLA metrics for a miner or all miners"""
        cutoff = datetime.now(UTC) - timedelta(hours=hours)
        stmt = select(SLAMetric).where(SLAMetric.timestamp >= cutoff)
        if miner_id:
            stmt = stmt.where(SLAMetric.miner_id == miner_id)
        stmt = stmt.order_by(desc(SLAMetric.timestamp))
        return (await self.db.execute(stmt)).scalars().all()  # type: ignore[misc, no-any-return]

    async def get_sla_violations(self, miner_id: str | None = None, resolved: bool = False) -> list[SLAViolation]:
        """Get SLA violations for a miner or all miners"""
        stmt = select(SLAViolation)
        if miner_id:
            stmt = stmt.where(SLAViolation.miner_id == miner_id)
        if resolved:
            stmt = stmt.where(SLAViolation.resolved_at.isnot_(None))
        else:
            stmt = stmt.where(SLAViolation.resolved_at.is_(None))
        stmt = stmt.order_by(desc(SLAViolation.created_at))
        return (await self.db.execute(stmt)).scalars().all()  # type: ignore[misc, no-any-return]

    def _check_violation(self, metric_type: str, value: float, threshold: float) -> bool:
        """Check if a metric value violates its SLA threshold"""
        if metric_type in ["uptime_pct", "completion_rate_pct", "capacity_availability_pct"]:
            return value < threshold
        elif metric_type in ["response_time_ms"]:
            return value > threshold
        return False

    async def _record_violation(
        self, miner_id: str, metric_type: str, metric_value: float, threshold: float, metadata: dict[str, str] | None = None
    ) -> SLAViolation:
        """Record an SLA violation"""
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
            violation_duration_ms=None,
            created_at=datetime.now(UTC),
            meta_data=metadata or {},
        )
        self.db.add(violation)
        await self.db.commit()  # type: ignore[misc, func-returns-value]
        logger.warning(
            "SLA violation recorded: miner=%s, type=%s, severity=%s, value=%s, threshold=%s",
            miner_id,
            metric_type,
            severity,
            metric_value,
            threshold,
        )
        return violation


class SLACollectorScheduler:
    """Scheduler for automated SLA metric collection"""

    def __init__(self, sla_collector: SLACollector):
        self.sla_collector = sla_collector
        self.logger = get_logger(__name__)
        self.running = False

    async def start(self, collection_interval_seconds: int = 300) -> None:
        """Start the SLA collection scheduler"""
        if self.running:
            return
        self.running = True
        self.logger.info("SLA Collector scheduler started")
        create_task_with_logging(self._collection_loop(collection_interval_seconds), name="sla_collection_loop")

    async def stop(self) -> None:
        """Stop the SLA collection scheduler"""
        self.running = False
        self.logger.info("SLA Collector scheduler stopped")

    async def _collection_loop(self, interval_seconds: int) -> None:
        """Background task that collects SLA metrics periodically"""
        while self.running:
            try:
                await self.sla_collector.collect_all_miner_metrics()
                await asyncio.sleep(interval_seconds)
            except Exception as e:
                self.logger.error("Error in SLA collection loop: %s", e)
                await asyncio.sleep(60)
