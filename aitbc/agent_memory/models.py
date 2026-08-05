"""Shared decentralized AI memory & storage types for AITBC (v0.11.0 §A3).

These are the canonical dependency-free primitives consumed by the
``apps/memory/`` service, agent runtimes, and the CLI. They define content
addressing, storage leases, replication proofs, and encryption envelopes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Any


class LeaseStatus(StrEnum):
    """Lifecycle status of a storage lease."""

    PENDING = "pending"
    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"


class ReplicationStatus(StrEnum):
    """Status of a replication proof returned by a storage node."""

    # Default state for a freshly constructed proof: nothing has checked it yet. Distinct
    # from INVALID, which is a verdict. Without this the dataclass had to default to a
    # trusting value, so an unchecked proof read as proven.
    UNVERIFIED = "unverified"
    VALID = "valid"
    EXPIRED = "expired"
    INVALID = "invalid"


class EncryptionAlgorithm(StrEnum):
    """Supported encryption algorithms for memory blobs."""

    AES_256_GCM = "aes-256-gcm"
    CHACHA20_POLY1305 = "chacha20-poly1305"


@dataclass
class ContentAddressedBlob:
    """A content-addressed data blob.

    The ``content_address`` is the canonical identifier (e.g. a SHA-256 CID)
    and must be non-empty.
    """

    content_address: str
    owner: str
    size: int = 0
    tags: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if not self.content_address:
            raise ValueError("content_address is required")
        if self.size < 0:
            raise ValueError("size cannot be negative")


@dataclass
class StorageLease:
    """A lease that grants a tenant access to a blob for a bounded time."""

    lease_id: str
    content_address: str
    tenant: str
    chain_id: str
    status: LeaseStatus | str = LeaseStatus.PENDING
    price: Decimal = field(default_factory=lambda: Decimal("0"))
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime = field(default_factory=lambda: datetime.now(UTC) + timedelta(days=7))
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if isinstance(self.status, str):
            self.status = LeaseStatus(self.status)
        if not self.content_address:
            raise ValueError("content_address is required")
        if not self.tenant:
            raise ValueError("tenant is required")
        if self.expires_at <= self.created_at:
            raise ValueError("expires_at must be after created_at")
        if self.price < 0:
            raise ValueError("price cannot be negative")

    def is_expired(self, now: datetime | None = None) -> bool:
        """Return True if the lease has passed its expiration time."""
        if self.status == LeaseStatus.REVOKED:
            return True
        if now is None:
            now = datetime.now(UTC)
        return self.expires_at <= now


@dataclass
class ReplicationProof:
    """Proof that a storage node is holding a copy of a blob."""

    proof_id: str
    content_address: str
    node_id: str
    status: ReplicationStatus | str = ReplicationStatus.UNVERIFIED
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    challenge_nonce: str = ""
    signature: str = ""
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if isinstance(self.status, str):
            self.status = ReplicationStatus(self.status)
        if not self.content_address:
            raise ValueError("content_address is required")
        if not self.node_id:
            raise ValueError("node_id is required")


@dataclass
class EncryptionEnvelope:
    """Encryption metadata and ciphertext wrapper for a blob."""

    envelope_id: str
    content_address: str
    algorithm: EncryptionAlgorithm | str = EncryptionAlgorithm.AES_256_GCM
    key_hash: str = ""
    ciphertext: bytes = field(default_factory=bytes)
    nonce: bytes = field(default_factory=bytes)
    auth_tag: bytes = field(default_factory=bytes)
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if isinstance(self.algorithm, str):
            self.algorithm = EncryptionAlgorithm(self.algorithm)
        if not self.content_address:
            raise ValueError("content_address is required")
        if not self.key_hash:
            raise ValueError("key_hash is required")
