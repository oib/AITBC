"""TEE-signed confidential transaction envelopes and balance proofs (v0.14.2 §A2).

Provides ``ConfidentialTransaction`` and ``ConfidentialWallet``. Signatures are Ed25519 over
a 32-byte key derived from the caller-supplied ``signing_key`` via SHA-256. Amounts are hidden
behind Pedersen commitments ``v*G + r*H`` on NIST256p.

What was wrong before (V23-19a)
-------------------------------
The audit found that the envelope carried the amount and the blinding factor in the clear, so
``verify_commitment()`` only established that a sender's own three fields agreed. That was the
least of it. Three further defects, each demonstrated by
``tests/security/test_v2319a_pedersen.py``:

1. **The commitments were not binding.** ``H`` was built as
   ``SigningKey.from_string(sha256(b"aitbc-pedersen-h")).get_verifying_key().point``, which is
   ``h*G`` for ``h = int(sha256(b"aitbc-pedersen-h"))`` — a value anybody can compute. Knowing
   ``h`` collapses ``C = v*G + r*H`` to ``(v + r*h)*G``, so for *any* target amount ``v'`` the
   blinding ``r' = (v + r*h - v')/h`` opens the same commitment to ``v'``. A commitment that
   opens to every amount commits to none.
2. **The commitments were not additively homomorphic.** ``v`` was ``sha256(amount) mod n``,
   and ``sha256("2") + sha256("3") != sha256("5")``. ``add_commitments`` and
   ``subtract_commitments`` therefore produced points that opened to nothing, which made the
   wallet's ``balance_commitment`` — built entirely from them — meaningless.
3. **Nothing retained the blinding factors**, so ``balance_commitment`` could never be opened
   by anyone, including its owner. It was an unopenable point presented as a balance proof.

Because the amount was hashed, any string worked as an "amount": the tests passed
``"commitment-100"`` and the CLI passed whatever string it was given.

What is fixed here
------------------
``H`` is now derived by try-and-increment hash-to-curve from a domain-separated seed, so no
discrete log relative to ``G`` is known to anyone. ``v`` is the amount in fixed-point minor
units (see ``COMMITMENT_SCALE``), so the homomorphism holds and ``Commit(a) + Commit(b)``
opens to ``a + b`` under the summed blinding. Openings are retained by the wallet and no
longer travel in the envelope: ``ConfidentialTransaction`` carries only the commitment.

What is still missing, and matters
----------------------------------
* **No range proof.** Pedersen commitments are homomorphic modulo the group order, so a
  sufficiently large amount wraps and a "negative" amount is indistinguishable from a huge
  one. Amounts are bounded to ``[0, 2**64)`` at construction time, which constrains an honest
  sender but proves nothing to a verifier — a hostile sender constructs the point directly.
  Closing this needs Bulletproofs; until then a verifier cannot conclude that a transfer
  created no value.
* **No opening transport.** The recipient needs ``(amount, blinding)`` to open what it was
  sent, and this module deliberately does not put that in the envelope. Delivering it over an
  encrypted channel to the recipient is not implemented.

So: the commitments are now real, and the *system* built on them is still incomplete. Do not
present it as production confidentiality.

Why ``ecdsa`` is still a dependency (V23-19)
--------------------------------------------
This module is the only consumer of ``ecdsa`` in the repository, and ``ecdsa`` 0.19.2 carries
PYSEC-2026-1325 with no upstream fix — the library is pure Python and does not defend against
timing side channels. Only curve arithmetic is used (point addition and scalar multiplication
on NIST256p); ``cryptography`` deliberately exposes no raw point arithmetic, so it is not a
drop-in replacement, and hand-writing curve operations would be worse than the advisory.

The previous rationale added that there was nothing for a timing attack to steal, since the
blinding factor travelled in the clear anyway. **That is no longer true** — the blinding is
now a real secret held by the wallet, so the advisory now describes a live exposure rather
than a theoretical one. It is the cost of having working commitments at all, and it is the
reason a production implementation belongs on a constant-time library.
"""

from __future__ import annotations

import base64
import hashlib
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from ecdsa import NIST256p, VerifyingKey  # type: ignore[import-untyped]
from ecdsa.ellipticcurve import Point, PointJacobi  # type: ignore[import-untyped]

_CURVE = NIST256p.curve
_P: int = _CURVE.p()
_A: int = _CURVE.a()
_B: int = _CURVE.b()
_N: int = NIST256p.order
_G = NIST256p.generator

#: Decimal places preserved by the commitment. Amounts with more precision are rejected
#: rather than rounded -- silently losing a fraction of a payment is not an acceptable
#: default in financial code.
COMMITMENT_SCALE = 8

#: Upper bound on the committed value. There is no range *proof*; this only stops an honest
#: caller from constructing a commitment that wraps the group order. See the module docstring.
MAX_AMOUNT_UNITS = 2**64

# Sentinel bytes for the point at infinity.
_INFINITY_BYTES = b"\x00"

