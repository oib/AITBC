"""#1811: edge compute request status markers are compare-and-swap."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlmodel import SQLModel, select

import aitbc_edge.services.compute_worker as worker_mod
from aitbc_edge.schemas.serve import ComputeRequest
from aitbc_edge.services.compute_worker import _mark_request_status


@pytest.fixture
async def engine(tmp_path):
    eng = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/edge.db")
    async with eng.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    yield eng
    await eng.dispose()


def _patch_sessions(monkeypatch, engine):
    @asynccontextmanager
    async def fake_get_session():
        async with AsyncSession(engine) as session:
            yield session

    monkeypatch.setattr(worker_mod, "get_session", fake_get_session)


async def _add(engine, request_id: str, status: str) -> None:
    async with AsyncSession(engine) as session:
        session.add(
            ComputeRequest(
                request_id=request_id,
                gpu_id="gpu-1",
                model_name="m",
                input_data={},
                status=status,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        )
        await session.commit()


async def _get(engine, request_id: str) -> ComputeRequest:
    async with AsyncSession(engine) as session:
        return (await session.execute(select(ComputeRequest).where(ComputeRequest.request_id == request_id))).scalar_one()


@pytest.mark.asyncio
async def test_mark_failed_from_running(monkeypatch, engine) -> None:
    _patch_sessions(monkeypatch, engine)
    await _add(engine, "req-run", "running")

    assert await _mark_request_status("req-run", "failed", error="boom") is True
    row = await _get(engine, "req-run")
    assert row.status == "failed"
    assert row.error == "boom"


@pytest.mark.asyncio
async def test_stale_failed_mark_does_not_regress_completed(monkeypatch, engine) -> None:
    _patch_sessions(monkeypatch, engine)
    await _add(engine, "req-done", "completed")

    assert await _mark_request_status("req-done", "failed", error="stale") is False
    row = await _get(engine, "req-done")
    assert row.status == "completed"
    assert row.error is None


@pytest.mark.asyncio
async def test_stale_failed_mark_does_not_regress_cancelled(monkeypatch, engine) -> None:
    _patch_sessions(monkeypatch, engine)
    await _add(engine, "req-cancel", "cancelled")

    assert await _mark_request_status("req-cancel", "failed", error="stale") is False
    row = await _get(engine, "req-cancel")
    assert row.status == "cancelled"
