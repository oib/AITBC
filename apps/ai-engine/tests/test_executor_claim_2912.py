"""AUDIT-EDGE pins: #2912 — executor claim/terminal-write races.

Before the fix, run_pending_once and schedule_job could both select the
same PENDING row and both run process_job (duplicate JobReceipt rows),
and cancel_job could commit CANCELED while an executor held the snapshot
— process_job then overwrote it to COMPLETED, resurrecting a cancelled
job and minting a receipt. Every transition is now an atomic guarded
UPDATE: claim requires state='pending', terminal write requires
state='running'.
"""

from __future__ import annotations

import asyncio
import os
import sqlite3
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

_DB_DIR = Path(tempfile.mkdtemp(prefix="aitbc_ai_claim_test_"))
os.environ.setdefault("AI_SERVICE_DATABASE_URL", f"sqlite+aiosqlite:///{_DB_DIR / 'ai_claim.db'}")
os.environ["AITBC_AI_CLIENT_KEYS"] = "test-key-a:tenant-a"
os.environ["AITBC_AI_EXECUTE_JOBS"] = "false"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "examples" / "src"))

from sqlalchemy import func, select  # noqa: E402

import aitbc_ai.executor as executor  # noqa: E402
from aitbc_ai.domain.jobs import Job, JobReceipt, JobState  # noqa: E402
from aitbc_ai.storage import engine, get_session  # noqa: E402


@pytest.fixture(autouse=True)
async def _fresh_schema():
    from sqlmodel import SQLModel

    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
        await conn.run_sync(SQLModel.metadata.create_all)
    yield


async def _insert_job(**overrides) -> Job:
    async with get_session() as session:
        job = Job(
            client_id="tenant-a",
            task_type="inference",
            task_data={"prompt": "hi"},
            state=JobState.PENDING,
            created_at=datetime.now(UTC),
            **overrides,
        )
        session.add(job)
        await session.commit()
        await session.refresh(job)
        return job


async def _job_state(job_id: str) -> JobState:
    async with get_session() as session:
        job = (await session.execute(select(Job).where(Job.id == job_id))).scalar_one()
        return job.state


async def _receipt_count(job_id: str) -> int:
    async with get_session() as session:
        return (await session.execute(select(func.count(JobReceipt.id)).where(JobReceipt.job_id == job_id))).scalar_one()


@pytest.mark.asyncio
async def test_concurrent_process_job_mints_single_receipt() -> None:
    """Two workers holding the same PENDING row: exactly one claims it."""
    job = await _insert_job()
    async with get_session() as s1, get_session() as s2:
        # Detached copies — process_job only reads id/task_data/expires_at.
        await asyncio.gather(executor.process_job(s1, job), executor.process_job(s2, job))
    assert await _job_state(job.id) == JobState.COMPLETED
    assert await _receipt_count(job.id) == 1


@pytest.mark.asyncio
async def test_cancel_during_run_is_not_resurrected(monkeypatch: pytest.MonkeyPatch) -> None:
    """cancel_job landing mid-run must survive: the terminal write is
    guarded on state='running', so a CANCELED row is never overwritten
    and no receipt/payment_status is minted."""
    job = await _insert_job()

    def _cancel_then_result(j):
        # _simulate_result is synchronous; cancel_job's commit is modelled
        # with a direct sqlite3 write on the same database file.
        # The jobs.state column stores the enum NAME ('CANCELED').
        with sqlite3.connect(engine.url.database, timeout=10) as conn:
            conn.execute("UPDATE jobs SET state='CANCELED' WHERE id=?", (j.id,))
            conn.commit()
        return {"output": "late result"}, None

    monkeypatch.setattr(executor, "_simulate_result", _cancel_then_result)
    async with get_session() as session:
        await executor.process_job(session, job)
    assert await _job_state(job.id) == JobState.CANCELED
    assert await _receipt_count(job.id) == 0


@pytest.mark.asyncio
async def test_second_process_job_on_terminal_row_is_noop() -> None:
    job = await _insert_job()
    async with get_session() as session:
        await executor.process_job(session, job)
    async with get_session() as session:
        await executor.process_job(session, job)
    assert await _job_state(job.id) == JobState.COMPLETED
    assert await _receipt_count(job.id) == 1


@pytest.mark.asyncio
async def test_expired_pending_job_expires_once() -> None:
    job = await _insert_job(expires_at=datetime.now(UTC) - timedelta(seconds=1))
    async with get_session() as session:
        await executor.process_job(session, job)
    assert await _job_state(job.id) == JobState.EXPIRED
    assert await _receipt_count(job.id) == 0
