"""
SLA Metrics Collection Service for Pool-Hub
Collects and tracks SLA metrics for miners including uptime, response time, job completion rate, and capacity availability.
"""

import asyncio
import contextlib
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from aitbc.aitbc_logging import get_logger
from aitbc.async_tasks import create_task_with_logging

from ..models import CapacitySnapshot, Feedback, MatchResult, Miner, MinerStatus, SLAMetric, SLAViolation

logger = get_logger(__name__)


def _as_utc(dt: datetime) -> datetime:
    """Normalize a possibly-naive datetime to aware UTC.

    SQLite drops tzinfo on DateTime(timezone=True) round-trips; Postgres keeps
    it. Treat naive values as already-UTC rather than crashing the loop.
    """
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


# Miners heartbeat every 15s (apps/miner/production_miner.py HEARTBEAT_INTERVAL).
# Uptime stays 100% through a grace window of ~4 missed beats, then decays
# linearly to 0% at DEAD — without the grace, a single late beat (>15s) reads
# as <95% and every healthy miner flaps in and out of violation each cycle.
_HEARTBEAT_GRACE_SECONDS = 60.0
_HEARTBEAT_DEAD_SECONDS = 300.0


def _uptime_from_heartbeat_age(age_seconds: float) -> float:
    if age_seconds <= _HEARTBEAT_GRACE_SECONDS:
        return 100.0
    if age_seconds >= _HEARTBEAT_DEAD_SECONDS:
        return 0.0
    span = _HEARTBEAT_DEAD_SECONDS - _HEARTBEAT_GRACE_SECONDS
    return max(0.0, min(100.0, (_HEARTBEAT_DEAD_SECONDS - age_seconds) / span * 100.0))


