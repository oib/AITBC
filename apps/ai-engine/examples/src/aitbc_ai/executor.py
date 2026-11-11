"""In-process example job executor (#1651).

The examples ``aitbc_ai`` service is not deployed fleet-wide; this module
demonstrates the submit → run → receipt flow with simulated inference only.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
from datetime import UTC, datetime

from sqlalchemy import select
from sqlmodel import SQLModel

from aitbc.aitbc_logging import get_logger

from .domain.jobs import Job, JobReceipt, JobState
from .storage import AsyncSessionLocal, engine, get_session

logger = get_logger(__name__)


def execute_jobs_enabled() -> bool:
    return os.getenv("AITBC_AI_EXECUTE_JOBS", "true").lower() == "true"


POLL_INTERVAL_SEC = float(os.getenv("AITBC_AI_EXECUTOR_POLL_SEC", "0.25"))
EXAMPLE_MINER_ID = os.getenv("AITBC_AI_EXAMPLE_MINER_ID", "example-miner")
_RECEIPT_SECRET = os.getenv("AITBC_AI_RECEIPT_SECRET", "example-receipt-secret")

_TERMINAL_STATES = {JobState.COMPLETED, JobState.FAILED, JobState.CANCELED, JobState.EXPIRED}


def receipt_signature(job_id: str, miner_id: str, result: dict) -> str:
    payload = f"{job_id}:{miner_id}:{json.dumps(result, sort_keys=True, separators=(',', ':'))}"
    return hmac.new(_RECEIPT_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()


def _job_expired(job: Job, now: datetime) -> bool:
    if job.expires_at is None:
        return False
    expires_at = job.expires_at if job.expires_at.tzinfo else job.expires_at.replace(tzinfo=UTC)
    return now >= expires_at


def _simulate_result(job: Job) -> tuple[dict | None, str | None]:
    if job.task_data.get("fail"):
        return None, str(job.task_data.get("error", "simulated failure"))
    prompt = job.task_data.get("prompt", "")
    return {
        "output": prompt,
        "task_type": job.task_type,
        "simulated": True,
        "notice": "Example executor: simulated inference only.",
    }, None


async def process_job(session, job: Job) -> None:
    """Transition one claimable job through RUNNING → terminal."""
    now = datetime.now(UTC)
    if _job_expired(job, now):
        job.state = JobState.EXPIRED
        job.completed_at = now
        await session.commit()
        return

    job.state = JobState.RUNNING
    job.started_at = now
    job.assigned_miner_id = EXAMPLE_MINER_ID
    await session.commit()

    result, error = _simulate_result(job)
    finished = datetime.now(UTC)
    if error:
        job.state = JobState.FAILED
        job.error = error
        job.result = None
    else:
        job.state = JobState.COMPLETED
        job.result = result
        job.error = None
        metrics = {"duration_ms": max(0, int((finished - now).total_seconds() * 1000))}
        signature = receipt_signature(job.id, EXAMPLE_MINER_ID, result or {})
        receipt_row = JobReceipt(
            job_id=job.id,
            miner_id=EXAMPLE_MINER_ID,
            result=result or {},
            metrics=metrics,
            signature=signature,
        )
        session.add(receipt_row)
        job.receipt_id = receipt_row.id
        job.receipt = {
            "id": receipt_row.id,
            "miner_id": EXAMPLE_MINER_ID,
            "signature": signature,
            "simulated": True,
        }
    job.completed_at = finished
    job.payment_status = "simulated"
    await session.commit()


async def run_pending_once() -> int:
    """Process at most one pending job; returns 1 if work was done."""
    async with get_session() as session:
        stmt = select(Job).where(Job.state == JobState.PENDING).order_by(Job.priority.desc(), Job.created_at.asc()).limit(1)
        result = await session.execute(stmt)
        job = result.scalar_one_or_none()
        if not job:
            return 0
        await process_job(session, job)
        return 1


async def run_executor_loop(stop: asyncio.Event) -> None:
    """Background poll for pending jobs."""
    while not stop.is_set():
        try:
            processed = await run_pending_once()
            if processed == 0:
                await asyncio.wait([stop.wait()], timeout=POLL_INTERVAL_SEC)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Example job executor tick failed")
            await asyncio.sleep(POLL_INTERVAL_SEC)


async def ensure_schema() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)


def schedule_job(job_id: str) -> None:
    """Fire-and-forget processing for a single job (used after submit)."""

    async def _one() -> None:
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(Job).where(Job.id == job_id, Job.state == JobState.PENDING))
            job = result.scalar_one_or_none()
            if job:
                await process_job(session, job)

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_one())
    except RuntimeError:
        pass
