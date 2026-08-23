"""Tests for the payment gate on job dispatch (G4).

An escrow that never locked must not buy GPU time. These pin the rule that
``JobService.acquire_next_job`` refuses a job whose payment was requested and not
secured, while leaving unpriced work dispatchable.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from coordinator_api.contexts.infrastructure.domain import Job, Miner
from coordinator_api.contexts.infrastructure.services.jobs import JobService
from coordinator_api.schemas import JobCreate


@pytest.fixture
def job_service(db_session):
    """Return a JobService bound to the in-memory test session."""
    return JobService(db_session)


@pytest.fixture
def miner(db_session):
    """Register a single online miner with no capability constraints."""
    miner = Miner(
        id="miner_paid",
        concurrency=1,
        inflight=0,
        status="ONLINE",
        extra_metadata={},
        capabilities={},
    )
    db_session.add(miner)
    db_session.commit()
    db_session.refresh(miner)
    return miner


def _make_job(job_service, db_session, *, payment_amount=None, payment_status=None):
    """Create a job and force it into a given payment state."""
    req = JobCreate(
        payload={"type": "inference", "prompt": "test prompt"},
        ttl_seconds=900,
        payment_amount=payment_amount,
        payment_currency="AITBC",
    )
    job = job_service.create_job(client_id="client1", req=req)
    if payment_status is not None:
        job.payment_status = payment_status
        db_session.add(job)
        db_session.commit()
        db_session.refresh(job)
    return job


def test_skipped_payment_is_not_dispatched(db_session, job_service, miner):
    """An escrow that failed to lock leaves the job queued, not running."""
    job = _make_job(job_service, db_session, payment_amount=Decimal("5"), payment_status="skipped")

    assert job_service.acquire_next_job(miner) is None

    refreshed = db_session.get(Job, job.id)
    assert refreshed is not None
    assert refreshed.state == "QUEUED"
    assert refreshed.assigned_miner_id is None


def test_failed_payment_is_not_dispatched(db_session, job_service, miner):
    """A rejected lock transaction is refused on the same grounds."""
    _make_job(job_service, db_session, payment_amount=Decimal("5"), payment_status="failed")

    assert job_service.acquire_next_job(miner) is None


def test_priced_job_without_a_payment_record_is_not_dispatched(db_session, job_service, miner):
    """A job that asked to be paid for but has no payment at all is refused."""
    _make_job(job_service, db_session, payment_amount=Decimal("5"))

    assert job_service.acquire_next_job(miner) is None


def test_escrowed_payment_is_dispatched(db_session, job_service, miner):
    """Locked funds are the one payment state that permits dispatch."""
    job = _make_job(job_service, db_session, payment_amount=Decimal("5"), payment_status="escrowed")

    acquired = job_service.acquire_next_job(miner)
    assert acquired is not None
    assert acquired.id == job.id
    assert acquired.state == "RUNNING"
    assert acquired.assigned_miner_id == miner.id


def test_unpriced_job_still_dispatches(db_session, job_service, miner):
    """Jobs submitted without a payment_amount are unaffected by the gate."""
    job = _make_job(job_service, db_session)

    acquired = job_service.acquire_next_job(miner)
    assert acquired is not None
    assert acquired.id == job.id
    assert acquired.assigned_miner_id == miner.id


def test_securing_the_escrow_later_unblocks_the_job(db_session, job_service, miner):
    """A client retrying the escrow clears the gate rather than being stuck."""
    job = _make_job(job_service, db_session, payment_amount=Decimal("5"), payment_status="skipped")
    assert job_service.acquire_next_job(miner) is None

    # What PaymentService.create_payment now writes back on a successful retry.
    job.payment_status = "escrowed"
    db_session.add(job)
    db_session.commit()

    acquired = job_service.acquire_next_job(miner)
    assert acquired is not None
    assert acquired.id == job.id


def test_gate_can_be_disabled_for_operators(db_session, job_service, miner, monkeypatch):
    """COORDINATOR_REQUIRE_PAYMENT=false restores the previous behaviour."""
    from coordinator_api.contexts.infrastructure.services import jobs as jobs_module

    monkeypatch.setattr(jobs_module, "_PAYMENT_REQUIRE", False)
    job = _make_job(job_service, db_session, payment_amount=Decimal("5"), payment_status="skipped")

    acquired = job_service.acquire_next_job(miner)
    assert acquired is not None
    assert acquired.id == job.id
