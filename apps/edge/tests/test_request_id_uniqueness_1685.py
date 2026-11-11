"""#1685 EDGE-RESULT-1: request_id collisions must not 500 reads.

``request_id`` was minted as ``req_<8 hex>`` (~4G space) behind a plain
non-unique index, so a birthday-bound collision made
``scalar_one_or_none`` raise ``MultipleResultsFound`` -> HTTP 500 for both
requests sharing the id. The fix: full-uuid4 ids, a unique index on
``compute_requests.request_id``, a bounded regenerate-and-retry on submit,
and newest-wins reads on ``compute_results`` for pre-existing duplicates.
"""

from __future__ import annotations

import re
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlmodel import SQLModel

import aitbc_edge.services.serve_service as svc_mod
from aitbc_edge.schemas.serve import ComputeRequest, ComputeResult
from aitbc_edge.services.serve_service import ServeService


@pytest.fixture
async def engine(tmp_path):
    eng = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/edge.db")
    async with eng.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest.fixture
def patched_sessions(monkeypatch, engine):
    @asynccontextmanager
    async def fake_get_session():
        async with AsyncSession(engine) as session:
            yield session

    monkeypatch.setattr(svc_mod, "get_session", fake_get_session)


async def _seed_request(engine, request_id: str) -> None:
    async with AsyncSession(engine) as session:
        session.add(
            ComputeRequest(
                request_id=request_id,
                gpu_id="gpu-1",
                model_name="m",
                input_data={},
                status="queued",
            )
        )
        await session.commit()


async def _add_result(engine, request_id: str, result_id: str, created_at: datetime) -> None:
    async with AsyncSession(engine) as session:
        session.add(
            ComputeResult(
                result_id=result_id,
                request_id=request_id,
                island_id="isl-1",
                gpu_id="gpu-1",
                output_data={"ok": True},
                status="completed",
                created_at=created_at,
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
        )
        await session.commit()


@pytest.mark.asyncio
async def test_submit_mints_full_entropy_request_id(patched_sessions):
    submitted = await ServeService().submit_compute_request("gpu-1", "m", {})
    assert re.fullmatch(r"req_[0-9a-f]{32}", submitted["request_id"])


@pytest.mark.asyncio
async def test_duplicate_request_id_rejected_by_unique_index(patched_sessions, engine):
    await _seed_request(engine, "req_dup")
    async with AsyncSession(engine) as session:
        session.add(
            ComputeRequest(
                request_id="req_dup",
                gpu_id="gpu-2",
                model_name="m",
                input_data={},
                status="queued",
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()


@pytest.mark.asyncio
async def test_submit_retries_on_request_id_collision(patched_sessions, engine, monkeypatch):
    """A colliding uuid must regenerate, not surface as a 500."""
    collide = UUID("00000000-0000-0000-0000-0000000000aa")
    fresh = UUID("00000000-0000-0000-0000-0000000000bb")
    await _seed_request(engine, f"req_{collide.hex}")

    ids = iter([collide, collide, fresh])
    monkeypatch.setattr(svc_mod, "uuid4", lambda: next(ids))

    submitted = await ServeService().submit_compute_request("gpu-1", "m", {})
    assert submitted["request_id"] == f"req_{fresh.hex}"
    assert submitted["success"] is True


@pytest.mark.asyncio
async def test_submit_gives_up_after_bounded_retries(patched_sessions, engine, monkeypatch):
    collide = UUID("00000000-0000-0000-0000-0000000000cc")
    await _seed_request(engine, f"req_{collide.hex}")
    monkeypatch.setattr(svc_mod, "uuid4", lambda: collide)

    with pytest.raises(IntegrityError):
        await ServeService().submit_compute_request("gpu-1", "m", {})


@pytest.mark.asyncio
async def test_get_compute_result_returns_newest_when_duplicates_exist(patched_sessions, engine):
    """Pre-#1685 databases can hold multiple fresh results per request_id;
    the read must return the newest instead of raising MultipleResultsFound."""
    now = datetime.now(UTC)
    await _add_result(engine, "req_multi", "res_old", now - timedelta(minutes=5))
    await _add_result(engine, "req_multi", "res_new", now)

    result = await ServeService().get_compute_result("req_multi")
    assert result is not None
    assert result["result_id"] == "res_new"
