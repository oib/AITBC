"""Pins for #1543: SLA read endpoints are bounded.

``SLACollector.get_sla_metrics`` / ``get_sla_violations`` honour ``limit`` —
the routers pass a clamped ``?limit=`` (default 500, max 500).
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from poolhub.models import Base, Miner, SLAMetric, SLAViolation
from poolhub.services.sla_collector import SLACollector


@pytest.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


def _miner(miner_id: str, **overrides) -> Miner:
    kwargs = {
        "miner_id": miner_id,
        "api_key_hash": "h" * 64,
        "addr": "/ip4/127.0.0.1/tcp/9000",
        "proto": "tcp",
        "gpu_vram_gb": 24.0,
        "cpu_cores": 16,
        "ram_gb": 64.0,
        "max_parallel": 4,
        "base_price": Decimal("0.01"),
    }
    kwargs.update(overrides)
    return Miner(**kwargs)


class TestSLALimit:
    @pytest.mark.asyncio
    async def test_get_sla_metrics_limit(self, db_session):
        async with db_session() as s:
            s.add(_miner("m-1"))
            await s.flush()
            now = dt.datetime.now(dt.UTC)
            for i in range(5):
                s.add(
                    SLAMetric(
                        miner_id="m-1",
                        metric_type="uptime_pct",
                        metric_value=99.0,
                        threshold=95.0,
                        timestamp=now - dt.timedelta(minutes=i),
                    )
                )
            await s.commit()
            collector = SLACollector(s)
            metrics = await collector.get_sla_metrics(miner_id="m-1", hours=24, limit=2)
            assert len(metrics) == 2
            # most recent first
            assert metrics[0].timestamp >= metrics[1].timestamp

    @pytest.mark.asyncio
    async def test_get_sla_violations_limit(self, db_session):
        async with db_session() as s:
            s.add(_miner("m-1"))
            await s.flush()
            now = dt.datetime.now(dt.UTC)
            for i in range(4):
                s.add(
                    SLAViolation(
                        miner_id="m-1",
                        violation_type="uptime_pct",
                        severity="high",
                        metric_value=80.0,
                        threshold=95.0,
                        created_at=now - dt.timedelta(minutes=i),
                        resolved_at=now - dt.timedelta(minutes=i) + dt.timedelta(seconds=30),
                    )
                )
            await s.commit()
            collector = SLACollector(s)
            violations = await collector.get_sla_violations(resolved=True, limit=3)
            assert len(violations) == 3
