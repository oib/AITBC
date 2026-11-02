"""#826: the poll response hands the miner the job's deadline.

A long-running job type (gpu_compute) holds a worker thread for a duration the buyer
chose; the miner can only stop the hold at the job's deadline if the poll response
carries it. ``AssignedJob.expires_at`` is that deadline as Unix epoch seconds.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta, timezone

import pytest

from coordinator_api.contexts.infrastructure.services.jobs import JobService
from coordinator_api.contexts.infrastructure.services.miners import MinerService
from coordinator_api.schemas import AssignedJob, JobCreate, MinerRegister

TTL = 900


@pytest.fixture
def job_service(db_session):
    return JobService(db_session)


def _job(job_service, ttl: int = TTL):
    req = JobCreate(payload={"type": "gpu_compute", "duration_seconds": 30}, ttl_seconds=ttl)
    return job_service.create_job(client_id="client1", req=req)


def test_assigned_job_carries_the_job_deadline_as_epoch_seconds(job_service):
    before = time.time()
    job = _job(job_service)
    after = time.time()

    assigned = job_service.to_assigned(job)

    assert isinstance(assigned.expires_at, float)
    assert before + TTL - 1 <= assigned.expires_at <= after + TTL + 1


def test_naive_deadline_from_the_database_is_read_as_utc(job_service, db_session):
    job = _job(job_service)
    job.expires_at = datetime(2030, 1, 1, 0, 0, 0)  # SQLite hands datetimes back naive
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)

    assert job_service.to_assigned(job).expires_at == datetime(2030, 1, 1, tzinfo=UTC).timestamp()


def test_aware_deadline_in_another_zone_is_the_same_instant(job_service):
    job = _job(job_service)
    job.expires_at = datetime(2030, 1, 1, 2, 0, 0, tzinfo=timezone(timedelta(hours=2)))

    assert job_service.to_assigned(job).expires_at == datetime(2030, 1, 1, tzinfo=UTC).timestamp()


def test_poll_returns_the_deadline_to_the_miner(db_session, job_service):
    miner = MinerService(db_session).register(
        "m826", MinerRegister(capabilities={}, concurrency=1, region=None, wallet_address=None)
    )
    miner.status = "ONLINE"
    miner.inflight = 0
    db_session.add(miner)
    db_session.commit()
    job = _job(job_service)

    assigned = MinerService(db_session).poll("m826", 0)

    assert assigned is not None and assigned.job_id == job.id
    assert assigned.expires_at is not None and assigned.expires_at > time.time()


def test_deadline_serialises_as_a_json_number():
    assigned = AssignedJob(job_id="j", payload={}, constraints={}, expires_at=1893456000.0)
    assert assigned.model_dump(mode="json")["expires_at"] == 1893456000.0


def test_deadline_is_optional_for_an_older_producer():
    assert AssignedJob(job_id="j", payload={}, constraints={}).expires_at is None
