"""Payment service for job payments"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import httpx
import logging

from ..domain.payment import JobPayment, PaymentEscrow
from ..schemas.payments import (
    JobPaymentCreate, 
    JobPaymentView, 
    PaymentStatus,
    PaymentMethod,
    EscrowRelease,
    RefundRequest
)
from ..storage import SessionDep

logger = logging.getLogger(__name__)


class PaymentService:
    """Service for handling job payments"""
    
    def __init__(self, session: SessionDep):
        self.session = session
        self.wallet_base_url = "http://127.0.0.1:20000"  # Wallet daemon URL
        self.exchange_base_url = "http://127.0.0.1:23000"  # Exchange API URL
    
    async def create_payment(self, job_id: str, payment_data: JobPaymentCreate) -> JobPayment:
        """Create a new payment for a job"""
        
        # Create payment record
        payment = JobPayment(
            job_id=job_id,
            amount=payment_data.amount,
            currency=payment_data.currency,
            payment_method=payment_data.payment_method,
            expires_at=datetime.utcnow() + timedelta(seconds=payment_data.escrow_timeout_seconds)
        )
        
        self.session.add(payment)
        self.session.commit()
        self.session.refresh(payment)
        
        # For AITBC token payments, use token escrow
        if payment_data.payment_method == PaymentMethod.AITBC_TOKEN:
            await self._create_token_escrow(payment)
        # Bitcoin payments only for exchange purchases
        elif payment_data.payment_method == PaymentMethod.BITCOIN:
            await self._create_bitcoin_escrow(payment)
        
        return payment
    
    async def _create_token_escrow(self, payment: JobPayment) -> None:
        """Create an escrow for AITBC token payments"""
        try:
            # For AITBC tokens, we use the token contract escrow
            async with httpx.AsyncClient() as client:
                # Call exchange API to create token escrow
                response = await client.post(
                    f"{self.exchange_base_url}/api/v1/token/escrow/create",
                    json={
                        "amount": payment.amount,
                        "currency": payment.currency,
                        "job_id": payment.job_id,
                        "timeout_seconds": 3600  # 1 hour
                    }
                )
                
                if response.status_code == 200:
                    escrow_data = response.json()
                    payment.escrow_address = escrow_data.get("escrow_id")
                    payment.status = PaymentStatus.ESCROWED
                    payment.escrowed_at = datetime.utcnow()
                    payment.updated_at = datetime.utcnow()
                    
                    # Create escrow record
                    escrow = PaymentEscrow(
                        payment_id=payment.id,
                        amount=payment.amount,
                        currency=payment.currency,
                        address=escrow_data.get("escrow_id"),
                        expires_at=datetime.utcnow() + timedelta(hours=1)
                    )
                    self.session.add(escrow)
                    
                    self.session.commit()
                    logger.info(f"Created AITBC token escrow for payment {payment.id}")
                else:
                    logger.error(f"Failed to create token escrow: {response.text}")
                    
        except Exception as e:
            logger.error(f"Error creating token escrow: {e}")
            payment.status = PaymentStatus.FAILED
            payment.updated_at = datetime.utcnow()
            self.session.commit()
    
    async def _create_bitcoin_escrow(self, payment: JobPayment) -> None:
        """Create an escrow for Bitcoin payments (exchange only)"""
        try:
            async with httpx.AsyncClient() as client:
                # Call wallet daemon to create escrow
                response = await client.post(
                    f"{self.wallet_base_url}/api/v1/escrow/create",
                    json={
                        "amount": payment.amount,
                        "currency": payment.currency,
                        "timeout_seconds": 3600  # 1 hour
                    }
                )
                
                if response.status_code == 200:
                    escrow_data = response.json()
                    payment.escrow_address = escrow_data["address"]
                    payment.status = PaymentStatus.ESCROWED
                    payment.escrowed_at = datetime.utcnow()
                    payment.updated_at = datetime.utcnow()
                    
                    # Create escrow record
                    escrow = PaymentEscrow(
                        payment_id=payment.id,
                        amount=payment.amount,
                        currency=payment.currency,
                        address=escrow_data["address"],
                        expires_at=datetime.utcnow() + timedelta(hours=1)
                    )
                    self.session.add(escrow)
                    
                    self.session.commit()
                    logger.info(f"Created Bitcoin escrow for payment {payment.id}")
                else:
                    logger.error(f"Failed to create Bitcoin escrow: {response.text}")
                    
        except Exception as e:
            logger.error(f"Error creating Bitcoin escrow: {e}")
            payment.status = PaymentStatus.FAILED
            payment.updated_at = datetime.utcnow()
            self.session.commit()
    
    async def release_payment(self, job_id: str, payment_id: str, reason: Optional[str] = None) -> bool:
        """Release payment from escrow to miner"""
        
        payment = self.session.get(JobPayment, payment_id)
        if not payment or payment.job_id != job_id:
            return False
        
        if payment.status != PaymentStatus.ESCROWED:
            return False
        
        try:
            async with httpx.AsyncClient() as client:
                # Call wallet daemon to release escrow
                response = await client.post(
                    f"{self.wallet_base_url}/api/v1/escrow/release",
                    json={
                        "address": payment.escrow_address,
                        "reason": reason or "Job completed successfully"
                    }
                )
                
                if response.status_code == 200:
                    release_data = response.json()
                    payment.status = PaymentStatus.RELEASED
                    payment.released_at = datetime.utcnow()
                    payment.updated_at = datetime.utcnow()
                    payment.transaction_hash = release_data.get("transaction_hash")
                    
                    # Update escrow record
                    escrow = self.session.exec(
                        self.session.query(PaymentEscrow).where(
                            PaymentEscrow.payment_id == payment_id
                        )
                    ).first()
                    
                    if escrow:
                        escrow.is_released = True
                        escrow.released_at = datetime.utcnow()
                    
                    self.session.commit()
                    logger.info(f"Released payment {payment_id} for job {job_id}")
                    return True
                else:
                    logger.error(f"Failed to release payment: {response.text}")
                    return False
                    
        except Exception as e:
            logger.error(f"Error releasing payment: {e}")
            return False
    
    async def refund_payment(self, job_id: str, payment_id: str, reason: str) -> bool:
        """Refund payment to client"""
        
        payment = self.session.get(JobPayment, payment_id)
        if not payment or payment.job_id != job_id:
            return False
        
        if payment.status not in [PaymentStatus.ESCROWED, PaymentStatus.PENDING]:
            return False
        
        try:
            async with httpx.AsyncClient() as client:
                # Call wallet daemon to refund
                response = await client.post(
                    f"{self.wallet_base_url}/api/v1/refund",
                    json={
                        "payment_id": payment_id,
                        "address": payment.refund_address,
                        "amount": payment.amount,
                        "reason": reason
                    }
                )
                
                if response.status_code == 200:
                    refund_data = response.json()
                    payment.status = PaymentStatus.REFUNDED
                    payment.refunded_at = datetime.utcnow()
                    payment.updated_at = datetime.utcnow()
                    payment.refund_transaction_hash = refund_data.get("transaction_hash")
                    
                    # Update escrow record
                    escrow = self.session.exec(
                        self.session.query(PaymentEscrow).where(
                            PaymentEscrow.payment_id == payment_id
                        )
                    ).first()
                    
                    if escrow:
                        escrow.is_refunded = True
                        escrow.refunded_at = datetime.utcnow()
                    
                    self.session.commit()
                    logger.info(f"Refunded payment {payment_id} for job {job_id}")
                    return True
                else:
                    logger.error(f"Failed to refund payment: {response.text}")
                    return False
                    
        except Exception as e:
            logger.error(f"Error refunding payment: {e}")
            return False
    
    def get_payment(self, payment_id: str) -> Optional[JobPayment]:
        """Get payment by ID"""
        return self.session.get(JobPayment, payment_id)
    
    def get_job_payment(self, job_id: str) -> Optional[JobPayment]:
        """Get payment for a specific job"""
        return self.session.exec(
            self.session.query(JobPayment).where(JobPayment.job_id == job_id)
        ).first()
    
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
            refund_transaction_hash=payment.refund_transaction_hash
        )
