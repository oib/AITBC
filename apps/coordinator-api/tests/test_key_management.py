"""
Tests for key management audit tokens and file storage permissions.
"""

import base64
import json
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from coordinator_api.contexts.security.services.key_management import FileKeyStorage, KeyManager
from coordinator_api.schemas import KeyPair


@pytest.mark.unit
@pytest.mark.asyncio
async def test_audit_authorization_signature(tmp_path: Path):
    """Valid audit tokens are accepted and forged tokens are rejected."""
    manager = KeyManager(FileKeyStorage(str(tmp_path)))
    token = await manager.create_audit_authorization("test-issuer", "test-purpose")
    assert manager.verify_audit_authorization_sync(token)

    # Tamper with the payload without recalculating the signature
    raw = base64.b64decode(token).decode()
    payload = json.loads(raw)
    payload["purpose"] = "forged-purpose"
    forged = base64.b64encode(json.dumps(payload).encode()).decode()
    assert manager.verify_audit_authorization_sync(forged) is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_file_key_storage_restricts_permissions(tmp_path: Path):
    """Private key files are written with 0o600 and the directory with 0o700."""
    storage = FileKeyStorage(str(tmp_path))
    key_pair = KeyPair(
        participant_id="test-participant",
        private_key=b"private-key-bytes",
        public_key=b"public-key-bytes",
        created_at=datetime.now(UTC),
    )
    await storage.store_key_pair(key_pair)

    private_path = tmp_path / "test-participant.priv"
    assert private_path.exists()
    assert (os.stat(private_path).st_mode & 0o777) == 0o600
    assert (os.stat(tmp_path).st_mode & 0o777) == 0o700


@pytest.mark.unit
@pytest.mark.asyncio
async def test_audit_authorization_naive_expires_at(tmp_path: Path, monkeypatch):
    """#1575: a token whose expires_at is a naive ISO string (legacy/foreign
    issuer) must not TypeError against the aware clock — it is treated as
    UTC."""
    import hashlib
    import hmac as hmac_mod
    from datetime import timedelta

    from coordinator_api.config import settings

    monkeypatch.setattr(settings, "hmac_secret", "test-hmac-secret")
    manager = KeyManager(FileKeyStorage(str(tmp_path)))
    token = await manager.create_audit_authorization("test-issuer", "test-purpose")

    raw = base64.b64decode(token).decode()
    payload = json.loads(raw)
    payload.pop("signature")
    # Rewrite expires_at as a NAIVE ISO string still in the future.
    payload["expires_at"] = (datetime.now(UTC) + timedelta(hours=1)).replace(tzinfo=None).isoformat()
    expected = hmac_mod.new(
        b"test-hmac-secret",
        json.dumps(payload, sort_keys=True).encode(),
        hashlib.sha256,
    ).hexdigest()
    payload["signature"] = expected
    naive_token = base64.b64encode(json.dumps(payload).encode()).decode()

    assert manager.verify_audit_authorization_sync(naive_token) is True
    # And the original aware token still verifies.
    assert manager.verify_audit_authorization_sync(token) is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_file_key_storage_rejects_traversal_participant(tmp_path: Path):
    """#1932 F1: participant_id is interpolated into storage filenames —
    traversal/separator payloads must be refused at the storage layer for
    every caller, before any path is built."""
    storage = FileKeyStorage(str(tmp_path / "keys"))
    key_pair = KeyPair(
        participant_id="../escaped",
        private_key=b"private-key-bytes",
        public_key=b"public-key-bytes",
        created_at=datetime.now(UTC),
    )
    with pytest.raises(ValueError, match="Invalid participant_id"):
        await storage.store_key_pair(key_pair)
    with pytest.raises(ValueError, match="Invalid participant_id"):
        await storage.get_key_pair("../escaped")
    with pytest.raises(ValueError, match="Invalid participant_id"):
        storage.get_key_pair_sync("../escaped")
    with pytest.raises(ValueError, match="Invalid participant_id"):
        await storage.revoke_keys("../escaped", "test")
    # Nothing may have been written outside the storage dir.
    assert not (tmp_path / "escaped.json").exists()
    assert not (tmp_path / "escaped.priv").exists()
    assert not (tmp_path / "keys" / ".." / "escaped.json").exists()


