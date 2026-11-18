"""#2242: a miner-reported ``result.status="failed"`` must not complete the job.

``production_miner._submit_failure`` posts ``{"result": {"status": "failed",
"error": ...}}`` to ``POST /v1/miners/{job_id}/result`` instead of ``/fail``.
Before the fix ``submit_result`` marked the job COMPLETED unconditionally,
issued a receipt, and moved the escrow to ``pending_acceptance`` — wedging
paid escrow behind a result that explicitly failed.

The fix routes ``status == "failed"`` to the failure path: job FAILED with
the miner's error, no receipt, no settlement, ``job.result`` left unset so
the escrowed payment stays refundable by the customer.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import asyncio

import pytest
from aitbc_shared import JobPayment, PaymentEscrow
from fastapi.testclient import TestClient
from sqlmodel import Session, func, select

from coordinator_api.contexts.infrastructure.domain.job import Job
from coordinator_api.contexts.infrastructure.domain.job_receipt import JobReceipt
from coordinator_api.contexts.infrastructure.domain.miner import Miner


def _running_job(
    session: Session,
    job_id: str = "job-2242",
    *,
    escrowed: bool = True,
    miner_id: str = "miner-b",
) -> tuple[Job, JobPayment | None]:
    payment = None
    if escrowed:
        payment = JobPayment(
            id=f"pay-{job_id}",
            job_id=job_id,
            client_id="client-1",
            amount=Decimal("0.5"),
            currency="AITBC",
            status="escrowed",
            payment_method="aitbc_token",
            escrow_address=f"escrow_{job_id}",
            escrowed_at=datetime.now(UTC) - timedelta(minutes=5),
        )
        session.add(payment)
        session.add(
            PaymentEscrow(
                payment_id=payment.id,
                amount=Decimal("0.5"),
                currency="AITBC",
                address=f"escrow_{job_id}",
                is_active=True,
            )
        )
    job = Job(
        id=job_id,
        client_id="client-1",
        state="RUNNING",
        payload={"type": "inference", "model": "linear-1"},
        assigned_miner_id=miner_id,
        payment_id=payment.id if payment else None,
        payment_status="escrowed" if payment else None,
        payment_amount=Decimal("0.5") if payment else None,
        payment_token="AITBC" if payment else None,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    session.add(job)
    miner = session.get(Miner, miner_id)
    if miner is None:
        miner = Miner(
            id=miner_id,
            inflight=1,
            status="ONLINE",
            extra_metadata={},
            capabilities={},
        )
        session.add(miner)
    else:
        miner.inflight += 1
        session.add(miner)
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


def _post_result(client: TestClient, job_id: str, result: dict):
    return client.post(f"/v1/miners/{job_id}/result", json={"result": result, "metrics": {}})


@pytest.mark.unit
def test_failed_result_marks_job_failed_without_receipt_or_settlement(miner_client, db_session):
    """The sandbox repro: status="failed" must produce FAILED, not COMPLETED."""
    _running_job(db_session)
    resp = _post_result(
        miner_client,
        "job-2242",
        {"status": "failed", "error": "no ollama models available"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["job_state"] == "FAILED"
    assert resp.json()["receipt"] is None

    db_session.expire_all()
    job = db_session.get(Job, "job-2242")
    assert job.state == "FAILED"
    assert job.error == "no ollama models available"
    # No delivered result: keeps the escrow refundable and off the
    # acceptance-window sweeper entirely.
    assert job.result is None
    assert job.receipt is None
    assert job.receipt_id is None
    assert job.payment_status == "escrowed"

    payment = db_session.get(JobPayment, "pay-job-2242")
    assert payment.status == "escrowed"

    receipts = db_session.execute(
        select(func.count()).select_from(JobReceipt).where(JobReceipt.job_id == "job-2242")
    ).scalar_one()
    assert receipts == 0

    miner = db_session.get(Miner, "miner-b")
    assert miner.inflight == 0
    assert miner.jobs_failed == 1
    assert miner.jobs_completed == 0


@pytest.mark.unit
def test_failed_result_status_is_case_insensitive(miner_client, db_session):
    _running_job(db_session, job_id="job-2242b", escrowed=False)
    resp = _post_result(miner_client, "job-2242b", {"status": " FAILED "})
    assert resp.status_code == 200, resp.text
    db_session.expire_all()
    job = db_session.get(Job, "job-2242b")
    assert job.state == "FAILED"
    assert job.error == "miner reported job failure"


@pytest.mark.unit
def test_failed_result_escrow_stays_refundable_by_customer(miner_client, db_session):
    """Payment path: FAILED + escrowed + undelivered -> client refund works."""
    _running_job(db_session)
    resp = _post_result(
        miner_client,
        "job-2242",
        {"status": "failed", "error": "ollama error"},
    )
    assert resp.status_code == 200, resp.text

    from coordinator_api.contexts.payments.services.payments import PaymentService

    with patch("coordinator_api.contexts.payments.services.payments.AsyncAITBCHTTPClient") as cls:
        chain = AsyncMock()
        chain.get.return_value = {"state": "funded"}
        chain.post.return_value = {"success": True, "refund_tx_hash": "0xrefundtx"}
        cls.return_value = chain
        refunded = asyncio.run(PaymentService(db_session).refund_payment("client-1", "job-2242", "pay-job-2242", "job failed"))
    assert refunded is True
    db_session.expire_all()
    payment = db_session.get(JobPayment, "pay-job-2242")
    assert payment.status == "refunded"
    job = db_session.get(Job, "job-2242")
    assert job.payment_status == "refunded"


@pytest.mark.unit
def test_failed_result_resubmit_is_409(miner_client, db_session):
    """Once FAILED the job is terminal — a second result submit conflicts."""
    _running_job(db_session, job_id="job-2242c", escrowed=False)
    first = _post_result(miner_client, "job-2242c", {"status": "failed", "error": "boom"})
    assert first.status_code == 200, first.text
    second = _post_result(miner_client, "job-2242c", {"status": "failed", "error": "boom"})
    assert second.status_code == 409


@pytest.mark.unit
def test_success_result_path_unchanged(miner_client, db_session):
    """status="completed" (and no status at all) still completes + receipts."""
    _running_job(db_session, job_id="job-ok1", escrowed=False)
    resp = _post_result(
        miner_client,
        "job-ok1",
        {"status": "completed", "output": {"answer": 42}},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "ok"
    db_session.expire_all()
    job = db_session.get(Job, "job-ok1")
    assert job.state == "COMPLETED"
    # The result payload is stored and the job completed — the receipt row
    # itself is signer-gated and is None in this test environment.
    assert job.result is not None
    assert job.result["status"] == "completed"

    # And a result with no status field behaves exactly as before.
    _running_job(db_session, job_id="job-ok2", escrowed=False)
    resp2 = _post_result(miner_client, "job-ok2", {"output": {"answer": 7}})
    assert resp2.status_code == 200, resp2.text
    db_session.expire_all()
    assert db_session.get(Job, "job-ok2").state == "COMPLETED"
