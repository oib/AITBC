"""#1387: POST /v1/gpu/queue/{job_id}/complete must only allow RUNNING -> COMPLETED.

Before the fix, EdgeGPUService.complete_job set status=COMPLETED unconditionally,
so a QUEUED job could be "completed" without executing and a CANCELLED/COMPLETED
job could be resurrected. Invalid transitions now raise JobStateError and the
endpoint answers 409; a missing job still answers 404.
"""

from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import gpu_service.main as main  # noqa: E402
from gpu_service.domain.gpu_market import GPUJobQueue, GPUJobStatus  # noqa: E402
from gpu_service.main import app  # noqa: E402
from gpu_service.services.edge_gpu_service import EdgeGPUService, JobStateError  # noqa: E402
from gpu_service.storage import get_session  # noqa: E402


def _job_id() -> str:
    return f"jobq_test_{uuid.uuid4().hex[:8]}"


async def _insert_job(job_id: str, status: GPUJobStatus) -> None:
    async with get_session() as session:
        session.add(
            GPUJobQueue(
                id=job_id,
                gpu_id="gpu_test",
                client_id="client_test",
                priority=0,
                status=status,
                payload={"task": "test"},
            )
        )
        await session.commit()


async def _job_status(job_id: str) -> GPUJobStatus | None:
    from sqlalchemy import select

    async with get_session() as session:
        job = (await session.execute(select(GPUJobQueue).where(GPUJobQueue.id == job_id))).scalar_one_or_none()
        return job.status if job else None


@pytest.fixture
def client():
    app.dependency_overrides[main.require_gpu_api_key] = lambda: {"role": "gpu_admin"}
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_complete_queued_job_rejected() -> None:
    """A QUEUED job has not executed — completing it must not be allowed."""
    job_id = _job_id()
    await _insert_job(job_id, GPUJobStatus.QUEUED)
    async with get_session() as session:
        with pytest.raises(JobStateError, match="not running"):
            await EdgeGPUService(session).complete_job(job_id)
    assert await _job_status(job_id) == GPUJobStatus.QUEUED


@pytest.mark.asyncio
async def test_complete_cancelled_job_rejected() -> None:
    """A CANCELLED job is terminal — it must not be resurrected to COMPLETED."""
    job_id = _job_id()
    await _insert_job(job_id, GPUJobStatus.CANCELLED)
    async with get_session() as session:
        with pytest.raises(JobStateError):
            await EdgeGPUService(session).complete_job(job_id)
    assert await _job_status(job_id) == GPUJobStatus.CANCELLED


@pytest.mark.asyncio
async def test_complete_completed_job_rejected() -> None:
    job_id = _job_id()
    await _insert_job(job_id, GPUJobStatus.COMPLETED)
    async with get_session() as session:
        with pytest.raises(JobStateError):
            await EdgeGPUService(session).complete_job(job_id)
    assert await _job_status(job_id) == GPUJobStatus.COMPLETED


@pytest.mark.asyncio
async def test_complete_running_job_succeeds() -> None:
    job_id = _job_id()
    await _insert_job(job_id, GPUJobStatus.RUNNING)
    async with get_session() as session:
        job = await EdgeGPUService(session).complete_job(job_id)
    assert job is not None
    assert job.status == GPUJobStatus.COMPLETED
    assert job.completed_at is not None
    assert await _job_status(job_id) == GPUJobStatus.COMPLETED


@pytest.mark.asyncio
async def test_complete_missing_job_returns_none() -> None:
    async with get_session() as session:
        assert await EdgeGPUService(session).complete_job(_job_id()) is None


def test_endpoint_returns_409_for_non_running_job(client) -> None:
    job_id = _job_id()
    asyncio.run(_insert_job(job_id, GPUJobStatus.QUEUED))
    resp = client.post(f"/v1/gpu/queue/{job_id}/complete")
    assert resp.status_code == 409, resp.text
    assert asyncio.run(_job_status(job_id)) == GPUJobStatus.QUEUED


def test_endpoint_returns_404_for_missing_job(client) -> None:
    resp = client.post(f"/v1/gpu/queue/{_job_id()}/complete")
    assert resp.status_code == 404, resp.text


def test_endpoint_completes_running_job(client) -> None:
    job_id = _job_id()
    asyncio.run(_insert_job(job_id, GPUJobStatus.RUNNING))
    resp = client.post(f"/v1/gpu/queue/{job_id}/complete")
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "completed"
    assert asyncio.run(_job_status(job_id)) == GPUJobStatus.COMPLETED


# --- Mutation-sweep pins (#1387 follow-ups) ---------------------------------
#
# Two mutants survived the original five-plus-three pins:
#
# 1. Dropping `.with_for_update()` from the complete_job SELECT — the row lock
#    is what stops a concurrent cancel/complete from interleaving between the
#    status read and the COMPLETED write. sqlite renders FOR UPDATE as a
#    no-op, so the lock is only visible when the statement is compiled for a
#    locking dialect (postgres).
# 2. Widening the endpoint's `except JobStateError` to `except Exception` —
#    a DB failure would then be reported to the caller as a 409 state
#    conflict instead of a 500.


class _SpySession:
    """AsyncSession proxy that records the statements execute() receives."""

    def __init__(self, session: object) -> None:
        self._session = session
        self.statements: list[object] = []

    async def execute(self, stmt: object, *args: object, **kwargs: object) -> object:
        self.statements.append(stmt)
        return await self._session.execute(stmt, *args, **kwargs)  # type: ignore[attr-defined]

    def __getattr__(self, name: str) -> object:
        return getattr(self._session, name)


@pytest.mark.asyncio
async def test_complete_job_select_locks_the_row() -> None:
    from sqlalchemy.dialects import postgresql

    job_id = _job_id()
    await _insert_job(job_id, GPUJobStatus.RUNNING)
    async with get_session() as session:
        spy = _SpySession(session)
        await EdgeGPUService(spy).complete_job(job_id)  # type: ignore[arg-type]
    assert spy.statements, "complete_job issued no SELECT"
    sql = str(spy.statements[0].compile(dialect=postgresql.dialect()))
    assert "FOR UPDATE" in sql


def test_endpoint_does_not_swallow_unexpected_errors(client, monkeypatch) -> None:
    """A non-JobStateError from complete_job must surface as a 500, not a 409."""

    class _ExplodingService:
        async def complete_job(self, job_id: str) -> None:
            raise RuntimeError("db exploded")

    app.dependency_overrides[main.get_edge_service] = lambda: _ExplodingService()
    try:
        # The app's error-handler middleware turns unhandled exceptions into a
        # 500 response rather than propagating them through TestClient.
        resp = client.post(f"/v1/gpu/queue/{_job_id()}/complete")
        assert resp.status_code == 500
    finally:
        app.dependency_overrides.pop(main.get_edge_service, None)
