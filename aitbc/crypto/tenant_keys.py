"""Per-tenant key derivation and rotation for regulated data (v0.15.1 §A2).

Provides ``TenantKeyPolicy``, ``TenantKey``, and ``TenantKeyManager``
primitives. Keys are derived from a tenant secret using PBKDF2 and are used
with Fernet symmetric encryption. Rotation re-encrypts data under a freshly
derived key without changing the underlying plaintext.
"""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from .errors import CryptoError


class TenantKeyStatus(StrEnum):
    """Lifecycle status of a tenant key."""

    ACTIVE = "active"
    ROTATED = "rotated"
    EXPIRED = "expired"
    REVOKED = "revoked"


@dataclass
class TenantKeyPolicy:
    """Policy controlling how tenant keys are derived and rotated."""

    tenant_id: str
    algorithm: str = "fernet"
    iterations: int = 100_000
    salt_bytes: int = 16
    key_length: int = 32
    rotation_interval: timedelta = field(default_factory=lambda: timedelta(days=90))
    max_age: timedelta = field(default_factory=lambda: timedelta(days=365))
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.iterations < 10_000:
            raise ValueError("iterations must be at least 10,000")
        if self.salt_bytes < 8:
            raise ValueError("salt_bytes must be at least 8")


@dataclass
class TenantKey:
    """A derived symmetric key for a tenant."""

    key_id: str
    tenant_id: str
    key_bytes: bytes
    salt: bytes
    status: TenantKeyStatus | str = TenantKeyStatus.ACTIVE
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime = field(default_factory=lambda: datetime.now(UTC) + timedelta(days=365))
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if isinstance(self.status, str):
            self.status = TenantKeyStatus(self.status)
        if not self.key_bytes:
            raise ValueError("key_bytes cannot be empty")
        if len(self.salt) < 8:
            raise ValueError("salt must be at least 8 bytes")

    def is_expired(self, now: datetime | None = None) -> bool:
        """Return True if the key has expired."""
        if now is None:
            now = datetime.now(UTC)
        return self.expires_at <= now

    def fernet(self) -> Fernet:
        """Return a Fernet instance for this key."""
        url_safe_key = base64.urlsafe_b64encode(self.key_bytes)
        return Fernet(url_safe_key)


class TenantKeyManager:
    """Derive, rotate, and use per-tenant encryption keys."""

    def __init__(self, policy: TenantKeyPolicy) -> None:
        self.policy = policy

    def _derive(self, secret: bytes, salt: bytes) -> bytes:
        """Derive a key using PBKDF2-HMAC-SHA256."""
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=self.policy.key_length,
            salt=salt,
            iterations=self.policy.iterations,
        )
        return kdf.derive(secret)

    def derive(
        self,
        key_id: str,
        tenant_secret: bytes,
        salt: bytes | None = None,
    ) -> TenantKey:
        """Derive a tenant key from a tenant secret and random salt."""
        if salt is None:
            salt = os.urandom(self.policy.salt_bytes)
        if len(salt) < 8:
            raise ValueError("salt must be at least 8 bytes")
        key_bytes = self._derive(tenant_secret, salt)
        return TenantKey(
            key_id=key_id,
            tenant_id=self.policy.tenant_id,
            key_bytes=key_bytes,
            salt=salt,
            expires_at=datetime.now(UTC) + self.policy.max_age,
        )

    def rotate(
        self,
        current_key: TenantKey,
        new_key_id: str,
        new_tenant_secret: bytes,
    ) -> TenantKey:
        """Rotate a tenant key and return the new key.

        The caller is responsible for re-encrypting existing ciphertext with
        the new key.
        """
        if current_key.tenant_id != self.policy.tenant_id:
            raise CryptoError("key tenant_id does not match policy")
        new_key = self.derive(new_key_id, new_tenant_secret)
        current_key.status = TenantKeyStatus.ROTATED
        return new_key

    def encrypt(self, key: TenantKey, plaintext: bytes) -> bytes:
        """Encrypt plaintext with the tenant key."""
        if key.is_expired():
            raise CryptoError("key has expired")
        if key.status != TenantKeyStatus.ACTIVE:
            raise CryptoError(f"key is not active: {key.status}")
        return key.fernet().encrypt(plaintext)

    def decrypt(self, key: TenantKey, ciphertext: bytes) -> bytes:
        """Decrypt ciphertext with the tenant key."""
        if key.status == TenantKeyStatus.REVOKED:
            raise CryptoError("key has been revoked")
        try:
            return key.fernet().decrypt(ciphertext)
        except InvalidToken as exc:
            raise CryptoError("decryption failed: invalid token") from exc

    def reencrypt(
        self,
        old_key: TenantKey,
        new_key: TenantKey,
        ciphertext: bytes,
    ) -> bytes:
        """Decrypt with ``old_key`` and re-encrypt with ``new_key``."""
        plaintext = self.decrypt(old_key, ciphertext)
        return self.encrypt(new_key, plaintext)
