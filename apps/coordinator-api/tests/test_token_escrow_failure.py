"""Regression tests for the token-escrow failure path.

Before the fix, ``_create_token_escrow`` swallowed every refusal — node 4xx,
network failures, the missing-signature early return — and returned None, so
the payment kept its ``pending`` default. The purchase endpoint only rolls
the booking back on ``failed``/``skipped``, so the buyer got HTTP 200
"purchased" with no escrow behind it and the job queued to its TTL. These
tests pin the failure semantics: the payment is marked ``failed`` with a
sanitized, classified reason — and, for the ambiguous kinds (a lost POST
response may still have committed the lock), an escrow lookup runs first so
a landed lock is adopted as ``escrowed``, confirmed absence is retriable,
and an unreadable state is ``funding_unknown`` rather than falsely clean.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from sqlmodel import Session, select

from aitbc.exceptions import AmbiguousRequestError, NetworkError
from aitbc.network import AsyncAITBCHTTPClient
from aitbc_shared import JobPayment, PaymentEscrow

from coordinator_api.contexts.infrastructure.domain.job import Job
from coordinator_api.contexts.payments.services.payments import PaymentService, _lookup_escrow_record
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


def _node_404_error() -> NetworkError:
    """The escrow GET 404s when no row exists — wrapped as NetworkError."""
    return _network_error_from_status(404, {"detail": "escrow not found"})


def _chain_lock_txs(*tx_hashes: str, job_id: str) -> list[dict]:
    """Transactions the /rpc/transactions lookup returns for ESCROW_LOCK."""
    return [{"tx_hash": h, "payload": {"job_id": job_id}} for h in tx_hashes]


def _make_payment(session: Session, job: Job) -> JobPayment:
    """A persisted payment row for direct _recover_ambiguous_escrow calls."""
    payment = JobPayment(
        job_id=job.id,
        amount=Decimal("5"),
        currency="AITBC",
        payment_method="aitbc_token",
        meta_data={},
    )
    session.add(payment)
    session.commit()
    return payment


def _mock_transport_client(monkeypatch, handler) -> list[httpx.Request]:
    """Route the real AsyncAITBCHTTPClient through an httpx.MockTransport.

    The production client constructs ``httpx.AsyncClient`` per request, so
    swapping the class for a factory that injects the transport exercises the
    genuine code path — retry policy, raise_for_status, NetworkError wrapping
    — with no stubbed methods. Returns the recorded request list.
    """
    calls: list[httpx.Request] = []

    def recording(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return handler(request)

    transport = httpx.MockTransport(recording)
    real_async_client = httpx.AsyncClient

    def client_factory(*args, **kwargs):
        kwargs["transport"] = transport
        return real_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", client_factory)
    return calls


@patch("coordinator_api.contexts.payments.services.payments.AsyncAITBCHTTPClient")
def test_node_500_marks_payment_failed_unavailable(mock_client_cls, payment_session):
    """A 5xx is retryable: failed, reported generically (no node detail leak)."""
    job = _make_job(payment_session, "job-refuse-500")
    mock_client = MagicMock()
    mock_client.post = AsyncMock(side_effect=_network_error_from_status(500, {"detail": "internal trace: /srv/node/db"}))
    mock_client.get = AsyncMock(side_effect=_node_404_error())
    mock_client.get_json = AsyncMock(return_value=[])
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
    mock_client.get = AsyncMock(side_effect=_node_404_error())
    mock_client.get_json = AsyncMock(return_value=[])
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


@patch("coordinator_api.contexts.payments.services.payments.AsyncAITBCHTTPClient")
def test_ambiguous_post_recovers_escrowed_when_lock_landed(mock_client_cls, payment_session):
    """Response lost after commit: the escrow record shows the lock → escrowed."""
    job = _make_job(payment_session, "job-ambiguous-recover")
    mock_client = MagicMock()
    mock_client.post = AsyncMock(side_effect=AmbiguousRequestError("outcome unknown"))
    mock_client.get = AsyncMock(return_value={"contract_id": "0xescrowA", "lock_tx_hash": "0xlock1", "state": "funded"})
    mock_client_cls.return_value = mock_client

    payment = _create(payment_session, job.id, _payment_data(job.id))

    assert payment.status == "escrowed"
    assert payment.escrow_address == "0xescrowA"
    assert payment.meta_data["escrow_recovered"] is True
    assert payment.meta_data["escrow_lock_tx_hash"] == "0xlock1"
    escrows = payment_session.exec(select(PaymentEscrow).where(PaymentEscrow.payment_id == payment.id)).all()
    assert len(escrows) == 1
    updated_job = payment_session.get(Job, job.id)
    assert updated_job.payment_status == "escrowed"
    mock_client.get_json.assert_not_called()  # record hit — no chain fallback needed


@patch("coordinator_api.contexts.payments.services.payments.AsyncAITBCHTTPClient")
def test_ambiguous_post_recovers_via_chain_when_row_missing(mock_client_cls, payment_session):
    """Row write lost but lock sealed: the chain lookup still finds it → escrowed."""
    job = _make_job(payment_session, "job-ambiguous-chain")
    mock_client = MagicMock()
    mock_client.post = AsyncMock(side_effect=AmbiguousRequestError("outcome unknown"))
    mock_client.get = AsyncMock(side_effect=_node_404_error())
    mock_client.get_json = AsyncMock(return_value=_chain_lock_txs("0xlock9", job_id=job.id))
    mock_client_cls.return_value = mock_client

    payment = _create(payment_session, job.id, _payment_data(job.id))

    assert payment.status == "escrowed"
    assert payment.meta_data["escrow_recovered"] is True
    assert payment.meta_data["escrow_lock_tx_hash"] == "0xlock9"
    escrows = payment_session.exec(select(PaymentEscrow).where(PaymentEscrow.payment_id == payment.id)).all()
    assert len(escrows) == 1


@patch("coordinator_api.contexts.payments.services.payments.AsyncAITBCHTTPClient")
def test_ambiguous_post_marks_failed_unavailable_when_no_lock(mock_client_cls, payment_session):
    """Response lost and nothing committed: confirmed absent → failed, retriable."""
    job = _make_job(payment_session, "job-ambiguous-none")
    mock_client = MagicMock()
    mock_client.post = AsyncMock(side_effect=AmbiguousRequestError("outcome unknown"))
    mock_client.get = AsyncMock(side_effect=_node_404_error())
    mock_client.get_json = AsyncMock(return_value=[])
    mock_client_cls.return_value = mock_client

    payment = _create(payment_session, job.id, _payment_data(job.id))

    assert payment.status == "failed"
    assert payment.meta_data["escrow_error_kind"] == "unavailable"
    assert "retried" in payment.meta_data["escrow_error"]
    mock_client.get.assert_called_once()  # the lock lookup ran before the mark
    escrows = payment_session.exec(select(PaymentEscrow).where(PaymentEscrow.payment_id == payment.id)).all()
    assert escrows == []


@patch("coordinator_api.contexts.payments.services.payments.AsyncAITBCHTTPClient")
def test_ambiguous_post_marks_funding_unknown_when_lookup_fails(mock_client_cls, payment_session):
    """Lock lookup unreadable: funding state is unknown, never a clean retry."""
    job = _make_job(payment_session, "job-ambiguous-unknown")
    mock_client = MagicMock()
    mock_client.post = AsyncMock(side_effect=AmbiguousRequestError("outcome unknown"))
    mock_client.get = AsyncMock(side_effect=NetworkError("GET request failed: connect timeout"))
    mock_client_cls.return_value = mock_client

    payment = _create(payment_session, job.id, _payment_data(job.id))

    assert payment.status == "failed"
    assert payment.meta_data["escrow_error_kind"] == "funding_unknown"
    assert job.id in payment.meta_data["escrow_error"]
    assert "may have landed" in payment.meta_data["escrow_error"]
    escrows = payment_session.exec(select(PaymentEscrow).where(PaymentEscrow.payment_id == payment.id)).all()
    assert escrows == []


# ---------------------------------------------------------------------------
# Real-client coverage: the lookups run against AsyncAITBCHTTPClient itself
# (retry policy, raise_for_status, NetworkError wrapping) with a MockTransport
# underneath, not a stubbed client.
# ---------------------------------------------------------------------------


def test_real_client_escrow_get_404_returns_none(monkeypatch):
    """A definitive 404 maps to None — and a 4xx is never retried."""
    calls = _mock_transport_client(
        monkeypatch, lambda req: httpx.Response(404, json={"detail": "escrow not found"}, request=req)
    )
    client = AsyncAITBCHTTPClient(timeout=5.0, api_key=None, max_retries=1)

    record = asyncio.run(_lookup_escrow_record("http://node.invalid", client, "job-x"))

    assert record is None
    assert len(calls) == 1


def test_real_client_escrow_get_500_raises(monkeypatch):
    """A 5xx is not an absence signal: the lookup raises (after its retry)."""
    calls = _mock_transport_client(monkeypatch, lambda req: httpx.Response(500, json={"detail": "boom"}, request=req))
    client = AsyncAITBCHTTPClient(timeout=5.0, api_key=None, max_retries=1)

    with pytest.raises(NetworkError):
        asyncio.run(_lookup_escrow_record("http://node.invalid", client, "job-x"))
    assert len(calls) == 2  # GET is retried once at max_retries=1


def test_real_client_escrow_get_connect_error_raises(monkeypatch):
    """A transport failure raises — never read as "no lock"."""

    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    calls = _mock_transport_client(monkeypatch, refuse)
    client = AsyncAITBCHTTPClient(timeout=5.0, api_key=None, max_retries=1)

    with pytest.raises(NetworkError):
        asyncio.run(_lookup_escrow_record("http://node.invalid", client, "job-x"))
    assert len(calls) == 2


def test_real_client_escrow_get_unparseable_200_raises(monkeypatch):
    """A 200 with a non-JSON body raises — the error is post-response, so no retry."""
    calls = _mock_transport_client(monkeypatch, lambda req: httpx.Response(200, content=b"<html>oops</html>", request=req))
    client = AsyncAITBCHTTPClient(timeout=5.0, api_key=None, max_retries=1)

    with pytest.raises(ValueError):
        asyncio.run(_lookup_escrow_record("http://node.invalid", client, "job-x"))
    assert len(calls) == 1


def test_recover_adopts_locked_record_via_real_client(monkeypatch, payment_session):
    """End to end: POST outcome lost, GET finds the lock → adopted as escrowed."""
    job = _make_job(payment_session, "job-real-locked")
    payment = _make_payment(payment_session, job)
    calls = _mock_transport_client(
        monkeypatch,
        lambda req: httpx.Response(
            200,
            json={"contract_id": "0xescrowZ", "lock_tx_hash": "0xlock7", "state": "locked"},
            request=req,
        ),
    )

    escrow, absent = asyncio.run(PaymentService(payment_session)._recover_ambiguous_escrow(payment, BUYER, PROVIDER))

    assert absent is False
    assert escrow is not None
    assert payment.status == "escrowed"
    assert payment.escrow_address == "0xescrowZ"
    assert payment.meta_data["escrow_recovered"] is True
    assert len(calls) == 1


def test_recover_does_not_adopt_released_record(monkeypatch, payment_session):
    """A settled record is stale evidence — never adopted as this payment's escrow."""
    job = _make_job(payment_session, "job-real-released")
    payment = _make_payment(payment_session, job)
    _mock_transport_client(
        monkeypatch,
        lambda req: httpx.Response(
            200,
            json={
                "contract_id": "0xescrowR",
                "lock_tx_hash": "0xlock8",
                "state": "released",
                "released_at": "2026-10-03T20:00:00+00:00",
            },
            request=req,
        ),
    )

    escrow, absent = asyncio.run(PaymentService(payment_session)._recover_ambiguous_escrow(payment, BUYER, PROVIDER))

    assert escrow is None
    assert absent is False
    assert payment.status == "failed"
    assert payment.meta_data["escrow_error_kind"] == "funding_unknown"
    assert job.id in payment.meta_data["escrow_error"]
    assert "released" in payment.meta_data["escrow_error"]