_H_SEED = b"aitbc/pedersen/H/nist256p/v2"


def _hash_to_curve(seed: bytes) -> Any:
    """Derive a curve point by try-and-increment, with no known discrete log.

    The second generator of a Pedersen commitment is binding only while nobody knows
    ``log_G(H)``. Deriving ``H`` as ``h*G`` for any computable ``h`` — as this module used to
    — hands that value to everyone. Hashing to an x-coordinate and solving the curve equation
    produces a point whose relationship to ``G`` nobody can express.

    NIST P-256 has ``p ≡ 3 (mod 4)``, so a square root is ``alpha ** ((p + 1) // 4)``, and
    cofactor 1, so every point on the curve generates the full prime-order group.
    """
    for counter in range(1024):
        x = int.from_bytes(hashlib.sha256(seed + counter.to_bytes(4, "big")).digest(), "big") % _P
        alpha = (pow(x, 3, _P) + _A * x + _B) % _P
        y = pow(alpha, (_P + 1) // 4, _P)
        if pow(y, 2, _P) == alpha:
            return Point(_CURVE, x, y)
    raise RuntimeError("hash-to-curve failed to find a point")  # pragma: no cover


_H = _hash_to_curve(_H_SEED)


def amount_to_units(amount: str | Decimal | int) -> int:
    """Return ``amount`` as an integer number of minor units.

    Rejects anything that is not a non-negative decimal within ``MAX_AMOUNT_UNITS`` and
    representable in ``COMMITMENT_SCALE`` places. The old code hashed the amount string, so
    ``"commitment-100"`` was an acceptable amount and ``"1"`` and ``"1.0"`` were different
    ones; both behaviours are now errors.
    """
    try:
        value = Decimal(str(amount))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"amount is not a decimal number: {amount!r}") from exc
    if not value.is_finite():
        raise ValueError(f"amount is not finite: {amount!r}")

    scaled = value.scaleb(COMMITMENT_SCALE)
    if scaled != scaled.to_integral_value():
        raise ValueError(f"amount has more than {COMMITMENT_SCALE} decimal places: {amount!r}")

    units = int(scaled)
    if units < 0:
        raise ValueError(f"amount is negative: {amount!r}")
    if units >= MAX_AMOUNT_UNITS:
        raise ValueError(f"amount exceeds the {MAX_AMOUNT_UNITS} unit bound: {amount!r}")
    return units


def units_to_amount(units: int) -> Decimal:
    """Inverse of :func:`amount_to_units`."""
    return Decimal(units).scaleb(-COMMITMENT_SCALE)


def random_blinding() -> bytes:
    """Return a fresh 32-byte blinding factor."""
    return os.urandom(32)


def _blinding_scalar(blinding: bytes) -> int:
    return int.from_bytes(blinding, "big") % _N


def add_blindings(*blindings: bytes) -> bytes:
    """Return the blinding factor that opens the sum of the corresponding commitments."""
    total = sum(_blinding_scalar(b) for b in blindings) % _N
    return total.to_bytes(32, "big")


def subtract_blindings(a: bytes, b: bytes) -> bytes:
    """Return the blinding factor that opens the difference of two commitments."""
    return ((_blinding_scalar(a) - _blinding_scalar(b)) % _N).to_bytes(32, "big")


def _commit(amount: str | Decimal | int, blinding: bytes) -> Any:
    """Return the Pedersen commitment point ``v*G + r*H``."""
    v = amount_to_units(amount)
    r = _blinding_scalar(blinding)
    return _G * v + _H * r


def commit(amount: str | Decimal | int, blinding: bytes) -> bytes:
    """Return the encoded Pedersen commitment to ``amount`` under ``blinding``."""
    return _encode(_commit(amount, blinding))


def _is_infinity(point: Any) -> bool:
    return point.x() is None or point.y() is None


def _encode(point: Any) -> bytes:
    """Encode a commitment point to compressed bytes."""
    if isinstance(point, PointJacobi):
        point = point.to_affine()
    if _is_infinity(point):
        return _INFINITY_BYTES
    return VerifyingKey.from_public_point(point, curve=NIST256p).to_string("compressed")  # type: ignore[no-any-return]


def _decode(data: bytes) -> Any:
    if data == _INFINITY_BYTES or not data:
        return _G * 0
    return VerifyingKey.from_string(data, curve=NIST256p).pubkey.point


def add_commitments(a: bytes, b: bytes) -> bytes:
    """Return the homomorphic sum of two commitment points.

    Opens to the sum of the two amounts under ``add_blindings`` of the two blinding factors.
    """
    return _encode(_decode(a) + _decode(b))


def subtract_commitments(a: bytes, b: bytes) -> bytes:
    """Return the homomorphic difference of two commitment points."""
    return _encode(_decode(a) + (_decode(b) * -1))


