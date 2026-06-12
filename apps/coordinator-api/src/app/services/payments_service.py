"""
Payments Service - Payment processing and escrow management

Provides:
- Payment intent creation
- Escrow for marketplace transactions
- Multi-currency support
- Payment confirmation
- Refund handling
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any
from aitbc.aitbc_logging import get_logger
logger = get_logger(__name__)

class PaymentStatus(Enum):
    """Payment status"""
    pending = 'pending'
    processing = 'processing'
    completed = 'completed'
    failed = 'failed'
    refunded = 'refunded'
    escrowed = 'escrowed'
    released = 'released'

class PaymentMethod(Enum):
    """Supported payment methods"""
    native_token = 'native_token'
    stablecoin = 'stablecoin'
    escrow = 'escrow'

@dataclass
class Payment:
    """Payment record"""
    id: str
    payer: str
    payee: str
    amount: int
    currency: str
    status: PaymentStatus
    method: PaymentMethod
    description: str
    metadata: dict[str, Any]
    created_at: datetime
    expires_at: datetime | None
    completed_at: datetime | None
    escrow_id: str | None
    escrow_released: bool
    tx_hash: str | None
    block_confirmation: int | None

    def to_dict(self) -> dict[str, Any]:
        return {'id': self.id, 'payer': self.payer, 'payee': self.payee, 'amount': self.amount, 'currency': self.currency, 'status': self.status.value, 'method': self.method.value, 'description': self.description, 'metadata': self.metadata, 'created_at': self.created_at.isoformat(), 'expires_at': self.expires_at.isoformat() if self.expires_at else None, 'completed_at': self.completed_at.isoformat() if self.completed_at else None, 'escrow': {'id': self.escrow_id, 'released': self.escrow_released} if self.escrow_id else None, 'transaction': {'hash': self.tx_hash, 'confirmations': self.block_confirmation} if self.tx_hash else None}

class PaymentsService:
    """
    Payment processing service.
    
    Handles:
    - Direct payments
    - Escrow-based payments
    - Multi-step payment flows
    - Refunds and cancellations
    """

    def __init__(self) -> None:
        self._payments: dict[str, Payment] = {}
        self._escrows: dict[str, dict[str, Any]] = {}
        self._payment_counter = 0

    def create_payment_intent(self, payer: str, payee: str, amount: int, currency: str='AITBC', method: str='native_token', description: str='', metadata: dict[str, Any] | None=None, escrow: bool=False, expires_in_hours: int=24) -> Payment:
        """
        Create a payment intent.
        
        Args:
            payer: Payer address
            payee: Payee address
            amount: Payment amount
            currency: Currency code
            method: Payment method
            description: Payment description
            metadata: Additional metadata
            escrow: Whether to hold in escrow
            expires_in_hours: Payment expiration time
        
        Returns:
            Created payment intent
        """
        self._payment_counter += 1
        payment_id = f'PAY-{self._payment_counter:06d}'
        try:
            pay_method = PaymentMethod(method)
        except ValueError:
            pay_method = PaymentMethod.native_token
        now = datetime.now(UTC)
        expires_at = now + timedelta(hours=expires_in_hours)
        escrow_id = None
        if escrow:
            escrow_id = f'ESC-{payment_id}'
            self._escrows[escrow_id] = {'payment_id': payment_id, 'amount': amount, 'payer': payer, 'payee': payee, 'status': 'held', 'created_at': now}
        payment = Payment(id=payment_id, payer=payer, payee=payee, amount=amount, currency=currency, status=PaymentStatus.pending, method=pay_method, description=description, metadata=metadata or {}, created_at=now, expires_at=expires_at, completed_at=None, escrow_id=escrow_id, escrow_released=False, tx_hash=None, block_confirmation=None)
        self._payments[payment_id] = payment
        logger.info('Payment intent created: %s for %s %s', payment_id, amount, currency)
        return payment

    def confirm_payment(self, payment_id: str, tx_hash: str, confirmations: int=1) -> Payment:
        """
        Confirm a payment with transaction hash.
        
        Args:
            payment_id: Payment to confirm
            tx_hash: Blockchain transaction hash
            confirmations: Number of block confirmations
        
        Returns:
            Updated payment
        """
        payment = self._payments.get(payment_id)
        if not payment:
            raise ValueError(f'Payment {payment_id} not found')
        if payment.status != PaymentStatus.pending:
            raise ValueError(f'Payment is not pending: {payment.status.value}')
        payment.tx_hash = tx_hash
        payment.block_confirmation = confirmations
        if payment.escrow_id:
            payment.status = PaymentStatus.escrowed
            self._escrows[payment.escrow_id]['status'] = 'held'
        else:
            payment.status = PaymentStatus.completed
            payment.completed_at = datetime.now(UTC)
        logger.info('Payment confirmed: %s with tx %s...', payment_id, tx_hash[:16])
        return payment

    def release_escrow(self, payment_id: str, releaser: str) -> Payment:
        """
        Release escrowed payment to payee.
        
        Args:
            payment_id: Payment to release
            releaser: Address releasing the escrow
        
        Returns:
            Updated payment
        """
        payment = self._payments.get(payment_id)
        if not payment:
            raise ValueError(f'Payment {payment_id} not found')
        if not payment.escrow_id:
            raise ValueError('Payment is not in escrow')
        if payment.status != PaymentStatus.escrowed:
            raise ValueError(f'Payment is not escrowed: {payment.status.value}')
        if releaser != payment.payer:
            raise ValueError('Only payer can release escrow')
        payment.status = PaymentStatus.released
        payment.escrow_released = True
        payment.completed_at = datetime.now(UTC)
        if payment.escrow_id in self._escrows:
            self._escrows[payment.escrow_id]['status'] = 'released'
        logger.info('Escrow released: %s to %s', payment_id, payment.payee)
        return payment

    def refund_payment(self, payment_id: str, reason: str='') -> Payment:
        """
        Refund a payment to payer.
        
        Args:
            payment_id: Payment to refund
            reason: Refund reason
        
        Returns:
            Updated payment
        """
        payment = self._payments.get(payment_id)
        if not payment:
            raise ValueError(f'Payment {payment_id} not found')
        if payment.status not in [PaymentStatus.pending, PaymentStatus.escrowed]:
            raise ValueError(f'Cannot refund payment with status: {payment.status.value}')
        payment.status = PaymentStatus.refunded
        payment.completed_at = datetime.now(UTC)
        payment.metadata['refund_reason'] = reason
        if payment.escrow_id and payment.escrow_id in self._escrows:
            self._escrows[payment.escrow_id]['status'] = 'refunded'
        logger.info('Payment refunded: %s - %s', payment_id, reason)
        return payment

    def get_payment(self, payment_id: str) -> Payment | None:
        """Get payment by ID"""
        return self._payments.get(payment_id)

    def list_payments(self, payer: str | None=None, payee: str | None=None, status: str | None=None) -> list[Payment]:
        """List payments with filters"""
        result = list(self._payments.values())
        if payer:
            result = [p for p in result if p.payer == payer]
        if payee:
            result = [p for p in result if p.payee == payee]
        if status:
            result = [p for p in result if p.status.value == status]
        result.sort(key=lambda p: p.created_at, reverse=True)
        return result

    def get_escrow(self, escrow_id: str) -> dict[str, Any] | None:
        """Get escrow details"""
        return self._escrows.get(escrow_id)

    def get_payment_stats(self) -> dict[str, Any]:
        """Get payment statistics"""
        payments = list(self._payments.values())
        total_volume = sum((p.amount for p in payments if p.status in [PaymentStatus.completed, PaymentStatus.released]))
        completed = len([p for p in payments if p.status == PaymentStatus.completed])
        pending = len([p for p in payments if p.status == PaymentStatus.pending])
        escrowed = len([p for p in payments if p.status == PaymentStatus.escrowed])
        refunded = len([p for p in payments if p.status == PaymentStatus.refunded])
        return {'total_payments': len(payments), 'total_volume': total_volume, 'by_status': {'completed': completed, 'pending': pending, 'escrowed': escrowed, 'refunded': refunded}, 'escrow_holdings': sum((e['amount'] for e in self._escrows.values() if e['status'] == 'held'))}
_payments_service: PaymentsService | None = None

def get_payments_service() -> PaymentsService:
    """Get global payments service"""
    global _payments_service
    if _payments_service is None:
        _payments_service = PaymentsService()
    return _payments_service