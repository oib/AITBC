from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from argon2.low_level import Type as Argon2Type, hash_secret_raw
from nacl.bindings import (
    crypto_aead_xchacha20poly1305_ietf_decrypt,
    crypto_aead_xchacha20poly1305_ietf_encrypt,
)


class EncryptionError(Exception):
    """Raised when encryption or decryption fails."""


@dataclass
class EncryptionSuite:
    """Argon2id + XChaCha20-Poly1305 helper functions."""

    salt_bytes: int = 16
    nonce_bytes: int = 24
    key_bytes: int = 32
    argon_time_cost: int = 3
    argon_memory_cost: int = 64 * 1024  # kibibytes
    argon_parallelism: int = 2

    def _derive_key(self, *, password: str, salt: bytes) -> bytes:
        password_bytes = password.encode("utf-8")
        return hash_secret_raw(
            secret=password_bytes,
            salt=salt,
            time_cost=self.argon_time_cost,
            memory_cost=self.argon_memory_cost,
            parallelism=self.argon_parallelism,
            hash_len=self.key_bytes,
            type=Argon2Type.ID,
        )

    def encrypt(self, *, password: str, plaintext: bytes, salt: bytes, nonce: bytes) -> bytes:
        key = self._derive_key(password=password, salt=salt)
        try:
            return crypto_aead_xchacha20poly1305_ietf_encrypt(
                message=plaintext,
                aad=b"",
                nonce=nonce,
                key=key,
            )
        except Exception as exc:  # pragma: no cover
            raise EncryptionError("encryption failed") from exc

    def decrypt(self, *, password: str, ciphertext: bytes, salt: bytes, nonce: bytes) -> bytes:
        key = self._derive_key(password=password, salt=salt)
        try:
            return crypto_aead_xchacha20poly1305_ietf_decrypt(
                ciphertext=ciphertext,
                aad=b"",
                nonce=nonce,
                key=key,
            )
        except Exception as exc:
            raise EncryptionError("decryption failed") from exc
