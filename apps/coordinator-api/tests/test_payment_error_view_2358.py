"""#2358: payment failure reasons must reach the API views.

``ai submit`` used to print "Escrow secured" for a payment whose on-chain
lock never landed — the ``JobPayment`` row was marked ``failed`` with the
reason in ``meta_data.escrow_error``, but neither ``JobPaymentView`` nor
``JobView`` exposed it, so the CLI (and ``ai status``) showed only a bare
``payment_status=failed``. These tests pin the surfacing: the reason is
present exactly when the payment failed, and absent otherwise.
"""

from __future__ import annotations

from decimal import Decimal

from sqlmodel import Session

from aitbc_shared import JobPayment

from coordinator_api.contexts.infrastructure.domain.job import Job
from coordinator_api.contexts.infrastructure.services.jobs import JobService
from coordinator_api.contexts.payments.services.payments import PaymentService


def _job(session: Session, job_id: str) -> Job:
    job = Job(id=job_id, client_id="client-1", state="QUEUED", payload={})
    session.add(job)
    session.commit()
    return job


def _payment(session: Session, job_id: str, *, status: str, meta: dict | None = None) -> JobPayment:
    payment = JobPayment(
        job_id=job_id,
        amount=Decimal("5"),
        currency="AITBC",
        payment_method="aitbc_token",
        status=status,
        meta_data=meta,
    )
    session.add(payment)
    session.commit()
    session.refresh(payment)
    return payment


def test_payment_view_surfaces_escrow_error_on_failed(db_session):
    job = _job(db_session, "job-fail-view")
    payment = _payment(
        db_session,
        job.id,
        status="failed",
        meta={"escrow_error_kind": "unsealed", "escrow_error": "the escrow lock did not seal on-chain"},
    )

    view = PaymentService(db_session).to_view(payment)

    assert view.status == "failed"
    assert view.payment_error == "the escrow lock did not seal on-chain"


def test_payment_view_omits_error_when_not_failed(db_session):
    job = _job(db_session, "job-ok-view")
    payment = _payment(
        db_session,
        job.id,
        status="escrowed",
        meta={"escrow_error": "stale reason from an earlier attempt"},
    )

    view = PaymentService(db_session).to_view(payment)

    assert view.payment_error is None


def test_job_view_surfaces_linked_payment_error(db_session):
    job = _job(db_session, "job-status-view")
    payment = _payment(
        db_session,
        job.id,
        status="failed",
        meta={"escrow_error": "the node refused the escrow (HTTP 422)"},
    )
    job.payment_id = payment.id
    job.payment_status = "failed"
    db_session.add(job)
    db_session.commit()

    view = JobService(db_session).to_view(job)

    assert view.payment_status == "failed"
    assert view.payment_error == "the node refused the escrow (HTTP 422)"


def test_job_view_omits_error_for_healthy_payment(db_session):
    job = _job(db_session, "job-healthy-view")
    payment = _payment(db_session, job.id, status="escrowed", meta={})
    job.payment_id = payment.id
    job.payment_status = "escrowed"
    db_session.add(job)
    db_session.commit()

    view = JobService(db_session).to_view(job)

    assert view.payment_error is None