class SLACollector:
    """Service for collecting and tracking SLA metrics for miners"""

    # V23-46: annotated AsyncSession, not Session. Every call site passes one
    # (app/routers/sla.py, tests/conftest.py) and every use here is `await`ed --
    # the sync annotation is what forced the `# type: ignore[misc]` on each of them.
    def __init__(self, db: AsyncSession):
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
        await self.db.commit()
        open_stmt = select(SLAViolation).where(
            SLAViolation.miner_id == miner_id,
            SLAViolation.violation_type == metric_type,
            SLAViolation.resolved_at.is_(None),
        )
        open_violation = (await self.db.execute(open_stmt)).scalar_one_or_none()
        if is_violation:
            if open_violation is None:
                await self._record_violation(miner_id, metric_type, metric_value, threshold, metadata)
        elif open_violation is not None:
            open_violation.resolved_at = datetime.now(UTC)
            await self.db.commit()
        logger.info(
            "Recorded SLA metric: miner=%s, type=%s, value=%s, violation=%s", miner_id, metric_type, metric_value, is_violation
        )
        return sla_metric

    async def collect_miner_uptime(self, miner_id: str) -> float:
        """Calculate miner uptime percentage based on heartbeat intervals"""
        stmt = select(MinerStatus).where(MinerStatus.miner_id == miner_id)
        miner_status = (await self.db.execute(stmt)).scalar_one_or_none()
        if not miner_status:
            return 0.0
        if miner_status.last_heartbeat_at:
            age = (datetime.now(UTC) - _as_utc(miner_status.last_heartbeat_at)).total_seconds()
            uptime_pct = _uptime_from_heartbeat_age(age)
        else:
            uptime_pct = 0.0
        miner_status.uptime_pct = uptime_pct
        await self.db.commit()
        await self.record_sla_metric(miner_id, "uptime_pct", uptime_pct, {"method": "heartbeat_based"})
        return uptime_pct

    async def collect_response_time(self, miner_id: str) -> float | None:
        """Calculate average response time for a miner from match results"""
        stmt = select(MatchResult).where(MatchResult.miner_id == miner_id).order_by(desc(MatchResult.created_at)).limit(100)
        results = (await self.db.execute(stmt)).scalars().all()
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
        feedback_records = (await self.db.execute(stmt)).scalars().all()
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
        miner_statuses = (await self.db.execute(stmt)).scalars().all()
        if not miner_statuses:
            return {"total_miners": 0, "active_miners": 0, "capacity_availability_pct": 0.0}
        total_miners = len(miner_statuses)
        active_miners = sum(1 for ms in miner_statuses if not ms.busy)
        capacity_availability_pct = active_miners / total_miners * 100.0
        snapshot = CapacitySnapshot(
            total_miners=total_miners,
            active_miners=active_miners,
            total_parallel_capacity=sum(m.max_parallel for m in (await self.db.execute(select(Miner))).scalars().all()),
            total_queue_length=sum(ms.queue_len for ms in miner_statuses),
            capacity_utilization_pct=100.0 - capacity_availability_pct,
            forecast_capacity=total_miners,
            recommended_scaling="stable",
            scaling_reason="Capacity within normal range",
            timestamp=datetime.now(UTC),
            meta_data={"method": "real_time_collection"},
        )
        self.db.add(snapshot)
        await self.db.commit()
        logger.info(
            "Capacity snapshot: total=%s, active=%s, availability=%.1f%%",
            total_miners,
            active_miners,
            capacity_availability_pct,
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
        miners = (await self.db.execute(select(Miner))).scalars().all()
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
            for ms in (await self.db.execute(select(MinerStatus).where(MinerStatus.miner_id.in_(miner_ids)))).scalars().all()
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
            .all()
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
            .all()
        )
        feedback_by_miner: dict[str, list[Feedback]] = {}
        for fb in feedback_records:
            feedback_by_miner.setdefault(fb.miner_id, []).append(fb)
        for mid in list(feedback_by_miner):
            feedback_by_miner[mid] = feedback_by_miner[mid][:100]

        # Currently-open violations, keyed (miner_id, violation_type): a metric
        # below threshold opens one violation only when none is open, and a
        # recovered metric resolves it. Without this, every collection pass
        # would append a fresh violation row for a persisting breach.
        open_violations: dict[tuple[str, str], SLAViolation] = {
            (v.miner_id, v.violation_type): v
            for v in (await self.db.execute(select(SLAViolation).where(SLAViolation.resolved_at.is_(None)))).scalars().all()
        }
        violations_opened = 0
        violations_resolved = 0

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

                # Persist SLAMetric rows — the batched path used to compute
                # values into `results` without ever writing sla_metrics, so
                # /v1/sla/* stayed empty even with the scheduler enabled.
                for metric_type, value in (
                    ("uptime_pct", uptime),
                    ("response_time_ms", response_time),
                    ("completion_rate_pct", completion_rate),
                ):
                    if value is None:
                        continue
                    threshold = self.sla_thresholds.get(metric_type, 100.0)
                    is_violation = self._check_violation(metric_type, value, threshold)
                    self.db.add(
                        SLAMetric(
                            miner_id=miner_id,
                            metric_type=metric_type,
                            metric_value=value,
                            threshold=threshold,
                            is_violation=is_violation,
                            timestamp=now,
                            meta_data={"method": "collect_all"},
                        )
                    )
                    key = (miner_id, metric_type)
                    if is_violation and key not in open_violations:
                        violation = SLAViolation(
                            miner_id=miner_id,
                            violation_type=metric_type,
                            severity=self._violation_severity(metric_type, value, threshold),
                            metric_value=value,
                            threshold=threshold,
                            created_at=now,
                            meta_data={"method": "collect_all"},
                        )
                        self.db.add(violation)
                        open_violations[key] = violation
                        violations_opened += 1
                    elif not is_violation and key in open_violations:
                        open_violations[key].resolved_at = now
                        violations_resolved += 1

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

        # Single commit for uptime updates, metric rows, and violation changes
        await self.db.commit()

        capacity = await self.collect_capacity_availability()
        results["capacity"] = capacity
        results["violations_detected"] = violations_opened
        results["violations_resolved"] = violations_resolved
        logger.info(
            "SLA collection complete: processed=%s, violations_opened=%s, violations_resolved=%s",
            results["miners_processed"],
            violations_opened,
            violations_resolved,
        )
        return results

    @staticmethod
    def _compute_uptime_from_status(status: MinerStatus | None) -> float:
        """Compute uptime percentage from a MinerStatus record (no DB access)."""
        if not status or not status.last_heartbeat_at:
            return 0.0
        age = (datetime.now(UTC) - _as_utc(status.last_heartbeat_at)).total_seconds()
        return _uptime_from_heartbeat_age(age)

    async def get_sla_metrics(self, miner_id: str | None = None, hours: int = 24) -> list[SLAMetric]:
        """Get SLA metrics for a miner or all miners"""
        cutoff = datetime.now(UTC) - timedelta(hours=hours)
        stmt = select(SLAMetric).where(SLAMetric.timestamp >= cutoff)
        if miner_id:
            stmt = stmt.where(SLAMetric.miner_id == miner_id)
        stmt = stmt.order_by(desc(SLAMetric.timestamp))
        return list((await self.db.execute(stmt)).scalars().all())

    async def get_sla_violations(self, miner_id: str | None = None, resolved: bool = False) -> list[SLAViolation]:
        """Get SLA violations for a miner or all miners"""
        stmt = select(SLAViolation)
        if miner_id:
            stmt = stmt.where(SLAViolation.miner_id == miner_id)
        if resolved:
            # is_not, not isnot_ (V23-97).  SQLAlchemy spells this `is_not` (with the
            # legacy alias `isnot`); `isnot_` is not an operator on any column, so this
            # line raised AttributeError before it could build a statement.
            stmt = stmt.where(SLAViolation.resolved_at.is_not(None))
        else:
            stmt = stmt.where(SLAViolation.resolved_at.is_(None))
        stmt = stmt.order_by(desc(SLAViolation.created_at))
        return list((await self.db.execute(stmt)).scalars().all())

    def _check_violation(self, metric_type: str, value: float, threshold: float) -> bool:
        """Check if a metric value violates its SLA threshold"""
        if metric_type in ["uptime_pct", "completion_rate_pct", "capacity_availability_pct"]:
            return value < threshold
        elif metric_type in ["response_time_ms"]:
            return value > threshold
        return False

    @staticmethod
    def _violation_severity(metric_type: str, metric_value: float, threshold: float) -> str:
        """Severity for a violating metric — shared by the single-metric and
        batched collection paths."""
        if metric_type in ["uptime_pct", "completion_rate_pct"]:
            return "critical" if metric_value < threshold * 0.8 else "high"
        elif metric_type == "response_time_ms":
            return "critical" if metric_value > threshold * 2 else "high"
        return "medium"

    async def _record_violation(
        self, miner_id: str, metric_type: str, metric_value: float, threshold: float, metadata: dict[str, str] | None = None
    ) -> SLAViolation:
        """Record an SLA violation"""
        severity = self._violation_severity(metric_type, metric_value, threshold)
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
        await self.db.commit()
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
    """Scheduler for automated SLA metric collection.

    Takes a session *factory*, not an :class:`SLACollector` (V23-101): a loop that
    runs for the lifetime of the process opens a session per pass rather than
    holding one -- and the pooled connection behind it -- open indefinitely.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self.session_factory = session_factory
        self.logger = get_logger(__name__)
        self.running = False
        self._task: asyncio.Task[Any] | None = None

    async def start(self, collection_interval_seconds: int = 300) -> None:
        """Start the SLA collection scheduler"""
        if self.running:
            return
        self.running = True
        self._task = create_task_with_logging(self._collection_loop(collection_interval_seconds), name="sla_collection_loop")
        self.logger.info("SLA Collector scheduler started (every %ss)", collection_interval_seconds)

    async def stop(self) -> None:
        """Stop the SLA collection scheduler and await the loop's exit.

        Clearing ``running`` alone left the task parked in ``asyncio.sleep`` for
        up to a full interval, so shutdown returned with it still pending.
        """
        self.running = False
        task, self._task = self._task, None
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self.logger.info("SLA Collector scheduler stopped")

    async def _collection_loop(self, interval_seconds: int) -> None:
        """Background task that collects SLA metrics periodically"""
        while self.running:
            try:
                async with self.session_factory() as session:
                    await SLACollector(session).collect_all_miner_metrics()
                await asyncio.sleep(interval_seconds)
            except Exception as e:
                self.logger.error("Error in SLA collection loop: %s", e)
                await asyncio.sleep(60)
