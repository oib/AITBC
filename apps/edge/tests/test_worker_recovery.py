"""Worker-queue recovery and result-store bounds (#1640, #1641, #1642, #1643).

Covers the ROUND-2 edge residuals:

- ``_requeue_interrupted_requests`` returns requests orphaned in ``running``
  to ``queued`` at worker startup (crash mid-execution used to strand them).
- ``_execute_and_store`` no longer overwrites a ``cancelled`` status that
  landed while the request was executing.
- ``_purge_expired_results`` deletes ComputeResult rows past ``expires_at``.
- ``list_compute_requests`` honours ``limit``.
- ``join_island`` replaces an existing membership row instead of stacking
  duplicates.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlmodel import SQLModel, select

import aitbc_edge.services.compute_worker as worker_mod
import aitbc_edge.services.island_service as island_svc_mod
import aitbc_edge.services.serve_service as serve_svc_mod
from aitbc_edge.schemas.island import IslandMembership
from aitbc_edge.schemas.serve import ComputeRequest, ComputeResult
from aitbc_edge.services.compute_worker import (
    _execute_and_store,
    _purge_expired_results,
    _requeue_interrupted_requests,
)
from aitbc_edge.services.island_service import IslandService
from aitbc_edge.services.serve_service import ServeService


@pytest.fixture
async def engine(tmp_path):
    eng = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/edge.db")
    async with eng.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    yield eng
    await eng.dispose()


def _patch_sessions(monkeypatch, engine, *modules):
    @asynccontextmanager
    async def fake_get_session():
        async with AsyncSession(engine) as session:
            yield session

    for mod in modules:
        monkeypatch.setattr(mod, "get_session", fake_get_session)


async def _add_request(engine, request_id: str, status: str) -> None:
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
                started_at=datetime.now(UTC) if status == "running" else None,
            )
        )
        await session.commit()


async def _get_request(engine, request_id: str) -> ComputeRequest:
    async with AsyncSession(engine) as session:
        return (await session.execute(select(ComputeRequest).where(ComputeRequest.request_id == request_id))).scalar_one()


# ---------------------------------------------------------------------------
# #1640 — orphaned "running" requests are requeued at worker startup
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_requeue_interrupted_requests(monkeypatch, engine):
    _patch_sessions(monkeypatch, engine, worker_mod)
    await _add_request(engine, "req-orphan", "running")
    await _add_request(engine, "req-queued", "queued")
    await _add_request(engine, "req-done", "completed")

    assert await _requeue_interrupted_requests() == 1

    orphan = await _get_request(engine, "req-orphan")
    assert orphan.status == "queued"
    assert orphan.started_at is None
    # Untouched rows keep their status.
    assert (await _get_request(engine, "req-queued")).status == "queued"
    assert (await _get_request(engine, "req-done")).status == "completed"


@pytest.mark.asyncio
async def test_execute_and_store_keeps_cancelled_status(monkeypatch, engine):
    """A cancel landing mid-execution must not be overwritten by the worker."""
    _patch_sessions(monkeypatch, engine, worker_mod, serve_svc_mod)
    await _add_request(engine, "req-cancel", "queued")

    async def _cancel_mid_flight(request):
        # Simulate cancel_compute_request committing from another session
        # while the worker is between the "running" commit and the result write.
        async with AsyncSession(engine) as session:
            row = (
                await session.execute(select(ComputeRequest).where(ComputeRequest.request_id == request.request_id))
            ).scalar_one()
            row.status = "cancelled"
            row.completed_at = datetime.now(UTC)
            await session.commit()
        return {"ok": True}, {"simulated": True}, 0.01, True, None

    monkeypatch.setattr(worker_mod, "_execute_request", _cancel_mid_flight)

    await _execute_and_store("req-cancel")

    row = await _get_request(engine, "req-cancel")
    assert row.status == "cancelled"

    # The result is still recorded — it just doesn't resurrect the request.
    async with AsyncSession(engine) as session:
        results = (
            (await session.execute(select(ComputeResult).where(ComputeResult.request_id == "req-cancel"))).scalars().all()
        )
        assert len(results) == 1
        assert results[0].status == "completed"


# ---------------------------------------------------------------------------
# #1641 — expired ComputeResult rows are purged
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_purge_expired_results(monkeypatch, engine):
    _patch_sessions(monkeypatch, engine, worker_mod)
    now = datetime.now(UTC)
    async with AsyncSession(engine) as session:
        session.add(
            ComputeResult(
                result_id="res-old",
                request_id="req-1",
                island_id="isl",
                gpu_id="gpu-1",
                result={},
                created_at=now - timedelta(hours=2),
                expires_at=now - timedelta(hours=1),
            )
        )
        session.add(
            ComputeResult(
                result_id="res-new",
                request_id="req-2",
                island_id="isl",
                gpu_id="gpu-1",
                result={},
                created_at=now,
                expires_at=now + timedelta(hours=1),
            )
        )
        await session.commit()

    assert await _purge_expired_results() == 1

    async with AsyncSession(engine) as session:
        remaining = (await session.execute(select(ComputeResult))).scalars().all()
        assert [r.result_id for r in remaining] == ["res-new"]


# ---------------------------------------------------------------------------
# #1642 — list_compute_requests honours limit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_compute_requests_bounded(monkeypatch, engine):
    _patch_sessions(monkeypatch, engine, serve_svc_mod)
    svc = ServeService()
    for _i in range(5):
        await svc.submit_compute_request("gpu-1", "m", {}, owner_id=None)

    assert len(await svc.list_compute_requests(limit=3)) == 3
    assert len(await svc.list_compute_requests(limit=0)) == 1  # clamped to >=1
    assert len(await svc.list_compute_requests(limit=10_000)) == 5  # clamped to <=1000


# ---------------------------------------------------------------------------
# #1643 — re-join replaces the membership row
# ---------------------------------------------------------------------------


class _StubRPC:
    def __init__(self, reply: dict[str, Any]):
        self._reply = reply

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def join_island(self, *args, **kwargs):
        return self._reply


@pytest.mark.asyncio
async def test_join_island_replaces_duplicate_membership(monkeypatch, engine):
    _patch_sessions(monkeypatch, engine, island_svc_mod)
    monkeypatch.setattr(
        island_svc_mod,
        "BlockchainRPCClient",
        lambda **kw: _StubRPC({"success": True, "island_id": "isl-1", "status": "joined"}),
    )
    svc = IslandService()

    await svc.join_island("isl-1", "Island One", "chain-a")
    await svc.join_island("isl-1", "Island One Renamed", "chain-b", role="hub")

    async with AsyncSession(engine) as session:
        rows = (await session.execute(select(IslandMembership).where(IslandMembership.island_id == "isl-1"))).scalars().all()
        assert len(rows) == 1
        assert rows[0].island_name == "Island One Renamed"
        assert rows[0].chain_id == "chain-b"
