"""
Regression tests for PaymentService refund idempotency.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from sqlmodel import Session, select

from aitbc.exceptions import NetworkError

from coordinator_api.contexts.infrastructure.domain.job import Job
from coordinator_api.contexts.infrastructure.services.jobs import JobService
from coordinator_api.contexts.payments.services.payments import PaymentService
from coordinator_api.schemas import JobCreate, JobPaymentCreate


@pytest.fixture
def payment_session(db_engine) -> Session:
    with Session(db_engine) as session:
        yield session


def _make_job_and_payment(session: Session, job_id: str, payment_id: str) -> None:
    """Create a job, payment and escrow row in the test DB."""
    from aitbc_shared import JobPayment, PaymentEscrow

    client_id = "client-1"
    job = Job(
        id=job_id,
        client_id=client_id,
        state="COMPLETED",
        payload={},
        payment_id=payment_id,
        payment_status="escrowed",
        error="TEE attestation required before escrow release",
    )
    payment = JobPayment(
        id=payment_id,
        job_id=job_id,
        client_id=client_id,
        amount=5,
        currency="AITBC",
        status="escrowed",
        payment_method="aitbc_token",
        escrow_address="escrow_abc123",
    )
    escrow = PaymentEscrow(
        payment_id=payment_id,
        amount=5,
        currency="AITBC",
        address="escrow_address_for_payment",
        is_active=True,
        is_released=False,
        is_refunded=False,
    )
    session.add(job)
    session.add(payment)
    session.add(escrow)
    session.commit()


@pytest.mark.unit
class TestPaymentServiceRefund:
    """PaymentService.refund_payment idempotency and full-cycle behavior."""

    @patch("coordinator_api.contexts.payments.services.payments.AsyncAITBCHTTPClient")
    def test_refund_records_already_refunded_escrow(self, mock_client_cls, payment_session):
        """If the blockchain escrow is already refunded, record the real on-chain hash."""
        job_id = "job-refund-1"
        payment_id = "pay-refund-1"
        _make_job_and_payment(payment_session, job_id, payment_id)

        mock_client = AsyncMock()
        # The node reports the escrow as refunded with a stale local hash, but the
        # on-chain transaction lookup returns the authoritative real hash.
        mock_client.get.side_effect = [
            {"state": "refunded", "refund_tx_hash": "0xstalelocal"},
            [
                {
                    "tx_hash": "0xrealrefundtx",
                    "payload": {"job_id": job_id, "action": "escrow_refund"},
                }
            ],
        ]
        mock_client.post.return_value = {}  # Should not be called
        mock_client_cls.return_value = mock_client

        service = PaymentService(payment_session)
        result = asyncio.run(service.refund_payment("client-1", job_id, payment_id, "test"))
        assert result is True

        assert mock_client.get.call_count == 2
        mock_client.get.assert_any_call("http://localhost:8202/rpc/escrow/job-refund-1")
        mock_client.get.assert_any_call(
            "http://localhost:8202/transactions?transaction_type=ESCROW_REFUND&job_id=job-refund-1&limit=10"
        )
        mock_client.post.assert_not_called()

        from aitbc_shared import JobPayment, PaymentEscrow

        payment = payment_session.get(JobPayment, payment_id)
        assert payment.status == "refunded"
        assert payment.refund_transaction_hash == "0xrealrefundtx"

        escrow = payment_session.exec(select(PaymentEscrow).where(PaymentEscrow.payment_id == payment_id)).one()
        assert escrow.is_refunded is True

    @patch("coordinator_api.contexts.payments.services.payments.AsyncAITBCHTTPClient")
    def test_refund_calls_blockchain_and_records_tx_hash(self, mock_client_cls, payment_session):
        """If the escrow is still funded, call the blockchain refund endpoint and record the tx hash."""
        job_id = "job-refund-2"
        payment_id = "pay-refund-2"
        _make_job_and_payment(payment_session, job_id, payment_id)

        mock_client = AsyncMock()
        mock_client.get.return_value = {"state": "funded"}
        mock_client.post.return_value = {
            "success": True,
            "refund_tx_hash": "0xnewrefundtx",
        }
        mock_client_cls.return_value = mock_client

        service = PaymentService(payment_session)
        result = asyncio.run(service.refund_payment("client-1", job_id, payment_id, "test"))
        assert result is True

        mock_client.get.assert_called_once_with("http://localhost:8202/rpc/escrow/job-refund-2")
        mock_client.post.assert_called_once_with(
            "http://localhost:8202/rpc/escrow/job-refund-2/refund",
            json={"reason": "test"},
        )

        from aitbc_shared import JobPayment

        payment = payment_session.get(JobPayment, payment_id)
        assert payment.status == "refunded"
        assert payment.refund_transaction_hash == "0xnewrefundtx"

    @patch("coordinator_api.contexts.payments.services.payments.AsyncAITBCHTTPClient")
    def test_refund_fails_when_payment_not_escrowed(self, mock_client_cls, payment_session):
        """Refund returns False when the payment is not in an escrowed/pending state."""
        job_id = "job-refund-3"
        payment_id = "pay-refund-3"
        _make_job_and_payment(payment_session, job_id, payment_id)

        from aitbc_shared import JobPayment

        payment = payment_session.get(JobPayment, payment_id)
        payment.status = "released"
        payment_session.commit()

        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        service = PaymentService(payment_session)
        result = asyncio.run(service.refund_payment("client-1", job_id, payment_id, "test"))
        assert result is False
        mock_client.get.assert_not_called()

    @patch("coordinator_api.contexts.payments.services.payments.AsyncAITBCHTTPClient")
    def test_refund_reconciles_stale_local_hash(self, mock_client_cls, payment_session):
        """A stale local refund_tx_hash is ignored and a real on-chain tx is submitted."""
        job_id = "job-refund-stale"
        payment_id = "pay-refund-stale"
        _make_job_and_payment(payment_session, job_id, payment_id)

        mock_client = AsyncMock()
        # Escrow row says refunded with a stale local hash, but the chain has no
        # ESCROW_REFUND yet, so the node should resubmit and return the real hash.
        mock_client.get.side_effect = [
            {"state": "refunded", "refund_tx_hash": "0xstalelocalhash"},
            [],  # no on-chain ESCROW_REFUND yet
        ]
        mock_client.post.return_value = {
            "success": True,
            "refund_tx_hash": "0xrealonchainrefund",
        }
        mock_client_cls.return_value = mock_client

        service = PaymentService(payment_session)
        result = asyncio.run(service.refund_payment("client-1", job_id, payment_id, "test"))
        assert result is True

        from aitbc_shared import JobPayment

        payment = payment_session.get(JobPayment, payment_id)
        assert payment.status == "refunded"
        assert payment.refund_transaction_hash == "0xrealonchainrefund"

    @patch("coordinator_api.contexts.payments.services.payments.AsyncAITBCHTTPClient")
    def test_refund_unbacked_escrow_guard(self, mock_client_cls, payment_session):
        """A payment row with no on-chain lock tx is marked refunded on a 404 lookup."""
        job_id = "job-refund-unbacked"
        payment_id = "pay-refund-unbacked"
        _make_job_and_payment(payment_session, job_id, payment_id)

        from aitbc_shared import JobPayment

        payment = payment_session.get(JobPayment, payment_id)
        payment.transaction_hash = None
        payment_session.commit()

        request = httpx.Request("GET", f"http://localhost:8202/rpc/escrow/{job_id}")
        response = httpx.Response(404, request=request)
        cause = httpx.HTTPStatusError("Not found", request=request, response=response)
        exc = NetworkError("GET request failed")
        exc.__cause__ = cause

        mock_client = AsyncMock()
        # First GET for /rpc/escrow/{job_id} 404s; second GET for ESCROW_LOCK returns none.
        mock_client.get.side_effect = [exc, []]
        mock_client_cls.return_value = mock_client

        service = PaymentService(payment_session)
        result = asyncio.run(service.refund_payment("client-1", job_id, payment_id, "test"))
        assert result is True

        assert mock_client.get.call_count == 2
        mock_client.get.assert_any_call(f"http://localhost:8202/rpc/escrow/{job_id}")
        mock_client.get.assert_any_call(
            f"http://localhost:8202/transactions?transaction_type=ESCROW_LOCK&job_id={job_id}&limit=10"
        )
        mock_client.post.assert_not_called()
        refreshed = payment_session.get(JobPayment, payment_id)
        assert refreshed.status == "refunded"
        assert refreshed.refund_transaction_hash is None


@pytest.mark.unit
class TestPaymentCreation:
    """PaymentService.create_payment should keep the job row in step with the payment."""

    @pytest.mark.asyncio
    async def test_create_payment_backfills_job_amount_and_token(self, payment_session):
        """A job created without payment_amount gets the actual payment amount/token."""
        job_service = JobService(payment_session)
        job = job_service.create_job(
            "client-1",
            JobCreate(payload={"type": "inference", "prompt": "test prompt"}, ttl_seconds=900),
        )
        assert job.payment_amount is None
        assert job.payment_token is None

        payment_data = JobPaymentCreate(
            job_id=job.id,
            amount=Decimal("1.5"),
            currency="AITBC",
            payment_method="aitbc_token",
        )
        service = PaymentService(payment_session)
        # Skip the on-chain ESCROW_LOCK; we only care about the job row update.
        service._create_token_escrow = AsyncMock(return_value=None)
        payment = await service.create_payment("client-1", job.id, payment_data)

        refreshed = payment_session.get(Job, job.id)
        assert refreshed is not None
        assert refreshed.payment_id == payment.id
        assert refreshed.payment_status == payment.status
        assert refreshed.payment_amount == Decimal("1.5")
        assert refreshed.payment_token == "AITBC"
