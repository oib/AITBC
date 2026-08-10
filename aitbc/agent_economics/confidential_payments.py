"""Enclave-side confidential payment validation (v0.14.2 §A2).

Provides ``ConfidentialPayment`` and helpers to validate and settle confidential payments.
Validation checks sender/recipient, that the payment's commitment matches the transaction's,
and the Ed25519 signature over the envelope.

What validation does *not* establish (V23-19a)
----------------------------------------------
It does not establish anything about the amount. This function used to call
``tx.verify_commitment()`` and raise ``TEEError("confidential transaction commitment is
invalid")`` on failure, which read as a cryptographic check inside a trust boundary. It was
not one: the amount and the blinding factor were stored in the envelope next to the
commitment, so the check recomputed a value from its own inputs and could only fail if the
sender had corrupted its own data.

The envelope no longer carries the opening, so that check is now impossible rather than
vacuous, and it has been removed rather than replaced with something that looks like it.
Callers that hold the opening out of band can pass it as ``opening`` and it will be checked;
callers that do not get a signature check and no amount guarantee, which is the truth.

Even with an opening, there is no range proof — see ``aitbc.wallet.confidential``. A verifier
cannot conclude from a valid opening that the transfer created no value.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from aitbc.tee.errors import TEEError
from aitbc.wallet.confidential import ConfidentialTransaction, Opening


@dataclass
class ConfidentialPayment:
    """A validated confidential payment request."""

    payment_id: str
    sender_id: str
    recipient_id: str
    amount_commitment: bytes = b""
    tx: ConfidentialTransaction | None = None
    validated: bool = False


def validate_payment(
    payment: ConfidentialPayment,
    expected_sender: str = "",
    opening: Opening | None = None,
) -> bool:
    """Validate a confidential payment's parties and signature inside the TEE trust boundary.

    Establishes that the envelope was signed by the key it carries and that the payment refers
    to the transaction's commitment. It establishes **nothing about the amount** unless
    ``opening`` is supplied out of band, and even then no range guarantee — see the module
    docstring.
    """
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
    if opening is not None and not opening.opens(payment.amount_commitment):
        raise TEEError("supplied opening does not match the payment commitment")
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
