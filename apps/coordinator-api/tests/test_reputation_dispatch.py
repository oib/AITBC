"""Tests for reputation-aware job dispatch (P1.1 Phase B)."""

from __future__ import annotations

import pytest

from coordinator_api.contexts.infrastructure.domain import Job, Miner
from coordinator_api.contexts.infrastructure.services.jobs import JobService
from coordinator_api.contexts.reputation.domain.reputation import AgentReputation
from coordinator_api.custom_types import Constraints
from coordinator_api.schemas import JobCreate


@pytest.fixture
def job_service(db_session):
    """Return a JobService bound to the in-memory test session."""
    return JobService(db_session)


def _make_miner(session, miner_id: str, reputation: float, *, concurrency: int = 1, inflight: int = 0):
    """Create and persist a miner with a self-reported reputation score."""
    miner = Miner(
        id=miner_id,
        concurrency=concurrency,
        inflight=inflight,
        status="ONLINE",
        extra_metadata={"reputation_score": reputation},
        capabilities={},
    )
    session.add(miner)
    session.commit()
    session.refresh(miner)
    return miner


def _make_job(job_service, *, constraints: Constraints | None = None, payment_amount=None):
    """Create and persist a job through JobService."""
    if constraints is None:
        constraints = Constraints()
    req = JobCreate(
        payload={"type": "inference", "prompt": "test prompt"},
        constraints=constraints,
        ttl_seconds=900,
        payment_amount=payment_amount,
        payment_currency="AITBC",
    )
    return job_service.create_job(client_id="client1", req=req)


def test_min_reputation_blocks_low_reputation_miner(db_session, job_service):
    """A job with min_reputation is not acquired by a miner below the threshold."""
    low = _make_miner(db_session, "miner_low", 0.2)
    high = _make_miner(db_session, "miner_high", 0.9)
    job = _make_job(job_service, constraints=Constraints(min_reputation=0.8))

    # Low-rep miner cannot take a job requiring a high reputation.
    assert job_service.acquire_next_job(low) is None
    refreshed = db_session.get(Job, job.id)
    assert refreshed is not None
    assert refreshed.state == "QUEUED"

    # High-rep miner can take it.
    acquired = job_service.acquire_next_job(high)
    assert acquired is not None
    assert acquired.id == job.id
    assert acquired.assigned_miner_id == high.id


def test_high_reputation_miner_at_capacity_allows_lower_miner(db_session, job_service):
    """A higher-reputation miner that is at capacity is skipped, letting a lower-rep miner in."""
    low = _make_miner(db_session, "miner_low", 0.2)
    high = _make_miner(db_session, "miner_high", 0.9, concurrency=1, inflight=1)
    job = _make_job(job_service, constraints=Constraints(min_reputation=0.1))

    # High-rep miner is full, so low-rep miner gets the job.
    acquired = job_service.acquire_next_job(low)
    assert acquired is not None
    assert acquired.id == job.id
    assert acquired.assigned_miner_id == low.id


def test_unconstrained_job_prefers_highest_reputation(db_session, job_service):
    """Without explicit min_reputation, the highest-reputation available miner wins."""
    low = _make_miner(db_session, "miner_low", 0.2)
    high = _make_miner(db_session, "miner_high", 0.9)
    job = _make_job(job_service)

    # Low-rep miner should defer because a higher-rep miner is online and capable.
    assert job_service.acquire_next_job(low) is None

    # High-rep miner should acquire the job.
    acquired = job_service.acquire_next_job(high)
    assert acquired is not None
    assert acquired.id == job.id
    assert acquired.assigned_miner_id == high.id


def test_reputation_falls_back_to_agent_reputation_table(db_session, job_service):
    """When a miner does not self-report, its reputation is read from AgentReputation."""
    miner_id = "miner_trusted"
    miner = Miner(
        id=miner_id,
        concurrency=1,
        inflight=0,
        status="ONLINE",
        extra_metadata={},
        capabilities={},
        jobs_completed=0,
        jobs_failed=0,
    )
    db_session.add(miner)
    db_session.add(AgentReputation(agent_id=miner_id, trust_score=850))
    db_session.commit()
    db_session.refresh(miner)

    job = _make_job(job_service, constraints=Constraints(min_reputation=0.8))

    acquired = job_service.acquire_next_job(miner)
    assert acquired is not None
    assert acquired.id == job.id
    assert acquired.assigned_miner_id == miner_id
