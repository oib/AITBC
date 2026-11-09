"""Tests for PersistentKeystoreService: create / unlock / sign / delete."""

from __future__ import annotations

import json
import sqlite3

import pytest
from eth_keys import keys as eth_keys
from eth_utils import keccak, to_checksum_address

from wallet_app.keystore.persistent_service import PersistentKeystoreService

from .conftest import OTHER_PASSWORD, TEST_PASSWORD


def test_create_wallet_returns_record(keystore: PersistentKeystoreService) -> None:
    record = keystore.create_wallet("alice", TEST_PASSWORD)

    assert record.wallet_id == "alice"
    # Post-migration (#1078): public_key is the EIP-55 checksummed 0x address
    # derived from the secp256k1 key, not the raw Ed25519 public key bytes.
    assert record.public_key.startswith("0x")
    assert len(bytes.fromhex(record.public_key[2:])) == 20
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


def test_signature_recovers_the_wallet_address(keystore: PersistentKeystoreService) -> None:
    # #1409: wallets are secp256k1 since #1078 — sign_message must produce a
    # signature that recovers the wallet's own 0x address, not an Ed25519
    # signature that can never verify against it.
    secret = bytes(range(1, 33))
    record = keystore.create_wallet("alice", TEST_PASSWORD, secret=secret)
    message = b"transfer 10 AIT"

    signature = keystore.sign_message("alice", TEST_PASSWORD, message)

    assert len(signature) == 65
    recovered = eth_keys.Signature(signature).recover_public_key_from_msg_hash(keccak(message))
    assert to_checksum_address(recovered.to_checksum_address()) == record.public_key


def test_sign_with_wrong_password_raises(keystore: PersistentKeystoreService) -> None:
    keystore.create_wallet("alice", TEST_PASSWORD)

    with pytest.raises(ValueError):
        keystore.sign_message("alice", OTHER_PASSWORD, b"payload")


def test_signatures_are_deterministic(keystore: PersistentKeystoreService) -> None:
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


# ---------- secp256k1 send path (WALLET-DAEMON-SEND-...-KEYS-1, #1078) ----------


def _legacy_ed25519_wallet(keystore: PersistentKeystoreService, wallet_id: str) -> None:
    """Rewrite a fresh wallet row into a pre-migration one: no key_scheme
    marker, the state every Ed25519-era wallet on disk still has."""
    conn = sqlite3.connect(keystore.db_path)
    try:
        conn.execute("UPDATE wallets SET metadata = '{}' WHERE wallet_id = ?", (wallet_id,))
        conn.commit()
    finally:
        conn.close()


def test_new_wallet_mints_secp256k1_with_0x_address(keystore: PersistentKeystoreService) -> None:
    record = keystore.create_wallet("carol", TEST_PASSWORD)

    assert record.public_key.startswith("0x")
    assert len(bytes.fromhex(record.public_key[2:])) == 20
    assert record.metadata["key_scheme"] == "secp256k1"


def test_wallet_address_is_derived_from_the_stored_secret(keystore: PersistentKeystoreService) -> None:
    """The address in public_key must be the one the stored key controls —
    the same mismatch class as UTILS-KEYSTORE-PY-KEY-NOT-DERIVED (#937)."""
    from aitbc.utils.validation import validate_address
    from eth_keys import keys as eth_keys

    secret = bytes(range(32, 64))
    record = keystore.create_wallet("named", TEST_PASSWORD, secret=secret)

    assert validate_address(record.public_key)
    assert record.public_key.lower() == eth_keys.PrivateKey(secret).public_key.to_address().lower()


def test_legacy_ed25519_wallet_refused_on_send(keystore: PersistentKeystoreService) -> None:
    """A pre-migration row must be refused with the clear error — never a
    signature the node cannot verify."""
    keystore.create_wallet("legacy", TEST_PASSWORD)
    _legacy_ed25519_wallet(keystore, "legacy")

    result = keystore.sign_and_submit_transaction("legacy", TEST_PASSWORD, "0x" + "11" * 20, 10, chain_id="test-chain")

    assert result["success"] is False
    assert "legacy Ed25519" in result["error"]
    assert "migrate funds" in result["error"]