def verify_commitment(commitment: bytes, amount: str | Decimal | int, blinding: bytes) -> bool:
    """Return True if ``commitment`` opens to ``amount`` under ``blinding``.

    The caller must supply the opening. It is not carried in the envelope, which is the point
    of V23-19a: a verifier that recomputes a commitment from values sitting next to it has
    established only that the sender can do arithmetic.
    """
    try:
        return _encode(_commit(amount, blinding)) == commitment
    except Exception:
        return False


@dataclass(frozen=True)
class Opening:
    """The secret that opens a commitment. Never part of a transaction envelope."""

    amount: Decimal
    blinding: bytes

    def opens(self, commitment: bytes) -> bool:
        """Return True if this opening matches ``commitment``."""
        return verify_commitment(commitment, self.amount, self.blinding)


@dataclass
class ConfidentialTransaction:
    """A TEE-signed confidential transaction envelope.

    Carries the commitment only. ``amount_label`` and ``blinding`` were removed in V23-19a —
    an envelope that carries its own opening is not confidential, and a check that recomputes
    the commitment from that opening verifies nothing.
    """

    tx_id: str
    sender_id: str
    recipient_id: str
    amount_commitment: bytes = b""
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

    def opens_to(self, amount: str | Decimal | int, blinding: bytes) -> bool:
        """Return True if this envelope's commitment opens to the supplied secret.

        Replaces the old zero-argument ``verify_commitment()``, which compared the commitment
        against an amount and blinding stored in the same object and so could not fail for a
        well-formed sender.
        """
        return verify_commitment(self.amount_commitment, amount, blinding)


@dataclass
class ConfidentialWallet:
    """Wallet that tracks a confidential balance as a Pedersen commitment.

    The wallet retains the openings, which is what makes ``balance_commitment`` mean
    something: before V23-19a the blinding factors were discarded at the end of ``deposit``
    and ``send``, leaving a point nobody could ever open.
    """

    wallet_id: str
    owner_id: str
    balance_commitment: bytes = b""
    transactions: list[ConfidentialTransaction] = field(default_factory=list)

    #: Running opening of ``balance_commitment``, held by the owner and never transmitted.
    _balance_units: int = 0
    _balance_blinding: bytes = field(default=b"\x00" * 32)
    #: Opening for each sent transaction, keyed by ``tx_id``. The recipient needs this to
    #: open what it was sent; delivering it over an encrypted channel is not implemented.
    _openings: dict[str, Opening] = field(default_factory=dict)

    def deposit(self, amount: str | Decimal | int) -> Opening:
        """Add a confidential deposit to the balance and return its opening."""
        blinding = random_blinding()
        commitment = commit(amount, blinding)
        self.balance_commitment = add_commitments(self.balance_commitment, commitment)
        self._balance_units += amount_to_units(amount)
        self._balance_blinding = add_blindings(self._balance_blinding, blinding)
        return Opening(amount=Decimal(str(amount)), blinding=blinding)

    def send(
        self,
        recipient_id: str,
        amount: str | Decimal | int,
        signing_key: bytes,
    ) -> ConfidentialTransaction:
        """Create and sign a confidential transfer.

        The opening is retained on the wallet — see :meth:`opening_for` — rather than placed
        in the returned envelope.
        """
        units = amount_to_units(amount)
        if units > self._balance_units:
            raise ValueError(f"insufficient confidential balance: have {self.balance()}, sending {amount}")

        blinding = random_blinding()
        commitment = commit(amount, blinding)
        tx = ConfidentialTransaction(
            tx_id=f"ctx-{len(self.transactions)}",
            sender_id=self.owner_id,
            recipient_id=recipient_id,
            amount_commitment=commitment,
            nonce=len(self.transactions),
        )
        tx.sign(signing_key)
        self.transactions.append(tx)
        self._openings[tx.tx_id] = Opening(amount=Decimal(str(amount)), blinding=blinding)

        self.balance_commitment = subtract_commitments(self.balance_commitment, commitment)
        self._balance_units -= units
        self._balance_blinding = subtract_blindings(self._balance_blinding, blinding)
        return tx

    def opening_for(self, tx_id: str) -> Opening | None:
        """Return the opening for a transaction this wallet sent, if it has one."""
        return self._openings.get(tx_id)

    def balance(self) -> Decimal:
        """Return the cleartext balance. Owner-side only; never leaves the wallet."""
        return units_to_amount(self._balance_units)

    def open_balance(self) -> Opening:
        """Return the opening for ``balance_commitment``."""
        return Opening(amount=self.balance(), blinding=self._balance_blinding)

    def balance_proof(self) -> dict[str, Any]:
        """Return a balance proof suitable for TEE attestation.

        ``has_range_proof`` is reported because it is false: a recipient of this structure can
        confirm the commitment opens to the stated balance only if the owner hands over the
        opening, and cannot confirm the balance is non-negative at all.
        """
        return {
            "wallet_id": self.wallet_id,
            "owner_id": self.owner_id,
            "balance_commitment": self.balance_commitment.hex() if self.balance_commitment else "",
            "tx_count": len(self.transactions),
            "has_range_proof": False,
        }