def test_recover_does_not_adopt_refunded_record(monkeypatch, payment_session):
    """Same for a refunded record — settled either way is not ours to adopt."""
    job = _make_job(payment_session, "job-real-refunded")
    payment = _make_payment(payment_session, job)
    _mock_transport_client(
        monkeypatch,
        lambda req: httpx.Response(
            200,
            json={
                "contract_id": "0xescrowF",
                "lock_tx_hash": "0xlock9",
                "state": "refunded",
                "refunded_at": "2026-10-03T20:05:00+00:00",
            },
            request=req,
        ),
    )

    escrow, absent = asyncio.run(PaymentService(payment_session)._recover_ambiguous_escrow(payment, BUYER, PROVIDER))

    assert escrow is None
    assert absent is False
    assert payment.status == "failed"
    assert payment.meta_data["escrow_error_kind"] == "funding_unknown"
    assert "refunded" in payment.meta_data["escrow_error"]


def test_recover_settled_detail_names_timestamp_leg(monkeypatch, payment_session):
    """Settled by released_at alone (no state/status): the detail must name the leg, not 'None'."""
    job = _make_job(payment_session, "job-real-tsonly")
    payment = _make_payment(payment_session, job)
    _mock_transport_client(
        monkeypatch,
        lambda req: httpx.Response(
            200,
            json={
                "contract_id": "0xescrowT",
                "lock_tx_hash": "0xlockT",
                "released_at": "2026-10-03T20:00:00+00:00",
            },
            request=req,
        ),
    )

    escrow, absent = asyncio.run(PaymentService(payment_session)._recover_ambiguous_escrow(payment, BUYER, PROVIDER))

    assert escrow is None
    assert payment.status == "failed"
    assert payment.meta_data["escrow_error_kind"] == "funding_unknown"
    assert "None" not in payment.meta_data["escrow_error"]
    assert "released" in payment.meta_data["escrow_error"]


