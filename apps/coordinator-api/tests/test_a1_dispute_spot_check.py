"""
A-1 Option B: dispute-triggered spot-check re-execution.

When a customer disputes a completed job, the coordinator now automatically
schedules a spot-check re-execution (if the job is eligible) so the dispute
resolver has evidence rather than only the customer's word. This test verifies
the scheduling path and the evidence retrieval.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from sqlmodel import Session

from aitbc_shared import JobPayment

from coordinator_api.contexts.infrastructure.domain.job import Job
from coordinator_api.contexts.payments.services.payments import PaymentService


@pytest.fixture
def payment_session(db_engine) -> Session:
    with Session(db_engine) as session:
        yield session


def _make_disputable_job_and_payment(session: Session, job_id: str = "job-a1", payment_id: str = "pay-a1"):
    """Create a job + payment in PENDING_ACCEPTANCE, ready to dispute."""
    now = datetime.now(UTC)
    job = Job(
        id=job_id,
        client_id="client-a1",
        state="COMPLETED",
        payload={},
        payment_id=payment_id,
        payment_status="pending_acceptance",
        constraints={"deterministic_decoding": True, "decode_seed": 42},
    )
    payment = JobPayment(
        id=payment_id,
        job_id=job_id,
        client_id="client-a1",
        amount=1,
        currency="AITBC",
        status="pending_acceptance",
        escrow_address="0xtest",
        meta_data={"acceptance_deadline": (now + timedelta(hours=1)).isoformat()},
    )
    session.add(job)
    session.add(payment)
    session.commit()
    return job, payment


def test_dispute_schedules_spot_check(payment_session):
    """Disputing a deterministic job schedules a spot-check re-execution."""
    job, payment = _make_disputable_job_and_payment(payment_session)
    service = PaymentService(payment_session)
    with patch.object(service, "_require_owned_job", return_value=job):
        result = service.dispute_payment("client-a1", job.id, payment.id, "wrong output")
    assert result is True
    # The payment should be DISPUTED
    payment_session.refresh(payment)
    assert payment.status == "disputed"
    # A spot-check job should have been created
    from coordinator_api.contexts.infrastructure.domain.job import Job as JobModel
    from sqlmodel import select

    spot_jobs = (
        payment_session.execute(select(JobModel).where(JobModel.constraints["spot_check_for"].as_string() == job.id))
        .scalars()
        .all()
    )
    assert len(spot_jobs) == 1, f"expected 1 spot-check job, got {len(spot_jobs)}"
    assert spot_jobs[0].constraints.get("shadow_mode") is True


def test_dispute_without_deterministic_does_not_schedule(payment_session):
    """A non-deterministic job dispute does not schedule a spot-check."""
    job, payment = _make_disputable_job_and_payment(payment_session)
    job.constraints = {"model": "llama3.2:3b"}  # no deterministic_decoding
    payment_session.add(job)
    payment_session.commit()
    service = PaymentService(payment_session)
    with patch.object(service, "_require_owned_job", return_value=job):
        result = service.dispute_payment("client-a1", job.id, payment.id, "wrong output")
    assert result is True
    payment_session.refresh(payment)
    assert payment.status == "disputed"
    # No spot-check job should exist
    from coordinator_api.contexts.infrastructure.domain.job import Job as JobModel
    from sqlmodel import select

    spot_jobs = (
        payment_session.execute(select(JobModel).where(JobModel.constraints["spot_check_for"].as_string() == job.id))
        .scalars()
        .all()
    )
    assert len(spot_jobs) == 0


def test_get_dispute_evidence_returns_none_without_spot_check(payment_session):
    """get_dispute_evidence returns None when no spot-check has run."""
    job, payment = _make_disputable_job_and_payment(payment_session)
    service = PaymentService(payment_session)
    evidence = service.get_dispute_evidence(job.id)
    assert evidence is None


def test_get_dispute_evidence_returns_result_after_spot_check(payment_session):
    """get_dispute_evidence returns the spot-check result when it exists."""
    job, payment = _make_disputable_job_and_payment(payment_session)
    # Simulate a completed spot-check stored on the job
    job.constraints = {
        "deterministic_decoding": True,
        "spot_check_result": {
            "match": False,
            "original_output_hash": "abc123",
            "spot_output_hash": "def456",
            "spot_check_job_id": "shadow-1",
            "completed_at": "2026-09-07T16:00:00+00:00",
        },
    }
    payment_session.add(job)
    payment_session.commit()
    service = PaymentService(payment_session)
    evidence = service.get_dispute_evidence(job.id)
    assert evidence is not None
    assert evidence["match"] is False
    assert evidence["original_output_hash"] == "abc123"
    assert evidence["spot_output_hash"] == "def456"
