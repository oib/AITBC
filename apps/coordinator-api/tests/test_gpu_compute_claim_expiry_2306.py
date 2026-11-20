"""#2306: claiming a gpu_compute job extends expires_at over the rental window.

A gpu rental's ``expires_at`` is a queue deadline measured from request
time — escrow seal-wait and dispatch delay eat into it, so a job that goes
RUNNING late hit ``expires_at`` mid-rental and the stale-job reaper
refunded the buyer while the provider worked unpaid (S78 job
``f6443526…``: 1h rental, expires_at=request+3960s, sweeper expired it
~90s before rental end).

The claim CAS now pushes ``expires_at`` out to ``claim_time +
duration + COORDINATOR_GPU_JOB_CLAIM_SLACK_SECONDS`` for ``gpu_compute``
payloads. QUEUED expiry is unchanged — a stale rental still must not
dispatch — and the extension never shortens an already-later expiry.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlmodel import update

from coordinator_api.contexts.infrastructure.domain import Job, Miner
from coordinator_api.contexts.infrastructure.services.jobs import (
    _GPU_COMPUTE_CLAIM_SLACK_SECONDS,
    JobService,
)
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


def _gpu_job(job_service, **payload_extra):
    payload = {"type": "gpu_compute", "task": "general_compute", "duration_hours": 1.0}
    payload.update(payload_extra)
    return job_service.create_job(
        client_id="client1",
        req=JobCreate(payload=payload, ttl_seconds=900),
    )


def test_gpu_compute_claim_extends_expiry(db_session, job_service):
    miner = _miner("miner-gpu-1")
    db_session.add(miner)
    db_session.commit()

    job = _gpu_job(job_service)
    original_expiry = job.expires_at

    claimed = job_service.acquire_next_job(miner)
    assert claimed is not None
    assert claimed.state == "RUNNING"

    new_expiry = db_session.get(Job, job.id).expires_at
    expected_floor = datetime.now(UTC) + timedelta(seconds=3600 + _GPU_COMPUTE_CLAIM_SLACK_SECONDS - 60)
    assert _aware(new_expiry) >= expected_floor
    assert _aware(new_expiry) > _aware(original_expiry)


def test_non_gpu_job_expiry_unchanged(db_session, job_service):
    miner = _miner("miner-gpu-2")
    db_session.add(miner)
    db_session.commit()

    job = job_service.create_job(
        client_id="client1",
        req=JobCreate(payload={"type": "inference", "prompt": "x"}, ttl_seconds=900),
    )
    original_expiry = job.expires_at

    claimed = job_service.acquire_next_job(miner)
    assert claimed is not None
    assert _aware(db_session.get(Job, job.id).expires_at) == _aware(original_expiry)


def test_extension_never_shortens_later_expiry(db_session, job_service):
    miner = _miner("miner-gpu-3")
    db_session.add(miner)
    db_session.commit()

    # duration_hours=0.1 → extension ≈ now+360+900s, far inside the 900s+ TTL
    # only if ttl were tiny; use a long explicit ttl so existing expiry wins.
    job = _gpu_job(job_service, duration_hours=0.01)
    far_future = datetime.now(UTC) + timedelta(seconds=86400)
    db_session.execute(update(Job).where(Job.id == job.id).values(expires_at=far_future))
    db_session.commit()

    claimed = job_service.acquire_next_job(miner)
    assert claimed is not None
    assert _aware(db_session.get(Job, job.id).expires_at) == _aware(far_future)


def test_gpu_compute_without_duration_not_extended(db_session, job_service):
    miner = _miner("miner-gpu-4")
    db_session.add(miner)
    db_session.commit()

    job = job_service.create_job(
        client_id="client1",
        req=JobCreate(payload={"type": "gpu_compute", "task": "general_compute"}, ttl_seconds=900),
    )
    original_expiry = job.expires_at

    claimed = job_service.acquire_next_job(miner)
    assert claimed is not None
    assert _aware(db_session.get(Job, job.id).expires_at) == _aware(original_expiry)


def _aware(dt):
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
