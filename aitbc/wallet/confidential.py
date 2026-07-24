"""TEE-signed confidential transaction envelopes and balance proofs (v0.14.2 §A2).

Provides ``ConfidentialTransaction`` and ``ConfidentialWallet`` primitives. The
signature scheme uses Ed25519 with a 32-byte private key derived from the
caller-provided ``signing_key`` material via SHA-256. Production deployments
should generate keys inside the TEE and never expose the private key outside
the enclave boundary.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)


@dataclass
class ConfidentialTransaction:
    """A TEE-signed confidential transaction envelope."""

    tx_id: str
    sender_id: str
    recipient_id: str
    amount_commitment: str
    signature: bytes = b""
    public_key: bytes = b""
    nonce: int = 0
    meta: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def _signing_payload(self) -> bytes:
        return (f"{self.tx_id}:{self.sender_id}:{self.recipient_id}:{self.amount_commitment}:{self.nonce}").encode()

    def _derive_private_key(self, signing_key: bytes) -> Ed25519PrivateKey:
        # ponytail: derive a deterministic 32-byte Ed25519 seed from the caller's key.
        # Production should use a key generated and held inside the TEE.
        seed = hashlib.sha256(signing_key).digest()
        return Ed25519PrivateKey.from_private_bytes(seed)

    def sign(self, signing_key: bytes) -> None:
        """Sign the transaction envelope with a TEE-derived key."""
        private_key = self._derive_private_key(signing_key)
        self.public_key = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        self.signature = private_key.sign(self._signing_payload())

    def verify(self, public_key: bytes | None = None) -> bool:
        """Verify the TEE signature against a public key.

        If ``public_key`` is not provided, the public key stored on the
        transaction is used.
        """
        key_bytes = public_key if public_key is not None else self.public_key
        if not self.signature or not key_bytes:
            return False
        try:
            pub = Ed25519PublicKey.from_public_bytes(key_bytes)
            pub.verify(self.signature, self._signing_payload())
            return True
        except InvalidSignature:
            return False


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
