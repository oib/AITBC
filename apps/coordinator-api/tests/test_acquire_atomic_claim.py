"""Regression test for the atomic job claim in ``JobService.acquire_next_job`` (#1597).

Two miners polling concurrently both SELECT the same QUEUED row and pass every
dispatch gate; only the conditional ``UPDATE ... WHERE state='QUEUED'`` may
win. This pins the losing path: a session holding a stale QUEUED copy must not
overwrite ``assigned_miner_id`` after another session already claimed the job.
"""

from __future__ import annotations

import pytest
from sqlmodel import Session

from coordinator_api.contexts.infrastructure.domain import Job, Miner
from coordinator_api.contexts.infrastructure.services.jobs import JobService
from coordinator_api.schemas import JobCreate


def _miner(miner_id: str) -> Miner:
    return Miner(
        id=miner_id,
        concurrency=4,
        inflight=0,
        status="ONLINE",
        extra_metadata={},
        capabilities={},
    )


@pytest.fixture
def job_service(db_session):
    return JobService(db_session)


def test_losing_claim_does_not_overwrite_assignee(db_session, db_engine, job_service):
    miner1 = _miner("miner-claim-1")
    db_session.add(miner1)
    db_session.commit()

    job = job_service.create_job(
        client_id="client1",
        req=JobCreate(payload={"type": "inference", "prompt": "x"}, ttl_seconds=900),
    )

    # A second session/miner claims the job first and commits.
    with Session(db_engine) as other_session:
        miner2 = _miner("miner-claim-2")
        other_session.add(miner2)
        other_session.commit()
        other_service = JobService(other_session)
        won = other_service.acquire_next_job(miner2)
        assert won is not None
        assert won.assigned_miner_id == "miner-claim-2"

    # db_session's identity map still holds the pre-claim QUEUED copy — exactly
    # the stale-read a concurrent poll produces. Its acquire must lose cleanly:
    # the conditional UPDATE matches zero rows and no job is returned.
    assert db_session.get(Job, job.id).state == "QUEUED"
    lost = job_service.acquire_next_job(miner1)
    assert lost is None

    # The winning assignment is untouched.
    with Session(db_engine) as verify_session:
        fresh = verify_session.get(Job, job.id)
        assert fresh is not None
        assert fresh.state == "RUNNING"
        assert fresh.assigned_miner_id == "miner-claim-2"
