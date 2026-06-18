"""Payment service for job payments"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session
from sqlmodel import select

from aitbc.aitbc_logging import get_logger
from aitbc.exceptions import NetworkError
from aitbc.network import AITBCHTTPClient

from ....schemas import JobPaymentCreate, JobPaymentView
from ....storage import get_session
from ..domain.payment import JobPayment, PaymentEscrow

logger = get_logger(__name__)


class PaymentService:
    """Service for handling job payments"""

    def __init__(self, session: Annotated[Session, Depends(get_session)]):
        self.session = session
        self.wallet_base_url = "http://127.0.0.1:20000"
        self.exchange_base_url = "http://127.0.0.1:8106"

    async def create_payment(self, job_id: str, payment_data: JobPaymentCreate) -> JobPayment:
        """Create a new payment for a job with ACID compliance"""
        try:
            payment = JobPayment(
                job_id=job_id,
                amount=payment_data.amount,
                currency=payment_data.currency,
                payment_method=payment_data.payment_method,
                expires_at=datetime.now(UTC) + timedelta(seconds=payment_data.escrow_timeout_seconds),
            )
            self.session.add(payment)
            if payment_data.payment_method == "aitbc_token":
                try:
                    escrow = await self._create_token_escrow(payment)
                    if escrow is not None:
                        self.session.add(escrow)
                except Exception as e:
                    logger.warning("Token escrow not available, skipping payment: %s", e)
                    payment.status = "skipped"
            elif payment_data.payment_method == "bitcoin":
                escrow = await self._create_bitcoin_escrow(payment)
                if escrow is not None:
                    self.session.add(escrow)
            self.session.commit()
            self.session.refresh(payment)
            logger.info("Payment created successfully: %s", payment.id)
            return payment
        except Exception as e:
            self.session.rollback()
            logger.error("Failed to create payment: %s", e)
            raise

    async def _create_token_escrow(self, payment: JobPayment) -> PaymentEscrow | None:
        """Create an escrow for AITBC token payments"""
        try:
            client = AITBCHTTPClient(timeout=10.0)
            response = client.post(
                f"{self.exchange_base_url}/api/v1/token/escrow/create",
                json={
                    "amount": float(payment.amount),
                    "currency": payment.currency,
                    "job_id": payment.job_id,
                    "timeout_seconds": 3600,
                },
            )
            escrow_data = response
            payment.escrow_address = escrow_data.get("escrow_id")
            payment.status = "escrowed"
            payment.escrowed_at = datetime.now(UTC)
            payment.updated_at = datetime.now(UTC)
            escrow = PaymentEscrow(
                payment_id=payment.id,
                amount=payment.amount,
                currency=payment.currency,
                address=escrow_data.get("escrow_id"),
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
            if escrow is not None:
                self.session.add(escrow)
            self.session.commit()
            logger.info("Created AITBC token escrow for payment %s", payment.id)
            return escrow
        except NetworkError as e:
            logger.warning("Token escrow endpoint not available: %s", e)
            return None
        except Exception as e:
            logger.warning("Token escrow creation failed: %s", e)
            return None

    async def _create_bitcoin_escrow(self, payment: JobPayment) -> PaymentEscrow | None:
        """Create an escrow for Bitcoin payments (exchange only)"""
        try:
            client = AITBCHTTPClient(timeout=30.0)
            try:
                escrow_data = client.post(
                    f"{self.wallet_base_url}/api/v1/escrow/create",
                    json={"amount": float(payment.amount), "currency": payment.currency, "timeout_seconds": 3600},
                )
                payment.escrow_address = escrow_data["address"]
                payment.status = "escrowed"
                payment.escrowed_at = datetime.now(UTC)
                payment.updated_at = datetime.now(UTC)
                escrow = PaymentEscrow(
                    payment_id=payment.id,
                    amount=payment.amount,
                    currency=payment.currency,
                    address=escrow_data["address"],
                    expires_at=datetime.now(UTC) + timedelta(hours=1),
                )
                if escrow is not None:
                    self.session.add(escrow)
                self.session.commit()
                logger.info("Created Bitcoin escrow for payment %s", payment.id)
                return escrow
            except NetworkError as e:
                logger.error("Failed to create Bitcoin escrow: %s", e)
                payment.status = "failed"
                payment.updated_at = datetime.now(UTC)
                self.session.commit()
                return None
        except Exception as e:
            logger.error("Error creating Bitcoin escrow: %s", e)
            payment.status = "failed"
            payment.updated_at = datetime.now(UTC)
            self.session.commit()
            return None

    async def release_payment(self, job_id: str, payment_id: str, reason: str | None = None) -> bool:
        """Release payment from escrow to miner"""
        payment = self.session.get(JobPayment, payment_id)
        if not payment or payment.job_id != job_id:
            return False
        if payment.status != "escrowed":
            return False
        try:
            client = AITBCHTTPClient(timeout=30.0)
            try:
                release_data = client.post(
                    f"{self.wallet_base_url}/api/v1/escrow/release",
                    json={"address": payment.escrow_address, "reason": reason or "Job completed successfully"},
                )
                payment.status = "released"
                payment.released_at = datetime.now(UTC)
                payment.updated_at = datetime.now(UTC)
                payment.transaction_hash = release_data.get("transaction_hash")
                escrow = (
                    self.session.execute(select(PaymentEscrow).where(PaymentEscrow.payment_id == payment_id)).scalars().first()
                )
                if escrow:
                    escrow.is_released = True
                    escrow.released_at = datetime.now(UTC)
                self.session.commit()
                logger.info("Released payment %s for job %s", payment_id, job_id)
                return True
            except NetworkError as e:
                logger.error("Failed to release payment: %s", e)
                return False
        except Exception as e:
            logger.error("Error releasing payment: %s", e)
            return False

    async def refund_payment(self, job_id: str, payment_id: str, reason: str) -> bool:
        """Refund payment to client"""
        payment = self.session.get(JobPayment, payment_id)
        if not payment or payment.job_id != job_id:
            return False
        if payment.status not in ["escrowed", "pending"]:
            return False
        try:
            client = AITBCHTTPClient(timeout=30.0)
            try:
                refund_data = client.post(
                    f"{self.wallet_base_url}/api/v1/refund",
                    json={
                        "payment_id": payment_id,
                        "address": payment.refund_address,
                        "amount": float(payment.amount),
                        "reason": reason,
                    },
                )
                payment.status = "refunded"
                payment.refunded_at = datetime.now(UTC)
                payment.updated_at = datetime.now(UTC)
                payment.refund_transaction_hash = refund_data.get("transaction_hash")
                escrow = (
                    self.session.execute(select(PaymentEscrow).where(PaymentEscrow.payment_id == payment_id)).scalars().first()
                )
                if escrow:
                    escrow.is_refunded = True
                    escrow.refunded_at = datetime.now(UTC)
                self.session.commit()
                logger.info("Refunded payment %s for job %s", payment_id, job_id)
                return True
            except NetworkError as e:
                logger.error("Failed to refund payment: %s", e)
                return False
        except Exception as e:
            logger.error("Error refunding payment: %s", e)
            return False

    def get_payment(self, payment_id: str) -> JobPayment | None:
        """Get payment by ID"""
        return self.session.get(JobPayment, payment_id)

    def get_job_payment(self, job_id: str) -> JobPayment | None:
        """Get payment for a specific job"""
        return self.session.execute(select(JobPayment).where(JobPayment.job_id == job_id)).scalars().first()

    def to_view(self, payment: JobPayment) -> JobPaymentView:
        """Convert payment to view model"""
        return JobPaymentView(
            job_id=payment.job_id,
            payment_id=payment.id,
            amount=float(payment.amount),
            currency=payment.currency,
            status=payment.status,
            payment_method=payment.payment_method,
            escrow_address=payment.escrow_address,
            refund_address=payment.refund_address,
            created_at=payment.created_at,
            updated_at=payment.updated_at,
            released_at=payment.released_at,
            refunded_at=payment.refunded_at,
            transaction_hash=payment.transaction_hash,
            refund_transaction_hash=payment.refund_transaction_hash,
        )
