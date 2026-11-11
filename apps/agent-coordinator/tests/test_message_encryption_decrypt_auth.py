"""CRYPTO-AUDIT-1 (#1551): MessageEncryptor.decrypt_message must fail closed.

Previously a message whose claimed ``sender_id`` had no registered public
key skipped signature verification entirely and still returned plaintext.
"""

from __future__ import annotations

import dataclasses

import pytest

from agent_app.encryption.message_encryption import MessageEncryptor


@pytest.fixture
def encryptor(tmp_path) -> MessageEncryptor:
    return MessageEncryptor(keys_dir=str(tmp_path / "keys"))


def test_roundtrip_still_decrypts(encryptor: MessageEncryptor) -> None:
    encryptor.generate_key_pair("alice")
    encryptor.generate_key_pair("bob")
    msg = encryptor.encrypt_message({"text": "hello"}, "alice", "bob")
    assert msg is not None
    assert encryptor.decrypt_message(msg, "bob") == {"text": "hello"}


def test_unknown_sender_returns_none(encryptor: MessageEncryptor) -> None:
    """A valid ciphertext under an unregistered sender_id yields no plaintext."""
    encryptor.generate_key_pair("alice")
    encryptor.generate_key_pair("bob")
    msg = encryptor.encrypt_message({"text": "hello"}, "alice", "bob")
    assert msg is not None
    forged = dataclasses.replace(msg, sender_id="ghost-agent")
    assert encryptor.decrypt_message(forged, "bob") is None


def test_bad_signature_returns_none(encryptor: MessageEncryptor) -> None:
    encryptor.generate_key_pair("alice")
    encryptor.generate_key_pair("bob")
    msg = encryptor.encrypt_message({"text": "hello"}, "alice", "bob")
    assert msg is not None
    forged = dataclasses.replace(msg, signature=b"\x00" * len(msg.signature))
    assert encryptor.decrypt_message(forged, "bob") is None
