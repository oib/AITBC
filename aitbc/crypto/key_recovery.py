"""Key escrow and recovery flows for regulated data (v0.15.1 §A2).

Provides ``RecoveryShare``, ``KeyEscrow``, and helpers to split a sensitive
key into ``shares_total`` shards and reconstruct it. The default implementation
uses an XOR-based n-of-n scheme suitable for testing and development; production
deployments should replace this with a threshold Shamir Secret Sharing scheme
backed by hardware security modules.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

from .errors import CryptoError


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

    ponytail: the simulator uses an n-of-n XOR split. ``shares_required`` is
    stored for policy but recovery currently needs all shares. Production
    should use threshold Shamir Secret Sharing.
    """
    if not key_bytes:
        raise ValueError("key_bytes cannot be empty")
    if shares_total < 2:
        raise ValueError("shares_total must be at least 2")
    if shares_required is None:
        shares_required = shares_total

    # Generate random shares for all but the last position.
    random_shards = [os.urandom(len(key_bytes)) for _ in range(shares_total - 1)]
    last_shard = key_bytes
    for shard in random_shards:
        last_shard = bytes(a ^ b for a, b in zip(last_shard, shard, strict=True))

    shares = []
    for idx, shard in enumerate(random_shards + [last_shard], start=1):
        shares.append(
            RecoveryShare(
                share_id=f"{escrow_id}-{idx}",
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
    """Reconstruct the original key by XORing all provided shares together."""
    if not shares:
        raise CryptoError("at least one share is required for recovery")
    if shares_required is not None and len(shares) < shares_required:
        raise CryptoError("not enough shares for recovery")
    lengths = {len(share.shard) for share in shares}
    if len(lengths) != 1:
        raise CryptoError("all shares must have the same length")

    recovered = shares[0].shard
    for share in shares[1:]:
        recovered = bytes(a ^ b for a, b in zip(recovered, share.shard, strict=True))
    return recovered


def verify_escrow_integrity(escrow: KeyEscrow) -> bool:
    """Return True if the escrow can be recovered with the stored shares."""
    try:
        escrow.recover()
        return True
    except CryptoError:
        return False
