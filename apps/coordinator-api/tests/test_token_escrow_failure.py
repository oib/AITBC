"""Regression tests for the token-escrow failure path.

Before the fix, ``_create_token_escrow`` swallowed every refusal — node 4xx,
network failures, the missing-signature early return — and returned None, so
the payment kept its ``pending`` default. The purchase endpoint only rolls
the booking back on ``failed``/``skipped``, so the buyer got HTTP 200
"purchased" with no escrow behind it and the job queued to its TTL. These
tests pin the failure semantics: the payment is marked ``failed`` with a
sanitized, classified reason.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from sqlmodel import Session, select

from aitbc.exceptions import NetworkError
from aitbc_shared import JobPayment, PaymentEscrow

from coordinator_api.contexts.infrastructure.domain.job import Job
from coordinator_api.contexts.payments.services.payments import PaymentService
from coordinator_api.schemas import JobPaymentCreate

BUYER = "0x08aB801150eF3496344cFA78fe025c3B48Caf435"
PROVIDER = "0xF4924759508E420eeD947BD33326731B11c4B7Df"
NODE_WALLET = "0x02B8cC0D4f4d84e5D0a4a4c9a9D04A9C7Dd3Ef01"


@pytest.fixture
def payment_session(db_engine, monkeypatch) -> Session:
    monkeypatch.setenv("NODE_WALLET_ADDRESS", NODE_WALLET)
    with Session(db_engine) as session:
        yield session


def _make_job(session: Session, job_id: str, client_id: str = "client-1") -> Job:
    job = Job(id=job_id, client_id=client_id, state="QUEUED", payload={})
    session.add(job)
    session.commit()
    return job


def _payment_data(job_id: str, **overrides) -> JobPaymentCreate:
    data = {
        "job_id": job_id,
        "amount": Decimal("5"),
        "currency": "AITBC",
        "payment_method": "aitbc_token",
        "buyer_address": BUYER,
        "provider_address": PROVIDER,
        "buyer_lock_signature": "0xdeadbeef",
        "buyer_lock_nonce": 7,
    }
    data.update(overrides)
    return JobPaymentCreate(**data)


def _network_error_from_status(status_code: int, body: dict | None = None) -> NetworkError:
    """A NetworkError wrapping an httpx.HTTPStatusError, as the client raises."""
    request = httpx.Request("POST", "http://node.invalid/rpc/escrow/create")
    response = httpx.Response(status_code, json=body or {}, request=request)
    http_error = httpx.HTTPStatusError(f"status {status_code}", request=request, response=response)
    error = NetworkError("POST request failed")
    error.__cause__ = http_error
    return error


def _create(session: Session, job_id: str, data: JobPaymentCreate) -> JobPayment:
    service = PaymentService(session)
    return asyncio.run(service.create_payment("client-1", job_id, data))


@patch("coordinator_api.contexts.payments.services.payments.AsyncAITBCHTTPClient")
def test_node_422_refusal_marks_payment_failed(mock_client_cls, payment_session):
    """A node 4xx is a permanent refusal: failed, with the node's reason."""
    job = _make_job(payment_session, "job-refuse-422")
    mock_client = MagicMock()
    mock_client.post = AsyncMock(side_effect=_network_error_from_status(422, {"detail": "energy quote rate is stale"}))
    mock_client_cls.return_value = mock_client

    payment = _create(payment_session, job.id, _payment_data(job.id))

    assert payment.status == "failed"
    assert payment.meta_data["escrow_error_kind"] == "refused"
    assert payment.meta_data["escrow_error"] == "energy quote rate is stale"
    updated_job = payment_session.get(Job, job.id)
    assert updated_job.payment_status == "failed"
    escrows = payment_session.exec(select(PaymentEscrow).where(PaymentEscrow.payment_id == payment.id)).all()
    assert escrows == []


@patch("coordinator_api.contexts.payments.services.payments.AsyncAITBCHTTPClient")
def test_node_500_marks_payment_failed_unavailable(mock_client_cls, payment_session):
    """A 5xx is retryable: failed, reported generically (no node detail leak)."""
    job = _make_job(payment_session, "job-refuse-500")
    mock_client = MagicMock()
    mock_client.post = AsyncMock(side_effect=_network_error_from_status(500, {"detail": "internal trace: /srv/node/db"}))
    mock_client_cls.return_value = mock_client

    payment = _create(payment_session, job.id, _payment_data(job.id))

    assert payment.status == "failed"
    assert payment.meta_data["escrow_error_kind"] == "unavailable"
    assert "/srv/" not in payment.meta_data["escrow_error"]
    assert "http" not in payment.meta_data["escrow_error"].lower()


@patch("coordinator_api.contexts.payments.services.payments.AsyncAITBCHTTPClient")
def test_connect_error_marks_payment_failed_unavailable(mock_client_cls, payment_session):
    """A transport failure with no HTTP status is retryable: failed, generic."""
    job = _make_job(payment_session, "job-conn-error")
    mock_client = MagicMock()
    mock_client.post = AsyncMock(side_effect=NetworkError("POST request failed: connect timeout"))
    mock_client_cls.return_value = mock_client

    payment = _create(payment_session, job.id, _payment_data(job.id))

    assert payment.status == "failed"
    assert payment.meta_data["escrow_error_kind"] == "unavailable"


@patch("coordinator_api.contexts.payments.services.payments.AsyncAITBCHTTPClient")
def test_missing_buyer_signature_marks_payment_failed(mock_client_cls, payment_session):
    """No signature is a permanent client error: failed; no POST is attempted."""
    job = _make_job(payment_session, "job-unsigned")
    mock_client = MagicMock()
    mock_client.post = AsyncMock()
    mock_client_cls.return_value = mock_client

    data = _payment_data(job.id, buyer_lock_signature=None)
    payment = _create(payment_session, job.id, data)

    assert payment.status == "failed"
    assert payment.meta_data["escrow_error_kind"] == "unsigned"
    mock_client.post.assert_not_called()
    escrows = payment_session.exec(select(PaymentEscrow).where(PaymentEscrow.payment_id == payment.id)).all()
    assert escrows == []


@patch("coordinator_api.contexts.payments.services.payments.AsyncAITBCHTTPClient")
def test_node_refusal_without_detail_falls_back_to_generic(mock_client_cls, payment_session):
    """A 4xx body without a `detail` string gets a bounded generic reason."""
    job = _make_job(payment_session, "job-refuse-no-detail")
    mock_client = MagicMock()
    mock_client.post = AsyncMock(side_effect=_network_error_from_status(422, {"error": {"code": 1}}))
    mock_client_cls.return_value = mock_client

    payment = _create(payment_session, job.id, _payment_data(job.id))

    assert payment.status == "failed"
    assert payment.meta_data["escrow_error_kind"] == "refused"
    assert payment.meta_data["escrow_error"] == "the node refused the escrow (HTTP 422)"


@patch("coordinator_api.contexts.payments.services.payments.AsyncAITBCHTTPClient")
def test_successful_escrow_still_escrows(mock_client_cls, payment_session):
    """Sanity: the happy path is unchanged — escrowed payment + escrow row."""
    job = _make_job(payment_session, "job-ok")
    mock_client = MagicMock()
    mock_client.post = AsyncMock(return_value={"contract_id": "0xescrow123"})
    mock_client_cls.return_value = mock_client

    payment = _create(payment_session, job.id, _payment_data(job.id))

    assert payment.status == "escrowed"
    assert payment.escrow_address == "0xescrow123"
    escrows = payment_session.exec(select(PaymentEscrow).where(PaymentEscrow.payment_id == payment.id)).all()
    assert len(escrows) == 1
