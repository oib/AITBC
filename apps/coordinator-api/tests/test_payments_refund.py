"""
Regression tests for PaymentService refund idempotency.
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest
from sqlmodel import Session, select

from coordinator_api.contexts.infrastructure.domain.job import Job
from coordinator_api.contexts.payments.services.payments import PaymentService


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

    @patch("coordinator_api.contexts.payments.services.payments.AITBCHTTPClient")
    def test_refund_records_already_refunded_escrow(self, mock_client_cls, payment_session):
        """If the blockchain escrow is already refunded, record it without resubmitting."""
        job_id = "job-refund-1"
        payment_id = "pay-refund-1"
        _make_job_and_payment(payment_session, job_id, payment_id)

        mock_client = MagicMock()
        mock_client.get.return_value = {
            "state": "refunded",
            "refund_tx_hash": "0xalreadyrefunded",
        }
        mock_client.post.return_value = {}  # Should not be called
        mock_client_cls.return_value = mock_client

        service = PaymentService(payment_session)
        result = asyncio.run(service.refund_payment("client-1", job_id, payment_id, "test"))
        assert result is True

        mock_client.get.assert_called_once_with("http://localhost:8202/rpc/escrow/job-refund-1")
        mock_client.post.assert_not_called()

        from aitbc_shared import JobPayment, PaymentEscrow

        payment = payment_session.get(JobPayment, payment_id)
        assert payment.status == "refunded"
        assert payment.refund_transaction_hash == "0xalreadyrefunded"

        escrow = payment_session.exec(select(PaymentEscrow).where(PaymentEscrow.payment_id == payment_id)).one()
        assert escrow.is_refunded is True

    @patch("coordinator_api.contexts.payments.services.payments.AITBCHTTPClient")
    def test_refund_calls_blockchain_and_records_tx_hash(self, mock_client_cls, payment_session):
        """If the escrow is still funded, call the blockchain refund endpoint and record the tx hash."""
        job_id = "job-refund-2"
        payment_id = "pay-refund-2"
        _make_job_and_payment(payment_session, job_id, payment_id)

        mock_client = MagicMock()
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

    @patch("coordinator_api.contexts.payments.services.payments.AITBCHTTPClient")
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
