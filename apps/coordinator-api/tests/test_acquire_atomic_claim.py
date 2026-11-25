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


def test_market_ipfs_escrow_rail_is_not_dispatched_as_miner_work(db_session, job_service):
    """#2970: market-host coordinator rows are escrow rails, not executable jobs."""
    miner = _miner("miner-ipfs-boundary")
    db_session.add(miner)
    db_session.commit()

    rail = job_service.create_job(
        client_id="client1",
        req=JobCreate(
            payload={
                "type": "ipfs",
                "source": "market_host",
                "market_job_id": "sw_job_ipfs_test",
                "provider_address": "0x" + "22" * 20,
            },
            ttl_seconds=900,
        ),
    )
    real = job_service.create_job(
        client_id="client1",
        req=JobCreate(payload={"type": "inference", "prompt": "x"}, ttl_seconds=900),
    )

    claimed = job_service.acquire_next_job(miner)

    assert claimed is not None
    assert claimed.id == real.id
    db_session.expire_all()
    rail_fresh = db_session.get(Job, rail.id)
    assert rail_fresh is not None
    assert rail_fresh.state == "QUEUED"
    assert rail_fresh.assigned_miner_id is None


def test_market_ipfs_escrow_rail_does_not_fill_dispatch_scan_window(db_session, job_service, monkeypatch):
    """#2970: rails are excluded before the bounded QUEUED scan, not skipped after it."""
    monkeypatch.setattr(JobService, "_QUEUE_SCAN_LIMIT", 1)
    miner = _miner("miner-ipfs-scan-window")
    db_session.add(miner)
    db_session.commit()

    job_service.create_job(
        client_id="client1",
        req=JobCreate(
            payload={
                "type": "ipfs",
                "source": "market_host",
                "market_job_id": "sw_job_ipfs_scan_window",
            },
            ttl_seconds=900,
        ),
    )
    real = job_service.create_job(
        client_id="client1",
        req=JobCreate(payload={"type": "inference", "prompt": "x"}, ttl_seconds=900),
    )

    claimed = job_service.acquire_next_job(miner)

    assert claimed is not None
    assert claimed.id == real.id


def test_market_ipfs_escrow_rail_does_not_consume_inflight_cap(db_session, job_service, monkeypatch):
    """#2970: escrow rails are not executable inflight work for the client cap."""
    from coordinator_api.contexts.infrastructure.services import jobs as jobs_module

    monkeypatch.setattr(jobs_module, "_MAX_INFLIGHT_JOBS_PER_CLIENT", 1)

    job_service.create_job(
        client_id="client1",
        req=JobCreate(
            payload={
                "type": "ipfs",
                "source": "market_host",
                "market_job_id": "sw_job_ipfs_inflight_cap",
            },
            ttl_seconds=900,
        ),
        enforce_inflight_cap=True,
    )
    real = job_service.create_job(
        client_id="client1",
        req=JobCreate(payload={"type": "inference", "prompt": "x"}, ttl_seconds=900),
        enforce_inflight_cap=True,
    )

    assert real.state == "QUEUED"
    assert job_service.inflight_count("client1") == 1
