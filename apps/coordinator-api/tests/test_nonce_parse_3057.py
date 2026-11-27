"""Pins for AUDIT-NONCE-FABRICATE-SETTLEMENT-1 / issue #3057.

``PaymentEscrowMixin._get_account_nonce`` used to answer ``0`` for every
nonce-probe failure shape — a 200 without a valid ``nonce`` field AND any
exception — so the escrow-lock path built (and, on the signed lane, could
submit) an ESCROW_LOCK at a fabricated nonce 0: a doomed envelope the
payment row then believed had been signed.

Contract (same as #3015/#3041/#3044): only a real non-negative int counts —
explicit ``0`` included. Missing, null, string, bool, float or negative
nonce, a non-dict payload, and any probe failure are all "no source" →
fail closed: no lock tx is built or submitted, and the payment records a
truthful retryable failure instead of a fabricated-nonce "success".
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
from coordinator_api.utils.rpc_parse import parse_account_nonce

BUYER = "0x08aB801150eF3496344cFA78fe025c3B48Caf435"
PROVIDER = "0xF4924759508E420eeD947BD33326731B11c4B7Df"
NODE_WALLET = "0x02B8cC0D4f4d84e5D0a4a4c9a9D04A9C7Dd3Ef01"


@pytest.fixture
def payment_session(db_engine, monkeypatch) -> Session:
    monkeypatch.setenv("NODE_WALLET_ADDRESS", NODE_WALLET)
    with Session(db_engine) as session:
        yield session


def _make_job(session: Session, job_id: str) -> Job:
    job = Job(id=job_id, client_id="client-1", state="QUEUED", payload={})
    session.add(job)
    session.commit()
    return job


def _payment_data(job_id: str) -> JobPaymentCreate:
    """No buyer signature and no explicit nonce — the only shape that makes
    the coordinator probe the buyer account nonce at all."""
    return JobPaymentCreate(
        job_id=job_id,
        amount=Decimal("5"),
        currency="AITBC",
        payment_method="aitbc_token",
        buyer_address=BUYER,
        provider_address=PROVIDER,
        buyer_lock_signature=None,
        buyer_lock_nonce=None,
    )


def _node_404_error() -> NetworkError:
    """The escrow GET 404s when no row exists — wrapped as NetworkError."""
    request = httpx.Request("GET", "http://node.invalid/rpc/escrow/job")
    response = httpx.Response(404, json={"detail": "escrow not found"}, request=request)
    http_error = httpx.HTTPStatusError("status 404", request=request, response=response)
    error = NetworkError("GET request failed")
    error.__cause__ = http_error
    return error


def _nonce_probe_client(account_get):
    """Mock client: ``.get`` answers the accounts probe via ``account_get``
    and 404s the escrow-record lookup; ``.get_json`` answers the chain-lock
    lookup with an empty list (no lock landed). ``.post`` must never fire."""
    mock_client = MagicMock()

    async def get_side_effect(url, *args, **kwargs):
        if "/rpc/accounts/" in url:
            return await account_get(url)
        raise _node_404_error()

    mock_client.get = AsyncMock(side_effect=get_side_effect)
    mock_client.get_json = AsyncMock(return_value=[])
    mock_client.post = AsyncMock()
    return mock_client


def _create(session: Session, job_id: str) -> JobPayment:
    service = PaymentService(session)
    return asyncio.run(service.create_payment("client-1", job_id, _payment_data(job_id)))


# ---------------------------------------------------------------------------
# parse_account_nonce unit pins
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "payload", [{}, {"nonce": None}, {"nonce": "5"}, {"nonce": True}, {"nonce": -1}, {"nonce": 2.0}, "junk", None]
)
def test_parse_account_nonce_rejects_malformed(payload):
    assert parse_account_nonce(payload) is None


@pytest.mark.parametrize("nonce", [0, 1, 42])
def test_parse_account_nonce_accepts_real_ints(nonce):
    assert parse_account_nonce({"nonce": nonce, "balance": 7}) == nonce


# ---------------------------------------------------------------------------
# End-to-end: the escrow-lock path fails closed on no nonce source
# ---------------------------------------------------------------------------


@patch("coordinator_api.contexts.payments.services.payments.AsyncAITBCHTTPClient")
@pytest.mark.parametrize(
    "account_payload",
    [
        {},  # missing nonce
        {"balance": 100},  # no nonce field at all
        {"nonce": None},
        {"nonce": "5"},
        {"nonce": True},
        {"nonce": False},
        {"nonce": -1},
        {"nonce": 2.5},
        "not-a-dict",
    ],
)
def test_malformed_nonce_response_fails_closed(mock_client_cls, payment_session, account_payload):
    """A 200 account response without a real nonce is 'no source': the lock
    is never submitted and the payment fails retryable, not 'unsigned'."""
    job = _make_job(payment_session, f"job-nonce-{abs(hash(str(account_payload))) % 10**8}")

    async def account_get(url):
        return account_payload

    mock_client_cls.return_value = _nonce_probe_client(account_get)

    payment = _create(payment_session, job.id)

    assert payment.status == "failed"
    # Truthful retryable failure — NOT the fabricated-0 outcome ("unsigned").
    assert payment.meta_data["escrow_error_kind"] == "unavailable"
    mock_client_cls.return_value.post.assert_not_awaited()
    escrows = payment_session.exec(select(PaymentEscrow).where(PaymentEscrow.payment_id == payment.id)).all()
    assert escrows == []


@patch("coordinator_api.contexts.payments.services.payments.AsyncAITBCHTTPClient")
def test_nonce_probe_exception_fails_closed(mock_client_cls, payment_session):
    """A probe exception is 'no source' too — never a silent nonce 0."""
    job = _make_job(payment_session, "job-nonce-probe-down")

    async def account_get(url):
        raise NetworkError("GET request failed: connect timeout")

    mock_client_cls.return_value = _nonce_probe_client(account_get)

    payment = _create(payment_session, job.id)

    assert payment.status == "failed"
    assert payment.meta_data["escrow_error_kind"] == "unavailable"
    mock_client_cls.return_value.post.assert_not_awaited()
    escrows = payment_session.exec(select(PaymentEscrow).where(PaymentEscrow.payment_id == payment.id)).all()
    assert escrows == []


@patch("coordinator_api.contexts.payments.services.payments.AsyncAITBCHTTPClient")
@pytest.mark.parametrize("nonce", [0, 9])
def test_valid_nonce_still_reaches_lock_build(mock_client_cls, payment_session, nonce):
    """Explicit nonce 0 and a real nonce are both valid: the flow proceeds to
    build the lock tx and fails only on the (expected) missing signature —
    proving the probe result is actually used, not discarded."""
    job = _make_job(payment_session, f"job-nonce-ok-{nonce}")

    async def account_get(url):
        return {"nonce": nonce, "balance": 100}

    mock_client_cls.return_value = _nonce_probe_client(account_get)

    payment = _create(payment_session, job.id)

    assert payment.status == "failed"
    assert payment.meta_data["escrow_error_kind"] == "unsigned"
    mock_client_cls.return_value.post.assert_not_awaited()
