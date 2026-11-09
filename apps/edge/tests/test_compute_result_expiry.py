"""#1386: ComputeResult expiry is enforced and datetimes are tz-consistent.

Two defects shared one root area:

1. ``ServeService.get_compute_result`` returned the newest ComputeResult for
   a request_id with no ``expires_at`` check, so the ``cache_ttl`` the worker
   stamps was dead code — stale results were served forever.
2. The schema defaults used naive ``datetime.utcnow`` while the worker writes
   aware ``datetime.now(UTC)`` — persisted rows mixed naive and aware ISO
   strings that mis-order under any future comparison.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlmodel import SQLModel

import aitbc_edge.services.serve_service as svc_mod
from aitbc_edge.schemas.serve import ComputeRequest, ComputeResult
from aitbc_edge.services.serve_service import ServeService


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
    yield engine
    await engine.dispose()


async def _add_result(engine, request_id: str, expires_at: datetime, result_id: str) -> None:
    async with AsyncSession(engine) as session:
        session.add(
            ComputeResult(
                result_id=result_id,
                request_id=request_id,
                island_id="isl-1",
                gpu_id="gpu-1",
                result={"output": {"ok": True}},
                output_data={"ok": True},
                status="completed",
                created_at=datetime.now(UTC) - timedelta(hours=2),
                expires_at=expires_at,
            )
        )
        await session.commit()


@pytest.mark.asyncio
async def test_fresh_result_is_returned(seeded_session):
    await _add_result(seeded_session, "req_fresh", datetime.now(UTC) + timedelta(hours=1), "res_fresh")
    result = await ServeService().get_compute_result("req_fresh")
    assert result is not None
    assert result["result_id"] == "res_fresh"


@pytest.mark.asyncio
async def test_expired_result_is_not_served(seeded_session):
    await _add_result(seeded_session, "req_old", datetime.now(UTC) - timedelta(seconds=1), "res_old")
    assert await ServeService().get_compute_result("req_old") is None


@pytest.mark.asyncio
async def test_boundary_result_just_expired_is_not_served(seeded_session):
    await _add_result(seeded_session, "req_edge", datetime.now(UTC) - timedelta(minutes=1), "res_edge")
    assert await ServeService().get_compute_result("req_edge") is None


@pytest.mark.asyncio
async def test_naive_utc_expires_at_still_enforced(seeded_session):
    """Rows persisted before the aware-datetime fix carry naive UTC values;
    they must compare correctly against the aware 'now' rather than raising
    or mis-ordering."""
    naive_past = (datetime.now(UTC) - timedelta(hours=1)).replace(tzinfo=None)
    naive_future = (datetime.now(UTC) + timedelta(hours=1)).replace(tzinfo=None)
    await _add_result(seeded_session, "req_naive_old", naive_past, "res_naive_old")
    await _add_result(seeded_session, "req_naive_new", naive_future, "res_naive_new")

    assert await ServeService().get_compute_result("req_naive_old") is None
    result = await ServeService().get_compute_result("req_naive_new")
    assert result is not None
    assert result["result_id"] == "res_naive_new"


@pytest.mark.asyncio
async def test_expired_row_does_not_shadow_fresh_result(seeded_session):
    """A stale row for the same request_id must not cause a
    MultipleResultsFound once a fresh result lands."""
    await _add_result(seeded_session, "req_retry", datetime.now(UTC) - timedelta(hours=2), "res_retry_old")
    await _add_result(seeded_session, "req_retry", datetime.now(UTC) + timedelta(hours=1), "res_retry_new")
    result = await ServeService().get_compute_result("req_retry")
    assert result is not None
    assert result["result_id"] == "res_retry_new"


def test_schema_defaults_are_timezone_aware():
    """Sibling models (gpu.py, island.py) already default to
    ``datetime.now(UTC)``; serve.py must match so persisted rows never mix
    naive and aware values."""
    now = datetime.now(UTC)
    instances = [
        ComputeRequest(request_id="r", gpu_id="g", model_name="m"),
        ComputeResult(result_id="res", request_id="r", island_id="i", gpu_id="g"),
    ]
    for instance in instances:
        model = type(instance)
        for field_name in ("created_at", "updated_at", "expires_at"):
            value = getattr(instance, field_name, None)
            if value is not None:
                assert value.tzinfo is not None, f"{model.__name__}.{field_name} is naive"
                assert abs((value - now).total_seconds()) < 60
