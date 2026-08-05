"""Tests for PersistentKeystoreService: create / unlock / sign / delete."""

from __future__ import annotations

import sqlite3

import pytest
from nacl.signing import VerifyKey

from wallet_app.keystore.persistent_service import PersistentKeystoreService

from .conftest import OTHER_PASSWORD, TEST_PASSWORD


def test_create_wallet_returns_record(keystore: PersistentKeystoreService) -> None:
    record = keystore.create_wallet("alice", TEST_PASSWORD)

    assert record.wallet_id == "alice"
    assert len(bytes.fromhex(record.public_key)) == 32
    assert record.ciphertext
    assert "alice" in keystore.list_wallets()


def test_create_wallet_rejects_duplicate_id(keystore: PersistentKeystoreService) -> None:
    keystore.create_wallet("alice", TEST_PASSWORD)

    with pytest.raises(ValueError, match="already exists"):
        keystore.create_wallet("alice", TEST_PASSWORD)


def test_create_wallet_enforces_password_rules(keystore: PersistentKeystoreService) -> None:
    with pytest.raises(ValueError):
        keystore.create_wallet("weak", "short")


def test_create_wallet_rejects_wrong_length_secret(keystore: PersistentKeystoreService) -> None:
    with pytest.raises(ValueError, match="32 bytes"):
        keystore.create_wallet("bad-secret", TEST_PASSWORD, secret=b"too-short")


def test_unlock_returns_the_original_secret(keystore: PersistentKeystoreService) -> None:
    secret = bytes(range(32))
    keystore.create_wallet("alice", TEST_PASSWORD, secret=secret)

    assert keystore.unlock_wallet("alice", TEST_PASSWORD) == secret


def test_unlock_with_wrong_password_raises(keystore: PersistentKeystoreService) -> None:
    keystore.create_wallet("alice", TEST_PASSWORD)

    with pytest.raises(ValueError, match="failed to decrypt"):
        keystore.unlock_wallet("alice", OTHER_PASSWORD)


def test_unlock_unknown_wallet_raises(keystore: PersistentKeystoreService) -> None:
    with pytest.raises(KeyError):
        keystore.unlock_wallet("nobody", TEST_PASSWORD)


def test_private_key_is_not_stored_in_plaintext(keystore: PersistentKeystoreService) -> None:
    """The secret must never be recoverable by reading the keystore file directly."""
    secret = bytes(range(32))
    keystore.create_wallet("alice", TEST_PASSWORD, secret=secret)

    raw = keystore.db_path.read_bytes()

    assert secret not in raw
    assert TEST_PASSWORD.encode() not in raw


def test_signature_verifies_against_stored_public_key(keystore: PersistentKeystoreService) -> None:
    record = keystore.create_wallet("alice", TEST_PASSWORD)
    message = b"transfer 10 AIT"

    signature = keystore.sign_message("alice", TEST_PASSWORD, message)

    # Raises nacl.exceptions.BadSignatureError if the signature does not check out.
    VerifyKey(bytes.fromhex(record.public_key)).verify(message, signature)


def test_sign_with_wrong_password_raises(keystore: PersistentKeystoreService) -> None:
    keystore.create_wallet("alice", TEST_PASSWORD)

    with pytest.raises(ValueError):
        keystore.sign_message("alice", OTHER_PASSWORD, b"payload")


def test_signatures_are_deterministic_for_ed25519(keystore: PersistentKeystoreService) -> None:
    keystore.create_wallet("alice", TEST_PASSWORD, secret=bytes(range(32)))

    first = keystore.sign_message("alice", TEST_PASSWORD, b"payload")
    second = keystore.sign_message("alice", TEST_PASSWORD, b"payload")

    assert first == second


def test_delete_wallet_removes_it(keystore: PersistentKeystoreService) -> None:
    keystore.create_wallet("alice", TEST_PASSWORD)

    assert keystore.delete_wallet("alice") is True
    assert "alice" not in keystore.list_wallets()
    assert keystore.get_wallet("alice") is None


def test_delete_unknown_wallet_returns_false(keystore: PersistentKeystoreService) -> None:
    assert keystore.delete_wallet("nobody") is False


def test_wallets_persist_across_service_instances(keystore: PersistentKeystoreService) -> None:
    secret = bytes(range(32))
    keystore.create_wallet("alice", TEST_PASSWORD, secret=secret)

    reopened = PersistentKeystoreService(db_path=keystore.db_path)

    assert "alice" in reopened.list_wallets()
    assert reopened.unlock_wallet("alice", TEST_PASSWORD) == secret


def test_each_wallet_gets_distinct_salt_and_nonce(keystore: PersistentKeystoreService) -> None:
    first = keystore.create_wallet("alice", TEST_PASSWORD, secret=bytes(range(32)))
    second = keystore.create_wallet("bob", TEST_PASSWORD, secret=bytes(range(32)))

    assert first.salt != second.salt
    assert first.nonce != second.nonce
    # Identical secret + identical password must still yield different ciphertext.
    assert first.ciphertext != second.ciphertext


def test_access_log_records_success_and_failure(keystore: PersistentKeystoreService) -> None:
    keystore.create_wallet("alice", TEST_PASSWORD)
    keystore.unlock_wallet("alice", TEST_PASSWORD)
    with pytest.raises(ValueError):
        keystore.unlock_wallet("alice", OTHER_PASSWORD)

    actions = [entry["action"] for entry in keystore.get_access_log("alice")]

    assert "unlock_success" in actions
    assert "unlock_failed" in actions


def test_keystore_file_is_not_world_readable(keystore: PersistentKeystoreService) -> None:
    keystore.create_wallet("alice", TEST_PASSWORD)

    mode = keystore.db_path.stat().st_mode & 0o077

    assert mode == 0, f"keystore is group/world accessible (mode bits {mode:o})"


def test_metadata_roundtrips(keystore: PersistentKeystoreService) -> None:
    keystore.create_wallet("alice", TEST_PASSWORD, metadata={"label": "primary"})

    record = keystore.get_wallet("alice")

    assert record is not None
    assert record.metadata["label"] == "primary"


def test_sqlite_schema_has_expected_tables(keystore: PersistentKeystoreService) -> None:
    keystore.create_wallet("alice", TEST_PASSWORD)

    conn = sqlite3.connect(keystore.db_path)
    try:
        names = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        conn.close()

    assert {"wallets", "wallet_access_log"} <= names