def test_recover_confirmed_absent_via_real_client(monkeypatch, payment_session):
    """404 on the record plus an empty chain list → absence confirmed, retry safe."""

    def handler(request: httpx.Request) -> httpx.Response:
        if "/rpc/escrow/" in request.url.path:
            return httpx.Response(404, json={"detail": "escrow not found"}, request=request)
        return httpx.Response(200, json=[], request=request)

    job = _make_job(payment_session, "job-real-absent")
    payment = _make_payment(payment_session, job)
    _mock_transport_client(monkeypatch, handler)

    escrow, absent = asyncio.run(PaymentService(payment_session)._recover_ambiguous_escrow(payment, BUYER, PROVIDER))

    assert escrow is None
    assert absent is True


def test_recover_marks_funding_unknown_via_real_client_bad_body(monkeypatch, payment_session):
    """A 200 the client cannot parse fails the lookup → funding_unknown, fast."""
    job = _make_job(payment_session, "job-real-unknown")
    payment = _make_payment(payment_session, job)
    calls = _mock_transport_client(monkeypatch, lambda req: httpx.Response(200, content=b"not-json", request=req))

    escrow, absent = asyncio.run(PaymentService(payment_session)._recover_ambiguous_escrow(payment, BUYER, PROVIDER))

    assert escrow is None
    assert absent is False
    assert payment.status == "failed"
    assert payment.meta_data["escrow_error_kind"] == "funding_unknown"
    assert job.id in payment.meta_data["escrow_error"]
    assert len(calls) == 1
