"""#1797: payments hold/dispute/release writes are compare-and-swap.

Before the fix, ``open_acceptance_window``, ``dispute_payment`` and the
release/refund outcome writes all did read-check-write: two concurrent
callers could both pass the status check and both commit, leaving mixed
state (e.g. a held payment overwritten back to escrowed, or a released
row clobbered by a stale refund mark). Every transition now goes through
``_cas_payment_transition`` — a conditional ``UPDATE ... WHERE status IN
(...)`` where rowcount is the arbiter, the same pattern as the market CAS
(#1790).

The pins below simulate the losing side of the race deterministically:
the ORM object is left stale in the identity map (``synchronize_session=False``
on the interfering write) while the database has already moved on, so the
public method's early status check passes on stale data and only the CAS
predicate can stop the write.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from aitbc_shared import JobPayment, PaymentEscrow
from sqlmodel import Session, col, select, update

from coordinator_api.contexts.infrastructure.domain.job import Job
from coordinator_api.contexts.payments.acceptance import (
    DISPUTED,
    HELD_STATES,
    PENDING_ACCEPTANCE,
    SETTLEMENT_FAILED,
)
from coordinator_api.contexts.payments.services.payments import PaymentService


def _seed(session: Session, *, status: str = "escrowed", meta: dict | None = None) -> tuple[Job, JobPayment]:
    job = Job(
        id="job-cas-1797",
        client_id="client-1",
        state="COMPLETED",
        payload={},
        payment_id="pay-cas-1797",
        payment_status=status,
    )
    payment = JobPayment(
        id="pay-cas-1797",
        job_id=job.id,
        client_id="client-1",
        amount=Decimal("5"),
        currency="AITBC",
        status=status,
        payment_method="aitbc_token",
        escrow_address="escrow_cas",
        escrowed_at=datetime.now(UTC),
        meta_data=meta,
    )
    escrow = PaymentEscrow(
        payment_id=payment.id,
        amount=Decimal("5"),
        currency="AITBC",
        address="escrow_cas",
        is_active=True,
    )
    session.add(job)
    session.add(payment)
    session.add(escrow)
    session.commit()
    return job, payment


def _status(session: Session, payment_id: str) -> str:
    session.expire_all()
    return session.execute(select(JobPayment.status).where(JobPayment.id == payment_id)).scalar_one()


def _stale_move(session: Session, payment_id: str, new_status: str) -> None:
    """Move the row behind the identity map's back — the cached ORM object
    keeps its old status, exactly like a reader that fetched before a
    concurrent commit."""
    session.execute(
        update(JobPayment)
        .where(col(JobPayment.id) == payment_id)
        .values(status=new_status)
        .execution_options(synchronize_session=False)
    )
    session.commit()


@pytest.mark.unit
def test_cas_transition_second_writer_loses(db_session):
    _, payment = _seed(db_session)
    svc = PaymentService(db_session)
    assert svc._cas_payment_transition(payment.id, {"escrowed"}, {"status": PENDING_ACCEPTANCE})
    # Same from-state can never win twice.
    assert not svc._cas_payment_transition(payment.id, {"escrowed"}, {"status": DISPUTED})
    assert _status(db_session, payment.id) == PENDING_ACCEPTANCE


@pytest.mark.unit
def test_open_acceptance_window_stale_reader_cannot_double_hold(db_session):
    job, payment = _seed(db_session, status="escrowed")
    svc = PaymentService(db_session)
    # Warm the identity map, then move the row behind its back.
    assert db_session.get(JobPayment, payment.id).status == "escrowed"
    _stale_move(db_session, payment.id, DISPUTED)
    # The stale read still says "escrowed"; only the CAS can stop the hold.
    assert svc.open_acceptance_window(job.id, payment.id, 3600) is None
    assert _status(db_session, payment.id) == DISPUTED


@pytest.mark.unit
def test_open_acceptance_window_happy_path_still_holds(db_session):
    job, payment = _seed(db_session, status="escrowed")
    svc = PaymentService(db_session)
    deadline = svc.open_acceptance_window(job.id, payment.id, 3600)
    assert deadline is not None
    assert _status(db_session, payment.id) == PENDING_ACCEPTANCE


@pytest.mark.unit
def test_dispute_payment_stale_reader_cannot_dispute_released(db_session):
    job, payment = _seed(db_session, status=PENDING_ACCEPTANCE)
    svc = PaymentService(db_session)
    assert db_session.get(JobPayment, payment.id).status == PENDING_ACCEPTANCE
    _stale_move(db_session, payment.id, "released")
    assert svc.dispute_payment("client-1", job.id, payment.id, "changed my mind") is False
    assert _status(db_session, payment.id) == "released"


@pytest.mark.unit
def test_dispute_payment_still_works_from_pending_acceptance(db_session):
    job, payment = _seed(db_session, status=PENDING_ACCEPTANCE)
    svc = PaymentService(db_session)
    assert svc.dispute_payment("client-1", job.id, payment.id, "bad result") is True
    assert _status(db_session, payment.id) == DISPUTED


@pytest.mark.unit
def test_record_release_outcome_cannot_write_released_twice(db_session):
    job, payment = _seed(db_session, status="escrowed")
    svc = PaymentService(db_session)
    release_data = {"success": True, "tx_hash": "0xdeadbeef", "released_at": "2026-11-11T00:00:00+00:00"}
    assert svc._record_release_outcome(payment, job, payment.id, job.id, release_data) is True
    assert _status(db_session, payment.id) == "released"
    # A retry (or a second sweeper) presenting the same outcome must lose —
    # the terminal write is not idempotent-repeatable, it is CAS-guarded.
    assert svc._record_release_outcome(payment, job, payment.id, job.id, release_data) is False
    db_session.expire_all()
    row = db_session.get(JobPayment, payment.id)
    assert row.status == "released"
    assert row.transaction_hash == "0xdeadbeef"


@pytest.mark.unit
def test_release_outcome_cannot_clobber_refunded(db_session):
    job, payment = _seed(db_session, status="escrowed")
    svc = PaymentService(db_session)
    assert svc._mark_refunded(payment, job, payment.id, "0xrefund") is True
    assert _status(db_session, payment.id) == "refunded"
    # Late release outcome arrives after the refund already settled.
    release_data = {"success": True, "tx_hash": "0xlate", "released_at": "2026-11-11T00:00:00+00:00"}
    assert svc._record_release_outcome(payment, job, payment.id, job.id, release_data) is False
    assert _status(db_session, payment.id) == "refunded"


@pytest.mark.unit
def test_mark_refunded_cannot_overwrite_released(db_session):
    job, payment = _seed(db_session, status="escrowed")
    svc = PaymentService(db_session)
    release_data = {"success": True, "tx_hash": "0xpaid", "released_at": "2026-11-11T00:00:00+00:00"}
    assert svc._record_release_outcome(payment, job, payment.id, job.id, release_data) is True
    # A refund submit that was in flight loses the CAS — released stands.
    assert svc._mark_refunded(payment, job, payment.id, "0xrefund") is False
    assert _status(db_session, payment.id) == "released"


@pytest.mark.unit
def test_attempts_exhausted_cannot_clobber_terminal_row(db_session):
    job, payment = _seed(db_session, status="released", meta={"release_attempts": 99})
    svc = PaymentService(db_session)
    meta = dict(payment.meta_data or {})
    # Even at the bound, the settlement_failed write must refuse a row that
    # already left the held set — it reports 'stop' without touching status.
    assert svc._release_attempts_exhausted(payment, job.id, payment.id, meta, 99) is True
    assert _status(db_session, payment.id) == "released"


@pytest.mark.unit
def test_attempts_exhausted_still_fails_held_payment(db_session, monkeypatch):
    monkeypatch.setenv("COORDINATOR_RELEASE_MAX_ATTEMPTS", "3")
    job, payment = _seed(db_session, status="escrowed", meta={"release_attempts": 3})
    svc = PaymentService(db_session)
    meta = dict(payment.meta_data or {})
    assert svc._release_attempts_exhausted(payment, job.id, payment.id, meta, 3) is True
    assert _status(db_session, payment.id) == SETTLEMENT_FAILED
    # And once terminal, a second sweep cannot move it again.
    meta2 = dict(db_session.get(JobPayment, payment.id).meta_data or {})
    db_session.expire_all()
    row = db_session.get(JobPayment, payment.id)
    meta2 = dict(row.meta_data or {})
    assert svc._release_attempts_exhausted(row, job.id, payment.id, meta2, 99) is True
    assert _status(db_session, payment.id) == SETTLEMENT_FAILED


@pytest.mark.unit
def test_held_states_unchanged(db_session):
    """Guard rail: the CAS from-set is exactly the documented held set."""
    assert HELD_STATES == frozenset({"escrowed", PENDING_ACCEPTANCE, DISPUTED})
