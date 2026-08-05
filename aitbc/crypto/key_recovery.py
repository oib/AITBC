"""Key escrow and recovery flows for regulated data (v0.15.1 §A2).

Provides ``RecoveryShare``, ``KeyEscrow``, and helpers to split a sensitive key into
``shares_total`` shards and reconstruct it from any ``shares_required`` of them, using
Shamir Secret Sharing over GF(2**8).

This previously used an XOR n-of-n split while accepting and validating a
``shares_required`` threshold, so it looked like an M-of-N scheme. Recovering with
exactly ``shares_required`` shares out of a larger total XOR'd a subset and returned
**wrong key material with no error** -- the caller then used that as a key. The threshold
is now real, and is carried inside each share so recovery cannot be talked out of
enforcing it.

Shares remain sensitive: fewer than ``shares_required`` of them reveal nothing about the
key (that is the point of the scheme), but each is still key-adjacent material and should
be stored accordingly. An HSM-backed implementation remains preferable for production
custody; this provides the correct algorithm in software.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

from .errors import CryptoError

# --- GF(2**8) arithmetic -------------------------------------------------------------
# Rijndael field, irreducible polynomial x^8 + x^4 + x^3 + x + 1 (0x11B). Exp/log tables
# make multiplication and division table lookups rather than bit loops.
_GF_EXP: list[int] = [0] * 512
_GF_LOG: list[int] = [0] * 256


def _build_gf_tables() -> None:
    """Build exp/log tables using 3 as the generator.

    2 is not a generator of this field -- it has multiplicative order 51, not 255, so a
    table built from it is not a bijection and mul/div silently return wrong results.
    """
    x = 1
    for i in range(255):
        _GF_EXP[i] = x
        _GF_LOG[x] = i
        # x *= 3, i.e. (x * 2) ^ x, with reduction mod the field polynomial.
        doubled = x << 1
        if doubled & 0x100:
            doubled ^= 0x11B
        x = doubled ^ x
    # Duplicate the cycle so _gf_mul can index log[a]+log[b] (max 508) without a modulo.
    for i in range(255, 512):
        _GF_EXP[i] = _GF_EXP[i - 255]


_build_gf_tables()


def _gf_mul(a: int, b: int) -> int:
    if a == 0 or b == 0:
        return 0
    return _GF_EXP[_GF_LOG[a] + _GF_LOG[b]]


def _gf_div(a: int, b: int) -> int:
    if b == 0:
        raise CryptoError("division by zero in GF(2**8)")
    if a == 0:
        return 0
    return _GF_EXP[(_GF_LOG[a] - _GF_LOG[b]) % 255]


def _interpolate_at_zero(points: list[tuple[int, int]]) -> int:
    """Lagrange-interpolate f(0) from (x, y) points over GF(2**8)."""
    secret = 0
    for i, (x_i, y_i) in enumerate(points):
        numerator, denominator = 1, 1
        for j, (x_j, _) in enumerate(points):
            if i == j:
                continue
            numerator = _gf_mul(numerator, x_j)
            denominator = _gf_mul(denominator, x_i ^ x_j)
        secret ^= _gf_mul(y_i, _gf_div(numerator, denominator))
    return secret


# Each shard is self-describing: x-coordinate, threshold, and a digest of the secret,
# followed by one evaluation byte per secret byte. Carrying the threshold in the share is
# what makes the guarantee hold regardless of what a caller passes to recover_key.
_SHARD_HEADER = 2  # x, k
_DIGEST_LEN = 4


def _secret_digest(secret: bytes) -> bytes:
    return hashlib.sha256(secret).digest()[:_DIGEST_LEN]


class KeyEscrowStatus(StrEnum):
    """Lifecycle status of a key escrow."""

    PENDING = "pending"
    ACTIVE = "active"
    RECOVERED = "recovered"
    EXPIRED = "expired"


@dataclass
class RecoveryShare:
    """A single share of an escrowed key."""

    share_id: str
    escrow_id: str
    shard: bytes
    holder: str = ""
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.shard:
            raise ValueError("shard cannot be empty")


@dataclass
class KeyEscrow:
    """Container for an escrowed key split into recovery shares."""

    escrow_id: str
    key_id: str
    shares_required: int
    shares_total: int
    shares: list[RecoveryShare] = field(default_factory=list)
    status: KeyEscrowStatus | str = KeyEscrowStatus.PENDING
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime = field(default_factory=lambda: datetime.now(UTC) + timedelta(days=365))
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if isinstance(self.status, str):
            self.status = KeyEscrowStatus(self.status)
        if self.shares_required < 1 or self.shares_total < self.shares_required:
            raise ValueError("shares_total must be >= shares_required >= 1")

    def is_expired(self, now: datetime | None = None) -> bool:
        """Return True if the escrow has expired."""
        if now is None:
            now = datetime.now(UTC)
        return self.expires_at <= now

    def recover(self) -> bytes:
        """Recover the escrowed key using the stored shares."""
        return recover_key(self.shares, shares_required=self.shares_required)


def escrow_key(
    escrow_id: str,
    key_id: str,
    key_bytes: bytes,
    shares_total: int,
    shares_required: int | None = None,
) -> KeyEscrow:
    """Split ``key_bytes`` into ``shares_total`` recovery shares.

    Any ``shares_required`` of the resulting shares reconstruct the key; any fewer reveal
    nothing about it. The threshold and the x-coordinate are embedded in each shard, so
    recovery enforces the threshold even if the caller does not supply it.
    """
    if not key_bytes:
        raise ValueError("key_bytes cannot be empty")
    if shares_total < 2:
        raise ValueError("shares_total must be at least 2")
    # x-coordinates are 1..shares_total and must be distinct non-zero field elements;
    # x=0 is the secret itself.
    if shares_total > 255:
        raise ValueError("shares_total cannot exceed 255 (GF(2**8) has 255 non-zero points)")
    if shares_required is None:
        shares_required = shares_total
    if shares_required < 2:
        raise ValueError("shares_required must be at least 2")
    if shares_required > shares_total:
        raise ValueError("shares_required cannot exceed shares_total")

    digest = _secret_digest(key_bytes)

    # One independent polynomial per secret byte: f(0) = the byte, with shares_required-1
    # random coefficients. Coefficients come from secrets.token_bytes (CSPRNG) -- they are
    # what stands between an attacker holding k-1 shares and the key.
    evaluations: list[bytearray] = [bytearray() for _ in range(shares_total)]
    for byte in key_bytes:
        coefficients = [byte, *secrets.token_bytes(shares_required - 1)]
        for idx in range(shares_total):
            x = idx + 1
            # Horner evaluation of the polynomial at x, over GF(2**8).
            y = 0
            for coefficient in reversed(coefficients):
                y = _gf_mul(y, x) ^ coefficient
            evaluations[idx].append(y)

    shares = []
    for idx in range(shares_total):
        x = idx + 1
        shard = bytes([x, shares_required]) + digest + bytes(evaluations[idx])
        shares.append(
            RecoveryShare(
                share_id=f"{escrow_id}-{x}",
                escrow_id=escrow_id,
                shard=shard,
            )
        )

    escrow = KeyEscrow(
        escrow_id=escrow_id,
        key_id=key_id,
        shares_required=shares_required,
        shares_total=shares_total,
        shares=shares,
        status=KeyEscrowStatus.ACTIVE,
    )
    return escrow


def recover_key(shares: list[RecoveryShare], shares_required: int | None = None) -> bytes:
    """Reconstruct the original key from at least ``shares_required`` shares.

    The threshold embedded in the shares is authoritative. ``shares_required`` is honoured
    as an additional caller-side assertion but cannot lower the real threshold: passing a
    smaller number, or omitting it, still refuses to reconstruct from too few shares. A
    digest of the original secret is verified so a wrong or corrupt share set fails loudly
    rather than returning plausible-looking bytes.
    """
    if not shares:
        raise CryptoError("at least one share is required for recovery")

    lengths = {len(share.shard) for share in shares}
    if len(lengths) != 1:
        raise CryptoError("all shares must have the same length")
    shard_len = lengths.pop()
    if shard_len <= _SHARD_HEADER + _DIGEST_LEN:
        raise CryptoError("shares are malformed or truncated")

    thresholds = {share.shard[1] for share in shares}
    if len(thresholds) != 1:
        raise CryptoError("shares disagree on the recovery threshold")
    embedded_threshold = thresholds.pop()
    if embedded_threshold < 2:
        raise CryptoError("shares carry an invalid recovery threshold")

    digests = {share.shard[_SHARD_HEADER : _SHARD_HEADER + _DIGEST_LEN] for share in shares}
    if len(digests) != 1:
        raise CryptoError("shares belong to different secrets")
    expected_digest = digests.pop()

    x_coordinates = [share.shard[0] for share in shares]
    if 0 in x_coordinates:
        raise CryptoError("share has an invalid x-coordinate of 0")
    if len(set(x_coordinates)) != len(x_coordinates):
        raise CryptoError("duplicate shares supplied; each share must be distinct")

    # The embedded threshold wins. Requesting fewer is the exact mistake that used to
    # return a wrong key silently.
    required = max(embedded_threshold, shares_required or 0)
    if len(shares) < required:
        raise CryptoError(f"not enough shares for recovery: have {len(shares)}, need {required}")

    # Any `required` shares suffice; extras are ignored rather than over-determining.
    selected = shares[:required]
    body_len = shard_len - _SHARD_HEADER - _DIGEST_LEN
    recovered = bytearray()
    for position in range(body_len):
        points = [(share.shard[0], share.shard[_SHARD_HEADER + _DIGEST_LEN + position]) for share in selected]
        recovered.append(_interpolate_at_zero(points))

    result = bytes(recovered)
    if not secrets.compare_digest(_secret_digest(result), expected_digest):
        raise CryptoError("recovered key failed integrity check; shares are corrupt or mismatched")
    return result


def verify_escrow_integrity(escrow: KeyEscrow) -> bool:
    """Return True if the escrow can be recovered with the stored shares."""
    try:
        escrow.recover()
        return True
    except CryptoError:
        return False
