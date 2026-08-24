"""Tests for the acceptance window between result and release (G3).

A miner's result no longer pays the miner. These pin the pause: the escrow is held,
the customer can accept it early or reject it into a dispute, only an operator can
settle a dispute, and a customer who says nothing loses the hold on expiry rather
than keeping the provider's money locked forever.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from aitbc_shared import JobPayment

from coordinator_api.contexts.infrastructure.domain import Job
from coordinator_api.contexts.infrastructure.services.jobs import JobService
from coordinator_api.contexts.payments import acceptance
from coordinator_api.contexts.payments.acceptance import (
    DISPUTED,
    HELD_STATES,
    PENDING_ACCEPTANCE,
    deadline_from,
    deadline_passed,
    window_seconds_for,
)
from coordinator_api.contexts.payments.services.acceptance_sweeper import AcceptanceSweeper, sweeper_enabled
from coordinator_api.contexts.payments.services.payments import PaymentService
from coordinator_api.schemas import JobCreate


class _KeepOpen:
    """Hand the sweeper the test session without letting it close it."""

    def __init__(self, session):
        self._session = session

    def __enter__(self):
        return self._session

    def __exit__(self, *exc_info):
        return False


@pytest.fixture
def job_service(db_session):
    return JobService(db_session)


def _completed_job(job_service, db_session, *, payment_status="escrowed", constraints=None):
    """A completed, paid-for job with a JobPayment behind it."""
    req = JobCreate(
        payload={"type": "inference", "prompt": "test prompt"},
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
        meta_data={"provider_address": "0x" + "a" * 40},
    )
    db_session.add(payment)
    db_session.commit()
    db_session.refresh(payment)
    job.state = "COMPLETED"
    job.completed_at = datetime.now(UTC)
    job.payment_id = payment.id
    job.payment_status = payment_status
    if constraints is not None:
        job.constraints = constraints
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)
    return job, payment


# ---------------------------------------------------------------------------
# How long the window is
# ---------------------------------------------------------------------------


def test_window_defaults_to_the_operator_setting(monkeypatch):
    monkeypatch.setenv("COORDINATOR_ACCEPTANCE_WINDOW_SECONDS", "600")
    assert window_seconds_for(None) == 600


def test_a_job_may_name_its_own_window(monkeypatch):
    monkeypatch.setenv("COORDINATOR_ACCEPTANCE_WINDOW_SECONDS", "600")
    assert window_seconds_for({"acceptance_window_seconds": 30}) == 30


def test_a_job_cannot_hold_a_payout_past_the_operators_ceiling(monkeypatch):
    monkeypatch.setenv("COORDINATOR_ACCEPTANCE_WINDOW_MAX_SECONDS", "3600")
    assert window_seconds_for({"acceptance_window_seconds": 10_000_000}) == 3600


def test_a_job_may_waive_the_window_entirely(monkeypatch):
    monkeypatch.setenv("COORDINATOR_ACCEPTANCE_WINDOW_SECONDS", "600")
    assert window_seconds_for({"acceptance_window_seconds": 0}) == 0


def test_an_unreadable_window_falls_back_to_the_default(monkeypatch):
    monkeypatch.setenv("COORDINATOR_ACCEPTANCE_WINDOW_SECONDS", "600")
    assert window_seconds_for({"acceptance_window_seconds": "soon"}) == 600


# ---------------------------------------------------------------------------
# When the window is over
# ---------------------------------------------------------------------------


def test_a_future_deadline_has_not_passed():
    meta = acceptance.opened_window({}, 3600)
    assert deadline_passed(meta) is False
    assert deadline_from(meta) > datetime.now(UTC)


def test_a_past_deadline_has_passed():
    meta = acceptance.opened_window({}, 0, now=datetime.now(UTC) - timedelta(seconds=1))
    assert deadline_passed(meta) is True


def test_a_payment_with_no_deadline_is_treated_as_expired():
    """Better to pay the provider that did the work than to strand the escrow."""
    assert deadline_passed(None) is True
    assert deadline_passed({"provider_address": "0x" + "a" * 40}) is True
    assert deadline_passed({acceptance.META_DEADLINE: "not a date"}) is True


def test_opening_a_window_keeps_the_existing_metadata():
    meta = acceptance.opened_window({"offer_id": "gpu-offer-001"}, 60)
    assert meta["offer_id"] == "gpu-offer-001"
    assert acceptance.META_OPENED_AT in meta


# ---------------------------------------------------------------------------
# Holding the escrow
# ---------------------------------------------------------------------------


def test_holding_a_payment_moves_it_out_of_escrowed(db_session, job_service):
    job, payment = _completed_job(job_service, db_session)

    deadline = PaymentService(db_session).open_acceptance_window(job.id, payment.id, 3600)

    assert deadline is not None
    db_session.refresh(payment)
    assert payment.status == PENDING_ACCEPTANCE
    assert deadline_from(payment.meta_data) == deadline
    # The offer terms and payee written at escrow time survive the hold.
    assert payment.meta_data["provider_address"] == "0x" + "a" * 40


def test_only_an_escrowed_payment_can_be_held(db_session, job_service):
    job, payment = _completed_job(job_service, db_session)
    payment.status = "released"
    db_session.add(payment)
    db_session.commit()

    assert PaymentService(db_session).open_acceptance_window(job.id, payment.id, 3600) is None


def test_holding_refuses_a_payment_from_another_job(db_session, job_service):
    _, payment = _completed_job(job_service, db_session)

    assert PaymentService(db_session).open_acceptance_window("some-other-job", payment.id, 3600) is None


# ---------------------------------------------------------------------------
# Rejecting
# ---------------------------------------------------------------------------


def test_rejecting_moves_the_payment_to_disputed_without_refunding(db_session, job_service):
    """The customer's word alone must not move the money back."""
    job, payment = _completed_job(job_service, db_session, payment_status=PENDING_ACCEPTANCE)
    payment.status = PENDING_ACCEPTANCE
    db_session.add(payment)
    db_session.commit()

    assert PaymentService(db_session).dispute_payment("client1", job.id, payment.id, "empty output") is True

    db_session.refresh(payment)
    assert payment.status == DISPUTED
    assert payment.meta_data[acceptance.META_DISPUTE_REASON] == "empty output"
    assert payment.refunded_at is None


