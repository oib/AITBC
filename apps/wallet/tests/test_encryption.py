"""Tests for the wallet's Argon2id + XChaCha20-Poly1305 encryption suite."""

from __future__ import annotations

from secrets import token_bytes

import pytest

from wallet_app.crypto.encryption import EncryptionError, EncryptionSuite

from .conftest import OTHER_PASSWORD, TEST_PASSWORD


def _params(suite: EncryptionSuite) -> tuple[bytes, bytes]:
    return token_bytes(suite.salt_bytes), token_bytes(suite.nonce_bytes)


def test_encrypt_decrypt_roundtrip(encryption: EncryptionSuite) -> None:
    salt, nonce = _params(encryption)
    plaintext = token_bytes(32)

    ciphertext = encryption.encrypt(password=TEST_PASSWORD, plaintext=plaintext, salt=salt, nonce=nonce)
    recovered = encryption.decrypt(password=TEST_PASSWORD, ciphertext=ciphertext, salt=salt, nonce=nonce)

    assert recovered == plaintext


def test_ciphertext_does_not_contain_plaintext(encryption: EncryptionSuite) -> None:
    salt, nonce = _params(encryption)
    plaintext = token_bytes(32)

    ciphertext = encryption.encrypt(password=TEST_PASSWORD, plaintext=plaintext, salt=salt, nonce=nonce)

    assert plaintext not in ciphertext
    assert ciphertext != plaintext


def test_wrong_password_fails_to_decrypt(encryption: EncryptionSuite) -> None:
    salt, nonce = _params(encryption)
    ciphertext = encryption.encrypt(password=TEST_PASSWORD, plaintext=token_bytes(32), salt=salt, nonce=nonce)

    with pytest.raises(EncryptionError):
        encryption.decrypt(password=OTHER_PASSWORD, ciphertext=ciphertext, salt=salt, nonce=nonce)


def test_wrong_salt_fails_to_decrypt(encryption: EncryptionSuite) -> None:
    salt, nonce = _params(encryption)
    ciphertext = encryption.encrypt(password=TEST_PASSWORD, plaintext=token_bytes(32), salt=salt, nonce=nonce)
    other_salt = token_bytes(encryption.salt_bytes)

    with pytest.raises(EncryptionError):
        encryption.decrypt(password=TEST_PASSWORD, ciphertext=ciphertext, salt=other_salt, nonce=nonce)


def test_tampered_ciphertext_is_rejected(encryption: EncryptionSuite) -> None:
    """AEAD must detect modification rather than returning garbage plaintext."""
    salt, nonce = _params(encryption)
    ciphertext = bytearray(encryption.encrypt(password=TEST_PASSWORD, plaintext=token_bytes(32), salt=salt, nonce=nonce))
    ciphertext[0] ^= 0xFF

    with pytest.raises(EncryptionError):
        encryption.decrypt(password=TEST_PASSWORD, ciphertext=bytes(ciphertext), salt=salt, nonce=nonce)


def test_same_plaintext_differs_under_different_salts(encryption: EncryptionSuite) -> None:
    """A fresh salt per wallet must produce distinct ciphertext for identical input."""
    plaintext = token_bytes(32)
    salt_a, nonce_a = _params(encryption)
    salt_b, nonce_b = _params(encryption)

    first = encryption.encrypt(password=TEST_PASSWORD, plaintext=plaintext, salt=salt_a, nonce=nonce_a)
    second = encryption.encrypt(password=TEST_PASSWORD, plaintext=plaintext, salt=salt_b, nonce=nonce_b)

    assert first != second
