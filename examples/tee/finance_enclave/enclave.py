"""Reference finance (PCI/GLBA) TEE enclave for payment processing.

ponytail: This is a Python simulator. Production builds a minimal enclave binary
and runs it under a hardware TEE with attested key provisioning.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from aitbc.tee import Enclave, EnclaveConfig
from aitbc.tee.errors import TEEError


@dataclass
class PaymentCardToken:
    """A tokenized payment card handled inside the finance enclave."""

    token_id: str
    last_four: str
    bin_range: str
    encrypted_pan: bytes = b""


class FinanceEnclave:
    """Reference finance enclave for tokenizing payment instruments."""

    def __init__(self, enclave_id: str, image: str = "finance-enclave:latest") -> None:
        self.enclave = Enclave(config=EnclaveConfig(enclave_id=enclave_id, image=image))

    def start(self) -> None:
        """Build and launch the enclave."""
        self.enclave.build()
        self.enclave.launch()

    def tokenize(self, pan: str) -> PaymentCardToken:
        """Tokenize a PAN inside the enclave trust boundary."""
        if self.enclave.status.value != "running":
            raise TEEError("enclave is not running")
        if not pan or len(pan) < 13:
            raise TEEError("invalid PAN")
        if not pan.isdigit():
            raise TEEError("PAN must be numeric")
        return PaymentCardToken(
            token_id=f"tok-{pan[-6:]}",
            last_four=pan[-4:],
            bin_range=pan[:6],
            encrypted_pan=b"encrypted(" + pan.encode("utf-8") + b")",
        )

    def authorize(self, token: PaymentCardToken, amount: Decimal) -> dict[str, bool | str]:
        """Authorize a payment against a token."""
        if self.enclave.status.value != "running":
            raise TEEError("enclave is not running")
        if amount <= 0:
            raise TEEError("amount must be positive")
        return {
            "approved": True,
            "token_id": token.token_id,
            "amount": str(amount),
        }
