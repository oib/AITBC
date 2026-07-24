"""TEE-signed confidential transaction envelopes and balance proofs (v0.14.2 §A2).

ponytail: This is a skeleton. Real confidential transactions need range proofs,
commitments, and a TEE signature scheme.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class ConfidentialTransaction:
    """A TEE-signed confidential transaction envelope."""

    tx_id: str
    sender_id: str
    recipient_id: str
    amount_commitment: str
    signature: bytes = b""
    nonce: int = 0
    meta: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def sign(self, signing_key: bytes) -> None:
        """Sign the transaction envelope with a TEE-derived key."""
        payload = f"{self.tx_id}:{self.sender_id}:{self.recipient_id}:{self.amount_commitment}:{self.nonce}".encode()
        # ponytail: replace with real TEE signing (ECDSA/Ed25519 inside the enclave).
        self.signature = signing_key + b":" + payload[:32]

    def verify(self, public_key: bytes) -> bool:
        """Verify the TEE signature against a public key."""
        if not self.signature or b":" not in self.signature:
            return False
        return self.signature.startswith(public_key)


@dataclass
class ConfidentialWallet:
    """Wallet that tracks confidential balances using commitments."""

    wallet_id: str
    owner_id: str
    balance_commitment: str = "0"
    transactions: list[ConfidentialTransaction] = field(default_factory=list)

    def deposit(self, amount_commitment: str) -> None:
        """Add a confidential deposit commitment to the balance."""
        self.balance_commitment = f"{self.balance_commitment}+{amount_commitment}"

    def send(
        self,
        recipient_id: str,
        amount_commitment: str,
        signing_key: bytes,
    ) -> ConfidentialTransaction:
        """Create and sign a confidential transfer."""
        tx = ConfidentialTransaction(
            tx_id=f"ctx-{len(self.transactions)}",
            sender_id=self.owner_id,
            recipient_id=recipient_id,
            amount_commitment=amount_commitment,
            nonce=len(self.transactions),
        )
        tx.sign(signing_key)
        self.transactions.append(tx)
        self.balance_commitment = f"{self.balance_commitment}-{amount_commitment}"
        return tx

    def balance_proof(self) -> dict[str, Any]:
        """Return a balance proof suitable for TEE attestation."""
        return {
            "wallet_id": self.wallet_id,
            "owner_id": self.owner_id,
            "balance_commitment": self.balance_commitment,
            "tx_count": len(self.transactions),
        }
