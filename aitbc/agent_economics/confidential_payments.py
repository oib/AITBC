"""Enclave-side confidential payment validation (v0.14.2 §A2).

Provides ``ConfidentialPayment`` and helpers to validate and settle confidential
payments. Validation checks sender/recipient, commitment consistency, transaction
signature, and that the amount commitment opens to the stored label/blinding.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from aitbc.tee.errors import TEEError
from aitbc.wallet.confidential import ConfidentialTransaction


@dataclass
class ConfidentialPayment:
    """A validated confidential payment request."""

    payment_id: str
    sender_id: str
    recipient_id: str
    amount_commitment: bytes = b""
    tx: ConfidentialTransaction | None = None
    validated: bool = False


def validate_payment(payment: ConfidentialPayment, expected_sender: str = "") -> bool:
    """Validate a confidential payment inside the TEE trust boundary."""
    if not payment.sender_id or not payment.recipient_id:
        raise TEEError("payment must specify sender and recipient")
    if not payment.amount_commitment:
        raise TEEError("payment amount commitment cannot be empty")
    if expected_sender and payment.sender_id != expected_sender:
        raise TEEError("sender does not match expected sender")
    if payment.tx is None:
        raise TEEError("payment must include a signed confidential transaction")
    if payment.tx.amount_commitment != payment.amount_commitment:
        raise TEEError("payment commitment does not match transaction commitment")
    if not payment.tx.signature:
        raise TEEError("confidential transaction is not signed")
    if not payment.tx.verify():
        raise TEEError("confidential transaction signature is invalid")
    if not payment.tx.verify_commitment():
        raise TEEError("confidential transaction commitment is invalid")
    payment.validated = True
    return True


def settle_payment(payment: ConfidentialPayment) -> dict[str, Any]:
    """Mark a validated payment as settled and return a receipt."""
    if not payment.validated:
        raise TEEError("payment must be validated before settlement")
    return {
        "payment_id": payment.payment_id,
        "sender_id": payment.sender_id,
        "recipient_id": payment.recipient_id,
        "amount_commitment": payment.amount_commitment,
        "settled": True,
    }
