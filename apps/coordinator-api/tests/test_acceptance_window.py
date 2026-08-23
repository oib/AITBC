"""Tests for the customer acceptance / dispute window (G3).

A miner result must not immediately release the escrow. Instead the payment is held
for a configurable window during which the customer may accept, reject (dispute), or
say nothing. Saying nothing causes a sweeper to release after the deadline.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from aitbc_shared import JobPayment

from coordinator_api.contexts.infrastructure.domain import Job
from coordinator_api.contexts.infrastructure.services.jobs import JobService
from coordinator_api.contexts.payments.acceptance import (
    DISPUTED,
    PENDING_ACCEPTANCE,
    deadline_passed,
    default_window_seconds,
    opened_window,
    window_seconds_for,
)
from coordinator_api.contexts.payments.services.acceptance_sweeper import AcceptanceSweeper
from coordinator_api.contexts.payments.services.payments import PaymentService
from coordinator_api.custom_types import Constraints
from coordinator_api.schemas import JobCreate


@pytest.fixture
def job_service(db_session):
    return JobService(db_session)


@pytest.fixture
def payment_service(db_session):
    return PaymentService(db_session)


def _escrowed_job(job_service, db_session, *, window: int | None = None):
    constraints = Constraints(acceptance_window_seconds=window) if window is not None else Constraints()
    req = JobCreate(
        payload={"type": "inference", "prompt": "test"},
        constraints=constraints,
        ttl_seconds=900,
        payment_amount=Decimal("5"),
        payment_currency="AITBC",
    )
    job = job_service.create_job(client_id="client1", req=req)
    payment = JobPayment(
        job_id=job.id,
        amount=Decimal("5"),
        currency="AITBC",
        payment_method="aitbc_token",
        status="escrowed",
        meta_data={"provider_address": "0x1111111111111111111111111111111111111111"},
    )
    db_session.add(payment)
    db_session.commit()
    db_session.refresh(payment)
    job.payment_id = payment.id
    job.payment_status = "escrowed"
    job.state = "COMPLETED"
    job.completed_at = datetime.now(UTC)
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)
    return job, payment


def test_default_window_can_be_overridden_by_constraints():
    # Operator default is 3600s unless env says otherwise.
    assert default_window_seconds() > 0
    # A job may ask for a shorter window.
    assert window_seconds_for({"acceptance_window_seconds": 60}) == 60
    # Non-numeric values are ignored and fall back to the default.
    assert window_seconds_for({"acceptance_window_seconds": "not a number"}) == default_window_seconds()


def test_opened_window_records_deadline():
    now = datetime(2026, 8, 23, 12, 0, 0, tzinfo=UTC)
    meta = opened_window(None, 300, now=now)
    deadline = deadline_passed(meta, now=now + timedelta(seconds=299))
    assert not deadline
    assert deadline_passed(meta, now=now + timedelta(seconds=300))


def test_open_acceptance_window_holds_payment(db_session, job_service, payment_service):
    job, payment = _escrowed_job(job_service, db_session, window=600)
    deadline = payment_service.open_acceptance_window(job.id, payment.id, 600)
    assert deadline is not None
    db_session.refresh(payment)
    assert payment.status == PENDING_ACCEPTANCE
    assert deadline_passed(payment.meta_data, now=deadline + timedelta(seconds=1))


def test_dispute_payment_marks_disputed(db_session, job_service, payment_service):
    job, payment = _escrowed_job(job_service, db_session, window=600)
    assert payment_service.open_acceptance_window(job.id, payment.id, 600)
    assert payment_service.dispute_payment(job.client_id, job.id, payment.id, "result was wrong")
    db_session.refresh(payment)
    assert payment.status == DISPUTED


def test_sweeper_releases_after_window(db_session, job_service, payment_service):
    job, payment = _escrowed_job(job_service, db_session, window=0)
    assert payment_service.open_acceptance_window(job.id, payment.id, 0)
    job.payment_status = PENDING_ACCEPTANCE
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)

    sweeper = AcceptanceSweeper(
        interval_seconds=1,
        batch_size=10,
        session_factory=lambda: db_session,
    )
    with patch.object(PaymentService, "release_payment", new_callable=AsyncMock, return_value=True) as mock_release:
        counts = asyncio.run(sweeper.run_once())
        assert counts["held"] == 1
        assert counts["expired"] == 1
        mock_release.assert_awaited_once()
    job = db_session.get(Job, job.id)
    assert job is not None
    assert job.payment_status == "released"


def test_sweeper_keeps_disputed_payments_held(db_session, job_service, payment_service):
    job, payment = _escrowed_job(job_service, db_session, window=0)
    payment_service.open_acceptance_window(job.id, payment.id, 0)
    payment_service.dispute_payment(job.client_id, job.id, payment.id, "wrong")
    job.payment_status = DISPUTED
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)
    assert job.payment_status == DISPUTED

    sweeper = AcceptanceSweeper(
        interval_seconds=1,
        batch_size=10,
        session_factory=lambda: db_session,
    )
    with patch.object(PaymentService, "release_payment", new_callable=AsyncMock) as mock_release:
        counts = asyncio.run(sweeper.run_once())
        assert counts["held"] == 0
        assert counts["expired"] == 0
        mock_release.assert_not_awaited()