def test_a_payment_that_is_not_held_cannot_be_rejected(db_session, job_service):
    job, payment = _completed_job(job_service, db_session)

    assert PaymentService(db_session).dispute_payment("client1", job.id, payment.id, "too late") is False


def test_only_the_buyer_may_reject(db_session, job_service):
    from fastapi import HTTPException

    job, payment = _completed_job(job_service, db_session, payment_status=PENDING_ACCEPTANCE)
    payment.status = PENDING_ACCEPTANCE
    db_session.add(payment)
    db_session.commit()

    with pytest.raises(HTTPException) as exc:
        PaymentService(db_session).dispute_payment("someone-else", job.id, payment.id, "not mine")
    assert exc.value.status_code == 403


# ---------------------------------------------------------------------------
# Settling out of the held states
# ---------------------------------------------------------------------------


def test_held_and_disputed_are_still_settleable():
    """Both describe an escrow that never moved, so release and refund still apply."""
    assert PENDING_ACCEPTANCE in HELD_STATES
    assert DISPUTED in HELD_STATES
    assert "escrowed" in HELD_STATES
    assert "released" not in HELD_STATES
    assert "refunded" not in HELD_STATES


async def test_an_already_released_payment_is_not_released_again(db_session, job_service):
    job, payment = _completed_job(job_service, db_session)
    payment.status = "released"
    db_session.add(payment)
    db_session.commit()

    assert await PaymentService(db_session).release_payment("client1", job.id, payment.id) is False


# ---------------------------------------------------------------------------
# The sweeper
# ---------------------------------------------------------------------------


async def test_an_expired_window_releases_to_the_provider(db_session, job_service, monkeypatch):
    job, payment = _completed_job(job_service, db_session, payment_status=PENDING_ACCEPTANCE)
    payment.status = PENDING_ACCEPTANCE
    payment.meta_data = acceptance.opened_window(payment.meta_data, 0, now=datetime.now(UTC) - timedelta(seconds=5))
    db_session.add(payment)
    db_session.commit()

    released: list[tuple[str, str]] = []

    async def fake_release(self, client_id, job_id, payment_id, reason=None):
        released.append((job_id, reason))
        return True

    monkeypatch.setattr(PaymentService, "release_payment", fake_release)
    counts = await AcceptanceSweeper(session_factory=lambda: _KeepOpen(db_session)).run_once()

    assert counts["expired"] == 1
    assert counts["released"] == 1
    assert released == [(job.id, "Acceptance window expired")]
    assert db_session.get(Job, job.id).payment_status == "released"


