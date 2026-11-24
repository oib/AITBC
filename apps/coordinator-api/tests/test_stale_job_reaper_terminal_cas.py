"""#1805: stale job reaper terminal writes are compare-and-swap."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlmodel import Session, col, select, update

from coordinator_api.contexts.infrastructure.domain.job import Job
from coordinator_api.contexts.infrastructure.domain.miner import Miner
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


_GPU_PAYLOAD = {"type": "gpu_compute", "task": "general_compute", "duration_seconds": 3600}


def _expired_job(session: Session, job_id: str, **over) -> Job:
    kwargs = {
        "id": job_id,
        "client_id": "client-starve",
        "state": "QUEUED",
        "payload": {},
        "expires_at": (datetime.now(UTC) - timedelta(minutes=5)).replace(tzinfo=None),
    }
    kwargs.update(over)
    job = Job(**kwargs)
    session.add(job)
    session.commit()
    return job


def _window_open_running(session: Session, job_id: str) -> Job:
    """RUNNING gpu_compute job inside its purchased rental window — expired
    by expires_at but protected by _gpu_rental_window_open (#2317)."""
    return _expired_job(
        session,
        job_id,
        state="RUNNING",
        payload=dict(_GPU_PAYLOAD),
        started_at=datetime.now(UTC),
    )


@pytest.mark.unit
def test_ttl_sweep_pages_past_window_open_head(db_engine) -> None:
    """#2811: >batch_size window-open rows at the head must not starve the
    genuinely expired job behind them — the Python eligibility filter runs
    after the SQL LIMIT, so the find must page until a short page."""
    with Session(db_engine) as session:
        _window_open_running(session, "starve-w1")
        _window_open_running(session, "starve-w2")
        # RUNNING + non-gpu payload: expired by TTL but past the
        # _gpu_rental_window_open filter. RUNNING (not QUEUED) so the
        # state index does not sort it ahead of the window-open head.
        _expired_job(session, "starve-eligible", state="RUNNING")

    with Session(db_engine) as session:
        reaper = StaleJobReaper(session_factory=lambda: session, batch_size=2)
        counts = reaper.run_once()
        assert counts["ttl_expired"] == 1
        row = session.get(Job, "starve-eligible")
        assert row is not None and row.state == "EXPIRED"


@pytest.mark.unit
def test_miner_dead_sweep_pages_past_window_open_head(db_engine) -> None:
    """#2811: same starvation on the miner-dead leg — window-open RUNNING
    jobs with dead miners fill the batch while an eligible plain RUNNING
    job behind them is never reached."""
    miner_id = "miner-starve"
    with Session(db_engine) as session:
        miner = Miner(
            id=miner_id,
            concurrency=4,
            inflight=3,
            status="OFFLINE",
            last_heartbeat=(datetime.now(UTC) - timedelta(seconds=3600)).replace(tzinfo=None),
            extra_metadata={},
            capabilities={},
        )
        session.add(miner)
        for jid in ("md-w1", "md-w2"):
            _expired_job(
                session,
                jid,
                state="RUNNING",
                payload=dict(_GPU_PAYLOAD),
                started_at=datetime.now(UTC),
                assigned_miner_id=miner_id,
            )
        _expired_job(
            session,
            "md-eligible",
            state="RUNNING",
            expires_at=(datetime.now(UTC) + timedelta(hours=1)).replace(tzinfo=None),
            assigned_miner_id=miner_id,
        )
        session.commit()

    with Session(db_engine) as session:
        reaper = StaleJobReaper(session_factory=lambda: session, batch_size=2, miner_dead_seconds=60)
        counts = reaper.run_once()
        assert counts["miner_dead"] == 1
        row = session.get(Job, "md-eligible")
        assert row is not None and row.state == "EXPIRED"
