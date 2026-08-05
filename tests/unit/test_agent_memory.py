"""Unit tests for aitbc.agent_memory shared types (v0.11.0 §A3).

Covers content-addressed blobs, storage leases, replication proofs, and
encryption envelopes.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from aitbc.agent_memory import (
    ContentAddressedBlob,
    EncryptionAlgorithm,
    EncryptionEnvelope,
    LeaseStatus,
    ReplicationProof,
    ReplicationStatus,
    StorageLease,
)


def test_blob_requires_content_address() -> None:
    with pytest.raises(ValueError):
        ContentAddressedBlob(content_address="", owner="agent-a")


def test_blob_negative_size() -> None:
    with pytest.raises(ValueError):
        ContentAddressedBlob(content_address="cid-123", owner="agent-a", size=-1)


def test_storage_lease_defaults() -> None:
    lease = StorageLease(
        lease_id="l1",
        content_address="cid-123",
        tenant="tenant-a",
        chain_id="ait-hub",
    )
    assert lease.status == LeaseStatus.PENDING
    assert lease.expires_at > lease.created_at
    assert not lease.is_expired()


def test_storage_lease_string_status() -> None:
    lease = StorageLease(
        lease_id="l1",
        content_address="cid-123",
        tenant="tenant-a",
        chain_id="ait-hub",
        status="active",
    )
    assert lease.status == LeaseStatus.ACTIVE


def test_storage_lease_expired() -> None:
    now = datetime.now(UTC)
    lease = StorageLease(
        lease_id="l1",
        content_address="cid-123",
        tenant="tenant-a",
        chain_id="ait-hub",
        status=LeaseStatus.ACTIVE,
        created_at=now - timedelta(days=2),
        expires_at=now - timedelta(days=1),
    )
    assert lease.is_expired(now)


def test_storage_lease_revoked_is_expired() -> None:
    lease = StorageLease(
        lease_id="l1",
        content_address="cid-123",
        tenant="tenant-a",
        chain_id="ait-hub",
        status=LeaseStatus.REVOKED,
    )
    assert lease.is_expired()


def test_storage_lease_expires_before_created() -> None:
    now = datetime.now(UTC)
    with pytest.raises(ValueError):
        StorageLease(
            lease_id="l1",
            content_address="cid-123",
            tenant="tenant-a",
            chain_id="ait-hub",
            created_at=now,
            expires_at=now - timedelta(seconds=1),
        )


def test_storage_lease_negative_price() -> None:
    with pytest.raises(ValueError):
        StorageLease(
            lease_id="l1",
            content_address="cid-123",
            tenant="tenant-a",
            chain_id="ait-hub",
            price=Decimal("-1"),
        )


def test_replication_proof_defaults() -> None:
    """An unchecked proof defaults to UNVERIFIED, not VALID.

    This previously asserted VALID, encoding a fail-open default: a proof nobody had
    verified was indistinguishable from one that had passed.
    """
    proof = ReplicationProof(
        proof_id="p1",
        content_address="cid-123",
        node_id="node-1",
    )
    assert proof.status == ReplicationStatus.UNVERIFIED


def test_replication_proof_string_status() -> None:
    proof = ReplicationProof(
        proof_id="p1",
        content_address="cid-123",
        node_id="node-1",
        status="invalid",
    )
    assert proof.status == ReplicationStatus.INVALID


def test_replication_proof_requires_node_id() -> None:
    with pytest.raises(ValueError):
        ReplicationProof(
            proof_id="p1",
            content_address="cid-123",
            node_id="",
        )


def test_encryption_envelope_defaults() -> None:
    envelope = EncryptionEnvelope(
        envelope_id="e1",
        content_address="cid-123",
        key_hash="sha256-key-hash",
    )
    assert envelope.algorithm == EncryptionAlgorithm.AES_256_GCM


def test_encryption_envelope_string_algorithm() -> None:
    envelope = EncryptionEnvelope(
        envelope_id="e1",
        content_address="cid-123",
        algorithm="chacha20-poly1305",
        key_hash="sha256-key-hash",
    )
    assert envelope.algorithm == EncryptionAlgorithm.CHACHA20_POLY1305


def test_encryption_envelope_requires_key_hash() -> None:
    with pytest.raises(ValueError):
        EncryptionEnvelope(
            envelope_id="e1",
            content_address="cid-123",
            key_hash="",
        )