async def test_a_live_window_is_left_alone(db_session, job_service, monkeypatch):
    job, payment = _completed_job(job_service, db_session, payment_status=PENDING_ACCEPTANCE)
    payment.status = PENDING_ACCEPTANCE
    payment.meta_data = acceptance.opened_window(payment.meta_data, 3600)
    db_session.add(payment)
    db_session.commit()

    async def fail_release(self, client_id, job_id, payment_id, reason=None):
        raise AssertionError("released a payment whose window is still open")

    monkeypatch.setattr(PaymentService, "release_payment", fail_release)
    counts = await AcceptanceSweeper(session_factory=lambda: _KeepOpen(db_session)).run_once()

    assert counts["held"] == 1
    assert counts["expired"] == 0
    assert db_session.get(Job, job.id).payment_status == PENDING_ACCEPTANCE


async def test_a_dispute_is_never_swept_to_the_provider(db_session, job_service, monkeypatch):
    """A rejection waits for a ruling; a timer must not decide it."""
    job, payment = _completed_job(job_service, db_session, payment_status=PENDING_ACCEPTANCE)
    payment.status = DISPUTED
    payment.meta_data = acceptance.opened_window(payment.meta_data, 0, now=datetime.now(UTC) - timedelta(days=1))
    db_session.add(payment)
    db_session.commit()

    async def fail_release(self, client_id, job_id, payment_id, reason=None):
        raise AssertionError("swept a disputed payment")

    monkeypatch.setattr(PaymentService, "release_payment", fail_release)
    counts = await AcceptanceSweeper(session_factory=lambda: _KeepOpen(db_session)).run_once()

    assert counts["expired"] == 0
    assert db_session.get(Job, job.id).payment_status == PENDING_ACCEPTANCE


async def test_a_release_that_does_not_settle_stays_held_for_the_next_sweep(db_session, job_service, monkeypatch):
    job, payment = _completed_job(job_service, db_session, payment_status=PENDING_ACCEPTANCE)
    payment.status = PENDING_ACCEPTANCE
    payment.meta_data = acceptance.opened_window(payment.meta_data, 0, now=datetime.now(UTC) - timedelta(seconds=5))
    db_session.add(payment)
    db_session.commit()

    async def unsettled(self, client_id, job_id, payment_id, reason=None):
        return False

    monkeypatch.setattr(PaymentService, "release_payment", unsettled)
    counts = await AcceptanceSweeper(session_factory=lambda: _KeepOpen(db_session)).run_once()

    assert counts["failed"] == 1
    assert db_session.get(Job, job.id).payment_status == PENDING_ACCEPTANCE


def test_the_sweeper_stands_down_when_no_window_is_configured(monkeypatch):
    monkeypatch.setenv("COORDINATOR_ACCEPTANCE_WINDOW_SECONDS", "0")
    assert sweeper_enabled() is False

    monkeypatch.setenv("COORDINATOR_ACCEPTANCE_WINDOW_SECONDS", "600")
    assert sweeper_enabled() is True

    monkeypatch.setenv("COORDINATOR_ACCEPTANCE_SWEEP_ENABLED", "false")
    assert sweeper_enabled() is False


# ---------------------------------------------------------------------------
# The rest of the pipeline
# ---------------------------------------------------------------------------


def test_a_held_payment_is_not_dispatchable(db_session, job_service):
    """G4's gate allows only "escrowed"; a held payment must not buy more GPU time."""
    from coordinator_api.contexts.infrastructure.services.jobs import _payment_blocks_dispatch

    job, _ = _completed_job(job_service, db_session, payment_status=PENDING_ACCEPTANCE)
    assert _payment_blocks_dispatch(job) is not None

    job.payment_status = DISPUTED
    assert _payment_blocks_dispatch(job) is not None


def test_the_deadline_is_visible_to_the_customer(db_session, job_service):
    job, payment = _completed_job(job_service, db_session, payment_status=PENDING_ACCEPTANCE)
    deadline = PaymentService(db_session).open_acceptance_window(job.id, payment.id, 3600)

    view = job_service.to_view(db_session.get(Job, job.id))

    assert view.acceptance_deadline == deadline


def test_an_unheld_job_reports_no_deadline(db_session, job_service):
    job, _ = _completed_job(job_service, db_session)

    assert job_service.to_view(job).acceptance_deadline is None
