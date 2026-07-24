"""Unit tests for aitbc.crypto tenant keys and key recovery (v0.15.1 §A2)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from aitbc.crypto import (
    CryptoError,
    KeyEscrowStatus,
    RecoveryShare,
    TenantKeyManager,
    TenantKeyPolicy,
    TenantKeyStatus,
    escrow_key,
    recover_key,
    verify_escrow_integrity,
)


def test_tenant_key_derivation_and_encryption() -> None:
    policy = TenantKeyPolicy(tenant_id="tenant-1")
    manager = TenantKeyManager(policy)
    secret = b"tenant-master-secret"
    key = manager.derive("key-1", secret)

    assert key.tenant_id == "tenant-1"
    assert key.status == TenantKeyStatus.ACTIVE
    assert len(key.key_bytes) == 32

    ciphertext = manager.encrypt(key, b"sensitive data")
    plaintext = manager.decrypt(key, ciphertext)
    assert plaintext == b"sensitive data"


def test_tenant_key_rotation_and_reencryption() -> None:
    policy = TenantKeyPolicy(tenant_id="tenant-1")
    manager = TenantKeyManager(policy)

    old_key = manager.derive("key-1", b"secret-1")
    ciphertext = manager.encrypt(old_key, b"regulated payload")

    new_key = manager.rotate(old_key, "key-2", b"secret-2")
    assert new_key.status == TenantKeyStatus.ACTIVE
    assert old_key.status == TenantKeyStatus.ROTATED

    new_ciphertext = manager.reencrypt(old_key, new_key, ciphertext)
    assert manager.decrypt(new_key, new_ciphertext) == b"regulated payload"


def test_tenant_key_expired_cannot_encrypt() -> None:
    policy = TenantKeyPolicy(tenant_id="tenant-1")
    manager = TenantKeyManager(policy)
    key = manager.derive("key-1", b"secret")
    key.expires_at = datetime.now(UTC) - timedelta(minutes=1)

    with pytest.raises(CryptoError):
        manager.encrypt(key, b"data")


def test_tenant_key_revoked_cannot_decrypt() -> None:
    policy = TenantKeyPolicy(tenant_id="tenant-1")
    manager = TenantKeyManager(policy)
    key = manager.derive("key-1", b"secret")
    ciphertext = manager.encrypt(key, b"data")
    key.status = TenantKeyStatus.REVOKED

    with pytest.raises(CryptoError):
        manager.decrypt(key, ciphertext)


def test_key_escrow_and_recovery() -> None:
    key = os_urandom(32)
    escrow = escrow_key(
        escrow_id="esc-1",
        key_id="key-1",
        key_bytes=key,
        shares_total=3,
        shares_required=3,
    )
    assert escrow.status == KeyEscrowStatus.ACTIVE
    assert len(escrow.shares) == 3
    assert verify_escrow_integrity(escrow) is True

    recovered = recover_key(escrow.shares, shares_required=3)
    assert recovered == key


def test_key_recovery_requires_all_shares() -> None:
    key = os_urandom(32)
    escrow = escrow_key("esc-1", "key-1", key, shares_total=3, shares_required=3)
    with pytest.raises(CryptoError):
        recover_key(escrow.shares[:2], shares_required=3)


def test_key_recovery_rejects_mismatched_share_lengths() -> None:
    shares = [
        RecoveryShare(share_id="s1", escrow_id="esc-1", shard=b"abcd"),
        RecoveryShare(share_id="s2", escrow_id="esc-1", shard=b"xyz"),
    ]
    with pytest.raises(CryptoError):
        recover_key(shares)


# small helper so tests don't need to import os


def os_urandom(n: int) -> bytes:
    import os

    return os.urandom(n)
