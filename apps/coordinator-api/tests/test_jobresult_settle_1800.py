"""#1800: result resubmission after a failed settlement must be idempotent.

``submit_result`` marks the job COMPLETED before the money moves, and
``release_payment`` requires that terminal state — so a failed settle
leaves COMPLETED + escrowed. Before this fix a resubmit hit the
``state != running`` 409 forever and the escrowed payment was unpayable
except via the (disabled-by-default) SettlementReconciler.

The fix keeps the job COMPLETED — no state flapping, no reaper exposure,
no attempt-budget burn on a state-gate failure — and lets the assigned
miner's resubmit retry *only the money movement*. These pins drive the
real endpoint through the auth/session overrides.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from aitbc_shared import JobPayment, PaymentEscrow
from fastapi.testclient import TestClient
from sqlmodel import Session, func, select

from coordinator_api.contexts.infrastructure.domain.job import Job
from coordinator_api.contexts.infrastructure.domain.job_receipt import JobReceipt


def _completed_job(session: Session, *, payment_status: str = "escrowed", job_id: str = "job-1800") -> tuple[Job, JobPayment]:
    job = Job(
        id=job_id,
        client_id="client-1",
        state="COMPLETED",
        payload={"model": "linear-1"},
        assigned_miner_id="miner-b",
        constraints={"acceptance_window_seconds": 0},
        payment_id=f"pay-{job_id}",
        payment_status=payment_status,
        result={"output": {"x": 1}},
        receipt={"receipt_id": "r-1", "price": "0.01"},
        receipt_id="r-1",
        completed_at=datetime.now(UTC) - timedelta(minutes=5),
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    payment = JobPayment(
        id=f"pay-{job_id}",
        job_id=job.id,
        client_id="client-1",
        amount=Decimal("5"),
        currency="AITBC",
        status="escrowed",
        payment_method="aitbc_token",
        escrow_address=f"escrow_{job_id}",
        escrowed_at=datetime.now(UTC) - timedelta(minutes=10),
    )
    session.add(job)
    session.add(payment)
    session.add(
        PaymentEscrow(
            payment_id=payment.id,
            amount=Decimal("5"),
            currency="AITBC",
            address=f"escrow_{job_id}",
            is_active=True,
        )
    )
    session.add(JobReceipt(job_id=job.id, receipt_id="r-1", payload=dict(job.receipt)))
    session.commit()
    return job, payment


@pytest.fixture
def miner_client(db_session):
    from coordinator_api.main import app
    from aitbc.auth.dependencies import require_miner
    from coordinator_api.storage import get_session

    def override_session():
        yield db_session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[require_miner] = lambda: {"sub": "miner-b", "role": "miner"}
    yield TestClient(app)
    app.dependency_overrides.pop(get_session, None)
    app.dependency_overrides.pop(require_miner, None)


class _StubPaymentService:
    """Stand-in for PaymentService inside _retry_completed_settlement."""

    released: list[str] = []

    def __init__(self, session):
        pass

    async def release_payment(self, client_id, job_id, payment_id, reason=None, **kwargs) -> bool:
        type(self).released.append(payment_id)
        return type(self).next_result

    next_result = True


def _patch_payment_service(monkeypatch, result: bool):
    _StubPaymentService.next_result = result
    _StubPaymentService.released = []
    monkeypatch.setattr(
        "coordinator_api.contexts.payments.services.payments.PaymentService",
        _StubPaymentService,
    )


def _post_result(client: TestClient, job_id: str):
    return client.post(f"/v1/miners/{job_id}/result", json={"result": {"output": {"x": 1}}, "metrics": {}})


@pytest.mark.unit
def test_resubmit_after_failed_settle_retries_and_settles(miner_client, db_session, monkeypatch):
    """COMPLETED + escrowed -> resubmit retries the release; success marks released."""
    _completed_job(db_session)
    _patch_payment_service(monkeypatch, result=True)
    resp = _post_result(miner_client, "job-1800")
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "ok"
    db_session.expire_all()
    job = db_session.get(Job, "job-1800")
    assert job.state == "COMPLETED"
    assert job.payment_status == "released"
    assert _StubPaymentService.released == ["pay-job-1800"]


@pytest.mark.unit
def test_resubmit_after_failed_settle_stays_pending_and_retryable(miner_client, db_session, monkeypatch):
    """A still-failing release answers settlement_pending, keeps COMPLETED,
    and leaves the payment escrowed so a later resubmit/reconciler can retry."""
    _completed_job(db_session)
    _patch_payment_service(monkeypatch, result=False)
    resp = _post_result(miner_client, "job-1800")
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "settlement_pending"
    db_session.expire_all()
    job = db_session.get(Job, "job-1800")
    assert job.state == "COMPLETED"
    payment = db_session.get(JobPayment, "pay-job-1800")
    assert payment.status == "escrowed"
    # A second resubmit is still admitted — the retry is idempotent, not one-shot.
    _patch_payment_service(monkeypatch, result=True)
    resp2 = _post_result(miner_client, "job-1800")
    assert resp2.status_code == 200
    assert resp2.json()["status"] == "ok"


@pytest.mark.unit
def test_resubmit_creates_no_receipt_rows(miner_client, db_session, monkeypatch):
    """The retry path must not accumulate JobReceipt rows per resubmit."""
    _completed_job(db_session)
    before = db_session.execute(select(func.count()).select_from(JobReceipt)).scalar_one()
    _patch_payment_service(monkeypatch, result=True)
    _post_result(miner_client, "job-1800")
    _post_result(miner_client, "job-1800")
    db_session.expire_all()
    after = db_session.execute(select(func.count()).select_from(JobReceipt)).scalar_one()
    assert after == before


@pytest.mark.unit
def test_resubmit_on_settled_payment_still_409(miner_client, db_session):
    """Once the money moved there is nothing to retry — a resubmit is a real conflict."""
    job, payment = _completed_job(db_session)
    payment.status = "released"
    db_session.add(payment)
    job.payment_status = "released"
    db_session.add(job)
    db_session.commit()
    resp = _post_result(miner_client, "job-1800")
    assert resp.status_code == 409


@pytest.mark.unit
def test_resubmit_during_acceptance_window_still_409(miner_client, db_session):
    """pending_acceptance is inside the customer acceptance flow — releasing it
    here would bypass the window, so the resubmit stays a conflict."""
    job, payment = _completed_job(db_session)
    payment.status = "pending_acceptance"
    db_session.add(payment)
    job.payment_status = "pending_acceptance"
    db_session.add(job)
    db_session.commit()
    resp = _post_result(miner_client, "job-1800")
    assert resp.status_code == 409


@pytest.mark.unit
def test_resubmit_wrong_miner_still_403(miner_client, db_session, monkeypatch):
    job, _ = _completed_job(db_session, job_id="job-other")
    job.assigned_miner_id = "miner-x"
    db_session.add(job)
    db_session.commit()
    _patch_payment_service(monkeypatch, result=True)
    resp = _post_result(miner_client, "job-other")
    assert resp.status_code == 403
