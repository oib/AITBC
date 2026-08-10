"""TEE-signed confidential transaction envelopes and balance proofs (v0.14.2 §A2).

Provides ``ConfidentialTransaction`` and ``ConfidentialWallet`` primitives. The
signature scheme uses Ed25519 with a 32-byte private key derived from the
caller-provided ``signing_key`` material via SHA-256. Amount commitments are
simulated Pedersen commitments on NIST256p using the ``ecdsa`` library; this is
a pedagogical stand-in for production range proofs / Bulletproofs.

Why ``ecdsa`` is still a dependency (V23-19)
--------------------------------------------
This module is the only consumer of ``ecdsa`` in the repository, and ``ecdsa`` 0.19.2
carries PYSEC-2026-1325 with **no upstream fix published** — the library is pure Python and
does not defend against timing side channels. The audit asked for either removal or a
written rationale. The rationale:

* Only the *curve arithmetic* is used — ``NIST256p`` point addition and scalar
  multiplication, for the commitment construction. ``cryptography`` deliberately exposes no
  raw point arithmetic, so it is not a drop-in replacement; swapping would mean hand-writing
  curve operations, which is worse than the advisory.
* The side channel needs a secret to leak. The blinding factor is the only secret here, and
  ``ConfidentialTransaction`` **carries it in the clear** (``blinding``) alongside the
  amount (``amount_label``) — see V23-19a. There is nothing for a timing attack to recover
  that is not already in the envelope.

That second point is the actual reason this is tolerable, and it is not a comfortable one:
the advisory is survivable because the construction provides no confidentiality to begin
with. **Removing ``ecdsa`` is the wrong first move; making these commitments real is, and
that removes ``ecdsa`` as a side effect** — a production Pedersen/Bulletproof implementation
would not be built on this library.
"""

from __future__ import annotations

import base64
import hashlib
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from ecdsa import NIST256p, SigningKey, VerifyingKey  # type: ignore[import-untyped]
from ecdsa.ellipticcurve import PointJacobi  # type: ignore[import-untyped]


_G = NIST256p.generator
_H = (
    SigningKey.from_string(
        hashlib.sha256(b"aitbc-pedersen-h").digest(),
        curve=NIST256p,
    )
    .get_verifying_key()
    .pubkey.point
)

# Sentinel bytes for the point at infinity.
_INFINITY_BYTES = b"\x00"


def _amount_scalar(amount: str) -> int:
    digest = hashlib.sha256(amount.encode("utf-8")).digest()
    return int.from_bytes(digest, "big") % NIST256p.order  # type: ignore[no-any-return]


def _blinding_scalar(blinding: bytes) -> int:
    return int.from_bytes(blinding, "big") % NIST256p.order  # type: ignore[no-any-return]


def _commit(amount: str, blinding: bytes) -> Any:
    """Return a Pedersen-style commitment point: v*G + r*H."""
    v = _amount_scalar(amount)
    r = _blinding_scalar(blinding)
    return _G * v + _H * r


def _is_infinity(point: Any) -> bool:
    return point.x() is None or point.y() is None


def _encode(point: Any) -> bytes:
    """Encode a commitment point to compressed bytes, reducing coords into [0, p)."""
    if isinstance(point, PointJacobi):
        point = point.to_affine()
    if _is_infinity(point):
        return _INFINITY_BYTES
    curve = NIST256p.curve
    mod = curve.p()
    x, y = point.x(), point.y()
    if y < 0 or y >= mod:
        from ecdsa.ellipticcurve import Point as _Point

        point = _Point(curve, x, y % mod)
    return VerifyingKey.from_public_point(point, curve=NIST256p).to_string("compressed")  # type: ignore[no-any-return]


def _decode(data: bytes) -> Any:
    if data == _INFINITY_BYTES or not data:
        return _G * 0
    return VerifyingKey.from_string(data, curve=NIST256p).pubkey.point


def add_commitments(a: bytes, b: bytes) -> bytes:
    """Return the homomorphic sum of two commitment points."""
    return _encode(_decode(a) + _decode(b))


def subtract_commitments(a: bytes, b: bytes) -> bytes:
    """Return the homomorphic difference of two commitment points."""
    return _encode(_decode(a) + (_decode(b) * -1))


def verify_commitment(commitment: bytes, amount: str, blinding: bytes) -> bool:
    """Return True if ``commitment`` opens to ``amount`` and ``blinding``."""
    try:
        expected = _encode(_commit(amount, blinding))
        return expected == commitment
    except Exception:
        return False


@dataclass
class ConfidentialTransaction:
    """A TEE-signed confidential transaction envelope."""

    tx_id: str
    sender_id: str
    recipient_id: str
    amount_commitment: bytes = b""
    amount_label: str = ""
    blinding: bytes = b""
    signature: bytes = b""
    public_key: bytes = b""
    nonce: int = 0
    meta: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def _signing_payload(self) -> bytes:
        return (
            self.tx_id.encode("utf-8")
            + b":"
            + self.sender_id.encode("utf-8")
            + b":"
            + self.recipient_id.encode("utf-8")
            + b":"
            + base64.b64encode(self.amount_commitment)
            + b":"
            + self.amount_label.encode("utf-8")
            + b":"
            + str(self.nonce).encode("utf-8")
        )

    def _derive_private_key(self, signing_key: bytes) -> Ed25519PrivateKey:
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
        """Verify the Ed25519 signature."""
        key_bytes = public_key if public_key is not None else self.public_key
        if not self.signature or not key_bytes:
            return False
        try:
            pub = Ed25519PublicKey.from_public_bytes(key_bytes)
            pub.verify(self.signature, self._signing_payload())
            return True
        except (InvalidSignature, TypeError):
            return False

    def verify_commitment(self) -> bool:
        """Verify that ``amount_commitment`` opens to ``amount_label`` and ``blinding``."""
        return verify_commitment(self.amount_commitment, self.amount_label, self.blinding)


@dataclass
class ConfidentialWallet:
    """Wallet that tracks confidential balances using Pedersen commitments."""

    wallet_id: str
    owner_id: str
    balance_commitment: bytes = b""
    transactions: list[ConfidentialTransaction] = field(default_factory=list)

    def deposit(self, amount: str) -> None:
        """Add a confidential deposit commitment to the balance."""
        blinding = os.urandom(32)
        commitment = _encode(_commit(amount, blinding))
        self.balance_commitment = add_commitments(self.balance_commitment, commitment)

    def send(
        self,
        recipient_id: str,
        amount: str,
        signing_key: bytes,
    ) -> ConfidentialTransaction:
        """Create and sign a confidential transfer."""
        blinding = os.urandom(32)
        commitment = _encode(_commit(amount, blinding))
        tx = ConfidentialTransaction(
            tx_id=f"ctx-{len(self.transactions)}",
            sender_id=self.owner_id,
            recipient_id=recipient_id,
            amount_commitment=commitment,
            amount_label=amount,
            blinding=blinding,
            nonce=len(self.transactions),
        )
        tx.sign(signing_key)
        self.transactions.append(tx)
        self.balance_commitment = subtract_commitments(self.balance_commitment, commitment)
        return tx

    def balance_proof(self) -> dict[str, Any]:
        """Return a balance proof suitable for TEE attestation."""
        return {
            "wallet_id": self.wallet_id,
            "owner_id": self.owner_id,
            "balance_commitment": self.balance_commitment.hex() if self.balance_commitment else "",
            "tx_count": len(self.transactions),
        }