@pytest.mark.unit
@pytest.mark.parametrize("bad", ["a/b", "..", ".hidden", "has space", "x" * 64, "semi;colon", ""])
async def test_file_key_storage_rejects_unsafe_participant_ids(tmp_path: Path, bad: str):
    storage = FileKeyStorage(str(tmp_path / "keys"))
    with pytest.raises(ValueError, match="Invalid participant_id"):
        storage.get_key_pair_sync(bad)


@pytest.mark.unit
def test_audit_key_persists_across_restart_sync(tmp_path: Path):
    """#2162: with no event loop, generation persists via asyncio.run and a
    second KeyManager on the same dir loads the SAME key — no regeneration."""
    storage_dir = str(tmp_path / "keys")
    manager_a = KeyManager(FileKeyStorage(storage_dir))
    pub_a = manager_a.get_audit_key()

    priv_file = tmp_path / "keys" / "audit.priv"
    assert priv_file.exists()
    assert (os.stat(priv_file).st_mode & 0o777) == 0o600

    # "Restart": a brand-new KeyManager over the same storage dir.
    manager_b = KeyManager(FileKeyStorage(storage_dir))
    pub_b = manager_b.get_audit_key()
    assert pub_b.public_bytes_raw() == pub_a.public_bytes_raw()
    # Private halves match too (raw 32-byte X25519 scalars).
    assert manager_b._audit_private == manager_a._audit_private


@pytest.mark.unit
@pytest.mark.asyncio
async def test_audit_key_persists_across_restart_async(tmp_path: Path, monkeypatch):
    """#2162: inside a running loop the store is scheduled on the loop (not
    dropped) and a restarted manager loads the same public+private key."""
    import coordinator_api.config as config_mod

    monkeypatch.setattr(config_mod.settings, "hmac_secret", "test-hmac-secret")
    storage_dir = str(tmp_path / "keys")
    manager_a = KeyManager(FileKeyStorage(storage_dir))
    pub_a = manager_a.get_audit_key()
    # The store was scheduled on this loop; let it complete before "restart".
    if manager_a._audit_store_task is not None:
        await manager_a._audit_store_task
    assert (tmp_path / "keys" / "audit.priv").exists()

    token_a = await manager_a.create_audit_authorization("issuer", "audit")
    priv_a = await manager_a.get_audit_private_key(token_a)

    manager_b = KeyManager(FileKeyStorage(storage_dir))
    pub_b = manager_b.get_audit_key()
    assert pub_b.public_bytes_raw() == pub_a.public_bytes_raw()
    token_b = await manager_b.create_audit_authorization("issuer", "audit")
    priv_b = await manager_b.get_audit_private_key(token_b)
    assert priv_b.private_bytes_raw() == priv_a.private_bytes_raw()


@pytest.mark.unit
def test_audit_key_falls_back_when_storage_has_no_audit_key(tmp_path: Path):
    """#2162: a storage backend with no persisted audit key still yields a
    generated key (persistence failure must not break key access)."""

    class NoAuditStorage:
        def get_key_pair_sync(self, participant_id: str):
            raise NotImplementedError

        async def get_audit_key(self):
            return None

        async def store_audit_key(self, key_pair):
            return False

    manager = KeyManager(NoAuditStorage())
    pub = manager.get_audit_key()
    assert pub is not None
    assert len(pub.public_bytes_raw()) == 32


@pytest.mark.unit
def test_audit_key_regenerates_on_mismatched_persisted_key(tmp_path: Path):
    """#2162: a persisted audit.json whose public key does not match the
    private half is rejected and a fresh key is generated+persisted."""
    storage_dir = str(tmp_path / "keys")
    manager_a = KeyManager(FileKeyStorage(storage_dir))
    pub_a = manager_a.get_audit_key()

    # Tamper: rewrite audit.json with a different (valid-shaped) public key.
    audit_json = tmp_path / "keys" / "audit.json"
    metadata = json.loads(audit_json.read_text())
    metadata["public_key"] = base64.b64encode(b"\x00" * 32).decode()
    audit_json.write_text(json.dumps(metadata))

    manager_b = KeyManager(FileKeyStorage(storage_dir))
    pub_b = manager_b.get_audit_key()
    assert pub_b.public_bytes_raw() != pub_a.public_bytes_raw()
    # The fresh key was persisted, replacing the corrupt pair.
    manager_c = KeyManager(FileKeyStorage(storage_dir))
    assert manager_c.get_audit_key().public_bytes_raw() == pub_b.public_bytes_raw()
