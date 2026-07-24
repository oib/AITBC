"""AITBC decentralized AI memory & storage shared types (v0.11.0 §A3).

Provides:
- ContentAddressedBlob, StorageLease, ReplicationProof, EncryptionEnvelope
- LeaseStatus, ReplicationStatus, EncryptionAlgorithm enums
- Domain exceptions for missing or unauthorized blobs
"""

from __future__ import annotations

from .errors import (
    AgentMemoryError,
    BlobNotFoundError,
    BlobUnauthorizedError,
    EncryptionError,
    LeaseExpiredError,
    ReplicationProofError,
)
from .models import (
    ContentAddressedBlob,
    EncryptionAlgorithm,
    EncryptionEnvelope,
    LeaseStatus,
    ReplicationProof,
    ReplicationStatus,
    StorageLease,
)

__all__ = [
    "AgentMemoryError",
    "BlobNotFoundError",
    "BlobUnauthorizedError",
    "ContentAddressedBlob",
    "EncryptionAlgorithm",
    "EncryptionError",
    "EncryptionEnvelope",
    "LeaseExpiredError",
    "LeaseStatus",
    "ReplicationProof",
    "ReplicationProofError",
    "ReplicationStatus",
    "StorageLease",
]
