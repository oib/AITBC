"""#1384: MetricsService.list_metrics must honour its ``limit`` parameter.

Before the fix the query was built and ordered but never ``.limit()``-ed, so
``GET /v1/metrics?limit=1`` returned every ``edge_metrics`` row — an unbounded
read on a table that grows one row per POST.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlmodel import SQLModel, select

import aitbc_edge.services.metrics_service as svc_mod
from aitbc_edge.schemas.metrics import EdgeMetrics
from aitbc_edge.services.metrics_service import MAX_LIST_LIMIT, MetricsService


@pytest.fixture
async def seeded_session(monkeypatch, tmp_path):
    """In-memory sqlite session factory patched into the service."""
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/edge.db")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    @asynccontextmanager
    async def fake_get_session():
        async with AsyncSession(engine) as session:
            yield session

    monkeypatch.setattr(svc_mod, "get_session", fake_get_session)

    base = datetime(2026, 1, 1, tzinfo=UTC)
    async with AsyncSession(engine) as session:
        for i in range(5):
            session.add(
                EdgeMetrics(
                    metric_id=f"m_{i}",
                    gpu_id="gpu-a" if i % 2 == 0 else "gpu-b",
                    metrics_data={"i": i},
                    created_at=base + timedelta(minutes=i),
                )
            )
        await session.commit()

    yield engine
    await engine.dispose()


@pytest.mark.asyncio
async def test_limit_caps_results(seeded_session):
    metrics = await MetricsService().list_metrics("gpu-a", limit=2)
    # gpu-a has 3 rows (i = 0, 2, 4); newest first.
    assert [m["metric_id"] for m in metrics] == ["m_4", "m_2"]


@pytest.mark.asyncio
async def test_limit_larger_than_table_returns_all(seeded_session):
    metrics = await MetricsService().list_metrics("gpu-a", limit=100)
    assert len(metrics) == 3


@pytest.mark.asyncio
async def test_unfiltered_list_is_also_bounded(seeded_session):
    metrics = await MetricsService().list_metrics(limit=4)
    assert len(metrics) == 4


@pytest.mark.asyncio
async def test_nonpositive_limit_is_clamped_not_unbounded(seeded_session):
    assert len(await MetricsService().list_metrics(limit=0)) == 1
    assert len(await MetricsService().list_metrics(limit=-5)) == 1


@pytest.mark.asyncio
async def test_limit_is_capped_at_max(seeded_session):
    metrics = await MetricsService().list_metrics(limit=MAX_LIST_LIMIT + 500)
    assert len(metrics) == 5


@pytest.mark.asyncio
async def test_default_limit_bounds_large_table(seeded_session):
    """The router default (100) must also bound — a table bigger than the
    default must not be returned whole."""
    engine = seeded_session
    base = datetime(2026, 1, 1, tzinfo=UTC)
    async with AsyncSession(engine) as session:
        for i in range(5, 105):
            session.add(
                EdgeMetrics(
                    metric_id=f"bulk_{i}",
                    gpu_id="gpu-c",
                    metrics_data={"i": i},
                    created_at=base + timedelta(minutes=i),
                )
            )
        await session.commit()

    metrics = await MetricsService().list_metrics("gpu-c")
    assert len(metrics) == 100
    # newest first: bulk_104 .. bulk_005
    assert metrics[0]["metric_id"] == "bulk_104"


@pytest.mark.asyncio
async def test_rows_untouched(seeded_session):
    """list_metrics is a read — it must not mutate the table."""
    await MetricsService().list_metrics(limit=2)
    async with AsyncSession(seeded_session) as session:
        result = await session.execute(select(EdgeMetrics))
        assert len(result.scalars().all()) == 5