def test_signed_transaction_recovers_sender_address(keystore: PersistentKeystoreService) -> None:
    """The signature over the node's canonical unsigned fields must recover
    to the sender's 0x address — the comparison the node actually runs."""
    from eth_keys import keys as eth_keys
    from eth_utils import keccak

    record = keystore.create_wallet("dave", TEST_PASSWORD)
    captured: dict = {}

    def fake_submit(self, tx_data, signature):
        captured["tx_data"] = tx_data
        captured["signature"] = signature
        return {"success": True, "transaction_hash": "0xdead"}

    monkey = pytest.MonkeyPatch()
    monkey.setattr(PersistentKeystoreService, "_submit_transaction_to_chain", fake_submit)
    monkey.setattr(PersistentKeystoreService, "_get_account_nonce", lambda self, addr: 7)
    monkey.setenv("CHAIN_ID", "test-chain")
    try:
        result = keystore.sign_and_submit_transaction("dave", TEST_PASSWORD, "0x" + "22" * 20, 42)
    finally:
        monkey.undo()

    assert result["success"] is True
    tx = captured["tx_data"]
    # canonical unsigned fields only — a timestamp here used to break verify
    assert set(tx) >= {"from", "to", "amount", "fee", "nonce", "chain_id", "type"}
    assert "timestamp" not in tx
    assert tx["from"] == record.public_key
    assert tx["nonce"] == 7

    message = json.dumps(tx, sort_keys=True, separators=(",", ":")).encode()
    sig = eth_keys.Signature(signature_bytes=bytes.fromhex(captured["signature"].removeprefix("0x")))
    # the node compares canonical_address(recovered) == canonical_address(from)
    from aitbc.crypto.signature_recovery import canonical_address

    assert canonical_address(sig.recover_public_key_from_msg_hash(keccak(message)).to_checksum_address()) == canonical_address(
        tx["from"]
    )


def test_submit_body_uses_node_aliases_and_reads_transaction_hash(
    keystore: PersistentKeystoreService,
) -> None:
    """The wire body must speak the node's only accepted names
    (from/to/signature — not sender/recipient/sig) and read
    transaction_hash, not tx_hash, out of the answer."""
    import wallet_app.keystore.persistent_service as svc

    record = keystore.create_wallet("erin", TEST_PASSWORD)
    captured: dict = {}

    class _Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return {"success": True, "transaction_hash": "0xbeef", "status": "pending"}

    def fake_post(url, json=None, timeout=None):
        captured["url"] = url
        captured["body"] = json
        return _Resp()

    monkey = pytest.MonkeyPatch()
    monkey.setattr(svc.httpx, "post", fake_post)
    monkey.setattr(svc.httpx, "get", lambda *a, **k: _Resp())  # unreachable — nonce given
    try:
        result = keystore.sign_and_submit_transaction(
            "erin", TEST_PASSWORD, "0x" + "33" * 20, 5, nonce=0, chain_id="test-chain"
        )
    finally:
        monkey.undo()

    body = captured["body"]
    for alias in ("from", "to", "signature"):
        assert alias in body
    for rejected in ("sender", "recipient", "sig"):
        assert rejected not in body
    assert body["from"] == record.public_key
    assert result["success"] is True
    assert result["tx_hash"] == "0xbeef"


def test_nonce_lookup_error_propagates(keystore: PersistentKeystoreService) -> None:
    """A failed nonce fetch must not silently sign with nonce 0 — the error
    surfaces and nothing is submitted."""
    called: list = []

    def explode(self, address):
        raise RuntimeError("rpc down")

    monkey = pytest.MonkeyPatch()
    monkey.setattr(PersistentKeystoreService, "_get_account_nonce", explode)
    monkey.setattr(
        PersistentKeystoreService,
        "_submit_transaction_to_chain",
        lambda self, tx, sig: called.append((tx, sig)) or {"success": True},
    )
    try:
        keystore.create_wallet("frank", TEST_PASSWORD)
        result = keystore.sign_and_submit_transaction("frank", TEST_PASSWORD, "0x" + "44" * 20, 5, chain_id="test-chain")
    finally:
        monkey.undo()

    assert result["success"] is False
    assert "rpc down" in result["error"]
    assert called == []
