"""Domain exceptions for aitbc.agent_memory (v0.11.0 §A3)."""

from __future__ import annotations


class AgentMemoryError(Exception):
    """Base exception for decentralized memory & storage domain errors."""


class BlobNotFoundError(AgentMemoryError):
    """Requested blob does not exist or is not retrievable."""


class BlobUnauthorizedError(AgentMemoryError):
    """Caller is not authorized to access the blob."""


class LeaseExpiredError(AgentMemoryError):
    """Storage lease has expired or been revoked."""


class ReplicationProofError(AgentMemoryError):
    """Replication proof is invalid, expired, or cannot be verified."""


class EncryptionError(AgentMemoryError):
    """Blob encryption or decryption operation failed."""
