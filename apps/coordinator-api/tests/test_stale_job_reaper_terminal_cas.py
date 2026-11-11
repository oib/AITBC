"""#1805: stale job reaper terminal writes are compare-and-swap."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlmodel import Session, col, select, update

from coordinator_api.contexts.infrastructure.domain.job import Job
from coordinator_api.contexts.infrastructure.services.stale_job_reaper import StaleJobReaper


def _expired_queued(session: Session, job_id: str) -> Job:
    job = Job(
        id=job_id,
        client_id="client-cas",
        state="QUEUED",
        payload={},
        expires_at=(datetime.now(UTC) - timedelta(minutes=5)).replace(tzinfo=None),
    )
    session.add(job)
    session.commit()
    return job


@pytest.mark.unit
def test_reaper_does_not_regress_terminal_job(db_engine) -> None:
    with Session(db_engine) as session:
        job = _expired_queued(session, "reaper-skip-terminal")
        session.execute(
            update(Job).where(col(Job.id) == job.id).values(state="COMPLETED").execution_options(synchronize_session=False)
        )
        session.commit()

    with Session(db_engine) as session:
        reaper = StaleJobReaper(session_factory=lambda: session, batch_size=10)
        before = session.get(Job, "reaper-skip-terminal")
        assert before is not None and before.state == "COMPLETED"
        counts = reaper.run_once()
        assert counts["ttl_expired"] == 0
        after = session.get(Job, "reaper-skip-terminal")
        assert after is not None and after.state == "COMPLETED"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_concurrent_complete_and_expire_exactly_one_wins(db_engine) -> None:
    for _ in range(8):
        with Session(db_engine) as session:
            job_id = _expired_queued(session, f"race-{uuid4().hex[:10]}").id

        async def expire():
            with Session(db_engine) as session:
                reaper = StaleJobReaper(session_factory=lambda: session, batch_size=10)
                reaper.run_once()
                await asyncio.sleep(0)

        async def complete(_job_id: str = job_id):
            await asyncio.sleep(0)
            with Session(db_engine) as session:
                session.execute(
                    update(Job)
                    .where(col(Job.id) == _job_id, col(Job.state).in_({"QUEUED", "RUNNING"}))
                    .values(state="COMPLETED")
                    .execution_options(synchronize_session=False)
                )
                session.commit()

        await asyncio.gather(expire(), complete())
        with Session(db_engine) as session:
            row = session.scalars(select(Job).where(Job.id == job_id)).first()
            assert row is not None
            assert row.state in {"EXPIRED", "COMPLETED"}, (job_id, row.state)
