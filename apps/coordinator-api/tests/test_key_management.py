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
