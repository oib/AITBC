"""SLA collector persistence and violation-lifecycle tests.

``SLACollector`` runs genuine SQLAlchemy selects in batched queries, so the
``FakeSession`` used by the payout tests cannot exercise it. These tests use a
real async SQLite session instead — the models' ``PGUUID``/``JSON``/``Numeric``
columns all map onto SQLite types.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from unittest.mock import AsyncMock

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from poolhub.models import Base, Feedback, MatchRequest, MatchResult, Miner, MinerStatus, SLAMetric, SLAViolation
from poolhub.repositories.miner_repository import MinerRepository
from poolhub.services.sla_collector import SLACollector, SLACollectorScheduler


@pytest.fixture
async def session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


def _miner(miner_id: str = "miner-1", wallet: str = "0x" + "ab" * 20) -> Miner:
    return Miner(
        miner_id=miner_id,
        api_key_hash="x" * 64,
        addr="/ip4/127.0.0.1/tcp/9000",
        proto="tcp",
        gpu_vram_gb=24.0,
        gpu_name="RTX 4090",
        cpu_cores=16,
        ram_gb=64.0,
        max_parallel=4,
        base_price=Decimal("0.01"),
        wallet_address=wallet,
    )


def _status(miner_id: str, heartbeat_age_s: float) -> MinerStatus:
    return MinerStatus(
        miner_id=miner_id,
        last_heartbeat_at=datetime.now(UTC) - timedelta(seconds=heartbeat_age_s),
    )


async def test_collection_persists_metric_rows(session_factory):
    """A healthy miner gets uptime + response_time + completion_rate rows."""
    async with session_factory() as s:
        s.add(_miner())
        s.add(_status("miner-1", heartbeat_age_s=30))
        req = MatchRequest(job_id="job-1", requirements={})
        s.add(req)
        await s.flush()
        s.add(MatchResult(request_id=req.id, miner_id="miner-1", score=0.9, eta_ms=500))
        s.add(Feedback(job_id="job-1", miner_id="miner-1", outcome="success"))
        await s.commit()

    async with session_factory() as s:
        results = await SLACollector(s).collect_all_miner_metrics()

    assert results["miners_processed"] == 1
    async with session_factory() as s:
        metric_types = {
            row[0] for row in (await s.execute(select(SLAMetric.metric_type).where(SLAMetric.miner_id == "miner-1"))).all()
        }
    assert metric_types == {"uptime_pct", "response_time_ms", "completion_rate_pct"}
    assert results["violations_detected"] == 0


async def test_stale_heartbeat_opens_one_violation(session_factory):
    """Heartbeat older than the 300s window → uptime 0 → a single open violation,
    not a fresh row on every pass."""
    async with session_factory() as s:
        s.add(_miner())
        s.add(_status("miner-1", heartbeat_age_s=600))
        await s.commit()

    async with session_factory() as s:
        first = await SLACollector(s).collect_all_miner_metrics()
    assert first["violations_detected"] == 1

    async with session_factory() as s:
        second = await SLACollector(s).collect_all_miner_metrics()
    assert second["violations_detected"] == 0, "persisting breach must not open a second violation row"

    async with session_factory() as s:
        violations = (await s.execute(select(SLAViolation))).scalars().all()
    assert len(violations) == 1
    assert violations[0].violation_type == "uptime_pct"
    assert violations[0].severity == "critical"  # 0 < 95 * 0.8
    assert violations[0].resolved_at is None


async def test_recovered_heartbeat_resolves_violation(session_factory):
    """An open violation gets resolved_at set once the metric recovers."""
    async with session_factory() as s:
        s.add(_miner())
        s.add(_status("miner-1", heartbeat_age_s=600))
        await s.commit()
    async with session_factory() as s:
        await SLACollector(s).collect_all_miner_metrics()

    # Fresh heartbeat → uptime recovers to ~100%.
    async with session_factory() as s:
        status = (await s.execute(select(MinerStatus))).scalar_one()
        status.last_heartbeat_at = datetime.now(UTC)
        await s.commit()
    async with session_factory() as s:
        results = await SLACollector(s).collect_all_miner_metrics()

    assert results["violations_resolved"] == 1
    async with session_factory() as s:
        open_count = (await s.execute(select(func.count(SLAViolation.id)).where(SLAViolation.resolved_at.is_(None)))).scalar()
    assert open_count == 0


async def test_miner_without_status_records_zero_uptime(session_factory):
    """A registered miner with no heartbeat row still gets an uptime metric (0%)."""
    async with session_factory() as s:
        s.add(_miner("miner-silent"))
        await s.commit()

    async with session_factory() as s:
        await SLACollector(s).collect_all_miner_metrics()

    async with session_factory() as s:
        metrics = (await s.execute(select(SLAMetric))).scalars().all()
    assert [m.metric_type for m in metrics] == ["uptime_pct"]
    assert metrics[0].metric_value == 0.0


async def test_no_miners_collects_capacity_only(session_factory):
    async with session_factory() as s:
        results = await SLACollector(s).collect_all_miner_metrics()

    assert results["miners_processed"] == 0
    assert results["capacity"]["total_miners"] == 0


async def test_scheduler_opens_session_per_pass_and_survives_errors(session_factory, monkeypatch):
    """The scheduler must keep looping when a collection pass raises.

    The error path sleeps 60s, so asyncio.sleep is shrunk for the test —
    otherwise only the first (failing) pass would run before stop().
    """
    calls = 0
    real_sleep = asyncio.sleep

    async def flaky_collect(self):
        nonlocal calls
        calls += 1
        if calls % 2 == 1:
            raise RuntimeError("boom")

    async def fast_sleep(_seconds):
        await real_sleep(0.001)

    monkeypatch.setattr(SLACollector, "collect_all_miner_metrics", flaky_collect)
    monkeypatch.setattr(asyncio, "sleep", fast_sleep)

    scheduler = SLACollectorScheduler(session_factory)
    await scheduler.start(collection_interval_seconds=0)
    await real_sleep(0.05)  # let the loop run several passes
    await scheduler.stop()

    assert calls >= 2, "an exception in one pass must not kill the loop"
    assert scheduler._task is None


async def test_touch_heartbeat_stamps_miner_status(session_factory):
    """Regression: touch_heartbeat must write MinerStatus.last_heartbeat_at --
    the column the SLA collector reads uptime from. It used to update only
    Miner.last_seen_at, leaving every miner at uptime 0 forever."""
    async with session_factory() as s:
        s.add(_miner("miner-hb"))
        s.add(MinerStatus(miner_id="miner-hb"))
        await s.commit()

    async with session_factory() as s:
        repo = MinerRepository(s, AsyncMock())
        await repo.touch_heartbeat("miner-hb")

    async with session_factory() as s:
        status = (await s.execute(select(MinerStatus).where(MinerStatus.miner_id == "miner-hb"))).scalar_one()
        miner = (await s.execute(select(Miner).where(Miner.miner_id == "miner-hb"))).scalar_one()
    assert status.last_heartbeat_at is not None
    assert miner.last_seen_at is not None
    # And the collector now reads the miner as fully up.
    async with session_factory() as s:
        results = await SLACollector(s).collect_all_miner_metrics()
    assert results["violations_detected"] == 0
    assert results["metrics_collected"][0]["uptime_pct"] == 100.0


async def test_touch_heartbeat_creates_missing_status_row(session_factory):
    """A miner registered without a MinerStatus row still gets one on heartbeat."""
    async with session_factory() as s:
        s.add(_miner("miner-new"))
        await s.commit()

    async with session_factory() as s:
        repo = MinerRepository(s, AsyncMock())
        await repo.touch_heartbeat("miner-new")

    async with session_factory() as s:
        status = (await s.execute(select(MinerStatus).where(MinerStatus.miner_id == "miner-new"))).scalar_one()
    assert status.last_heartbeat_at is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
