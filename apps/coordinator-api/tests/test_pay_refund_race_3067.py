"""#3067: refund/completion race — refunded work must never complete unpaid.

Two cooperating defects let a buyer collect both the refund and the
delivered work: ``refund_payment`` fired the irreversible chain refund
before cancelling the job, and ``submit_result`` wrote COMPLETED as a
blind read-check-write across seconds of receipt/ZK work. These pins cover
the ordering inversion (job terminal BEFORE the chain POST), the
conditional RUNNING→COMPLETED completion CAS losing to a mid-flight
cancel, the completed+delivered recheck, and the refund relay sharing the
same transition discipline plus recording the refund on the payment row.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlmodel import Session, select, update

from aitbc.auth import create_access_token
from aitbc_shared import JobPayment

from coordinator_api.contexts.infrastructure.domain.job import Job
from coordinator_api.contexts.infrastructure.domain.miner import Miner
from coordinator_api.contexts.infrastructure.domain.user import User, Wallet
from coordinator_api.contexts.infrastructure.services.receipts import ReceiptService
from coordinator_api.contexts.payments.services.escrow_refund_relay import EscrowRefundRelayService
from coordinator_api.contexts.payments.services.payments import PaymentService

BUYER = "0x08aB801150eF3496344cFA78fe025c3B48Caf435"
PROVIDER = "0xF4924759508E420eeD947BD33326731B11c4B7Df"
RELAY_PATCH = "coordinator_api.contexts.payments.services.escrow_refund_relay.AsyncAITBCHTTPClient"
PAY_PATCH = "coordinator_api.contexts.payments.services.payments.AsyncAITBCHTTPClient"
PAST = datetime.now(UTC) - timedelta(hours=1)
FUTURE = datetime.now(UTC) + timedelta(hours=1)


@pytest.fixture
def payment_session(db_engine, monkeypatch) -> Session:
    monkeypatch.setenv("NODE_WALLET_ADDRESS", "0x02B8cC0D4f4d84e5D0a4a4c9a9D04A9C7Dd3Ef01")
    with Session(db_engine) as session:
        yield session


def _job(session: Session, job_id: str, state: str = "RUNNING", **kw) -> Job:
    job = Job(
        id=job_id,
        client_id=kw.pop("client_id", "client-1"),
        state=state,
        payload={},
        expires_at=kw.pop("expires_at", FUTURE),
        **kw,
    )
    session.add(job)
    session.commit()
    return job


def _escrowed_payment(session: Session, job_id: str, payment_id: str | None = None) -> JobPayment:
    payment = JobPayment(
        id=payment_id or f"pay-{job_id}",
        job_id=job_id,
        amount=Decimal("5"),
        currency="AITBC",
        status="escrowed",
        payment_method="aitbc_token",
        escrow_address="escrow_abc",
        escrowed_at=datetime.now(UTC),
    )
    session.add(payment)
    session.commit()
    return payment


def _chain_mock(*, post_side_effect=None) -> AsyncMock:
    client = AsyncMock()
    client.get.return_value = {"state": "funded"}
    client.get_json.return_value = []
    if post_side_effect is not None:
        client.post.side_effect = post_side_effect
    else:
        client.post.return_value = {"success": True, "refund_tx_hash": "0xrefund1"}
    return client


# ---------------------------------------------------------------------------
# refund_payment ordering
# ---------------------------------------------------------------------------


def test_refund_cancels_live_job_before_chain_call(payment_session, db_engine):
    """The job must be CANCELED before the irreversible chain refund POST."""
    job = _job(payment_session, "job-r1", state="RUNNING")
    payment = _escrowed_payment(payment_session, job.id)
    seen: dict = {}

    async def post(url, *a, **k):
        with Session(db_engine) as probe:
            seen["state_at_post"] = probe.get(Job, job.id).state
        return {"success": True, "refund_tx_hash": "0xrefund1"}

    mock = _chain_mock(post_side_effect=post)
    with patch(PAY_PATCH, return_value=mock):
        result = asyncio.run(PaymentService(payment_session).refund_payment("client-1", job.id, payment.id, "test"))

    assert result is True
    assert seen["state_at_post"] == "CANCELED"
    payment_session.refresh(job)
    assert job.state == "CANCELED"
    payment_session.refresh(payment)
    assert payment.status == "refunded"


def test_refund_terminal_job_leaves_state_alone(payment_session):
    """A FAILED job has nothing to cancel — refund proceeds normally."""
    job = _job(payment_session, "job-r2", state="FAILED")
    payment = _escrowed_payment(payment_session, job.id)
    mock = _chain_mock()
    with patch(PAY_PATCH, return_value=mock):
        result = asyncio.run(PaymentService(payment_session).refund_payment("client-1", job.id, payment.id, "test"))
    assert result is True
    payment_session.refresh(job)
    assert job.state == "FAILED"


def test_cancel_helper_refuses_completed_delivered_for_client(payment_session):
    """A job that completed with delivered output closes the refund window."""
    job = _job(payment_session, "job-r3", state="COMPLETED", result={"output": {"x": 1}})
    service = PaymentService(payment_session)
    with pytest.raises(HTTPException) as exc:
        service._cancel_live_job_for_refund(job, allow_completed=False)
    assert exc.value.status_code == 403
    payment_session.refresh(job)
    assert job.state == "COMPLETED"
    # Admin refunds are deliberate and proceed.
    service._cancel_live_job_for_refund(job, allow_completed=True)
    payment_session.refresh(job)
    assert job.state == "COMPLETED"


def test_cancel_helper_allows_completed_failure_result(payment_session):
    """COMPLETED with a failure payload delivered nothing — refund may proceed."""
    job = _job(payment_session, "job-r4", state="COMPLETED", result={"status": "failed", "error": "boom"})
    PaymentService(payment_session)._cancel_live_job_for_refund(job, allow_completed=False)
    payment_session.refresh(job)
    assert job.state == "COMPLETED"


# ---------------------------------------------------------------------------
# submit_result conditional completion
# ---------------------------------------------------------------------------


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


def _running_job(session: Session, job_id: str) -> Job:
    job = Job(
        id=job_id,
        client_id="client-1",
        state="RUNNING",
        payload={"model": "linear-1"},
        assigned_miner_id="miner-b",
        constraints={},
        expires_at=FUTURE,
    )
    session.add(job)
    session.add(Miner(id="miner-b", inflight=1, status="ONLINE", extra_metadata={}, capabilities={}))
    session.commit()
    return job


def _post_result(client: TestClient, job_id: str):
    return client.post(f"/v1/miners/{job_id}/result", json={"result": {"output": {"x": 1}}, "metrics": {}})


def test_result_completes_running_job_control(miner_client, db_session):
    _running_job(db_session, "job-m1")
    resp = _post_result(miner_client, "job-m1")
    assert resp.status_code == 200, resp.text
    db_session.expire_all()
    assert db_session.get(Job, "job-m1").state == "COMPLETED"


def test_completion_cas_loses_to_midflight_cancel(miner_client, db_session, db_engine, monkeypatch):
    """The decisive pin: a refund commits CANCELED while the receipt is being
    built (the seconds-wide ZK window). The conditional completion must lose —
    the job stays CANCELED and no result is stored."""
    _running_job(db_session, "job-m2")
    original = ReceiptService.create_receipt

    def cancel_midflight(self, job, *args, **kwargs):
        # A second session commits the refund-side cancel, exactly like
        # _cancel_live_job_for_refund does mid-request.
        with Session(db_engine) as other:
            other.execute(update(Job).where(Job.id == job.id).values(state="CANCELED"))
            other.commit()
        return original(self, job, *args, **kwargs)

    monkeypatch.setattr(ReceiptService, "create_receipt", cancel_midflight)
    resp = _post_result(miner_client, "job-m2")
    assert resp.status_code == 409, resp.text
    db_session.expire_all()
    job = db_session.get(Job, "job-m2")
    assert job.state == "CANCELED"
    assert job.result is None
    assert job.receipt_id is None


# ---------------------------------------------------------------------------
# escrow refund relay
# ---------------------------------------------------------------------------


def _relay_actor(db_session: Session, sub: str) -> dict[str, str]:
    if db_session.get(User, sub) is None:
        db_session.add(User(id=sub, email=f"{sub}@example.com", username=sub))
    existing = db_session.execute(select(Wallet).where(Wallet.address == BUYER.lower())).scalars().first()
    if existing is not None:
        existing.user_id = sub
    else:
        db_session.add(Wallet(user_id=sub, address=BUYER.lower()))
    db_session.commit()
    return {"Authorization": f"Bearer {create_access_token(sub, 'client')}"}


def _relay_escrow(buyer: str = BUYER, **extra) -> dict:
    escrow = {
        "job_id": "job_rel",
        "contract_id": "0xc1",
        "state": "funded",
        "buyer": buyer,
        "provider": PROVIDER,
        "amount": "2.0",
        "released_at": None,
        "refunded_at": None,
        "release_tx_hash": None,
        "refund_tx_hash": None,
    }
    escrow.update(extra)
    return escrow


def _relay_chain_mock(post_side_effect=None) -> AsyncMock:
    client = AsyncMock()
    client.get.return_value = _relay_escrow()
    client.get_json.return_value = []
    if post_side_effect is not None:
        client.post.side_effect = post_side_effect
    else:
        client.post.return_value = {"success": True, "refund_tx_hash": "0xref-relay", "contract_id": "0xc1"}
    return client


def test_relay_refund_cancels_expired_running_job_and_marks_payment(client, db_session):
    """Expired RUNNING job: relay refund must cancel the job, mark the payment,
    and record the hash — the job can no longer deliver unpaid work."""
    headers = _relay_actor(db_session, "c-relay-1")
    job = _job(db_session, "job_rel", state="RUNNING", client_id="c-relay-1", expires_at=PAST)
    payment = _escrowed_payment(db_session, job.id)
    mock = _relay_chain_mock()
    with patch(RELAY_PATCH, return_value=mock):
        resp = client.post("/v1/escrow/refund", json={"job_id": "job_rel"}, headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["refund_tx_hash"] == "0xref-relay"
    db_session.expire_all()
    assert db_session.get(Job, "job_rel").state == "CANCELED"
    assert db_session.get(JobPayment, payment.id).status == "refunded"
    assert db_session.get(JobPayment, payment.id).refund_transaction_hash == "0xref-relay"


def test_relay_refund_cancels_before_chain_post(client, db_session, db_engine):
    """Ordering pin for the relay: job is CANCELED when the chain POST fires."""
    headers = _relay_actor(db_session, "c-relay-2")
    job = _job(db_session, "job_rel", state="RUNNING", client_id="c-relay-2", expires_at=PAST)
    _escrowed_payment(db_session, job.id)
    seen: dict = {}

    async def post(url, *a, **k):
        with Session(db_engine) as probe:
            seen["state_at_post"] = probe.get(Job, "job_rel").state
        return {"success": True, "refund_tx_hash": "0xref-relay", "contract_id": "0xc1"}

    mock = _relay_chain_mock(post_side_effect=post)
    with patch(RELAY_PATCH, return_value=mock):
        resp = client.post("/v1/escrow/refund", json={"job_id": "job_rel"}, headers=headers)
    assert resp.status_code == 200, resp.text
    assert seen["state_at_post"] == "CANCELED"


def test_relay_cancel_helper_refuses_completed(client, db_session):
    """The relay's own cancel refuses a job that completed mid-flight."""
    _job(db_session, "job_rel", state="COMPLETED", client_id="c-x")
    service = EscrowRefundRelayService(db_session)
    with pytest.raises(HTTPException) as exc:
        service._cancel_live_job_for_refund("job_rel")
    assert exc.value.status_code == 409
    db_session.expire_all()
    assert db_session.get(Job, "job_rel").state == "COMPLETED"
