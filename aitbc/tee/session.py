"""Confidential messaging session with forward secrecy (v0.14.1 §A2).

Provides ``TEESession`` and ``SessionState`` primitives for key exchange,
replay-protected nonces, and shared-secret rotation. The shared-secret
derivation uses X25519 ECDH via the ``cryptography`` package; the caller is
responsible for supplying its own 32-byte private key and the peer's public
key. Production TEEs should perform key agreement inside the enclave so the
private key never leaves the enclave boundary.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey

from .errors import TEEError

#: X25519 keys are always 32 bytes.
X25519_KEY_SIZE = 32


class SessionState(StrEnum):
    """Lifecycle state of a TEE messaging session."""

    PENDING = "pending"
    ESTABLISHED = "established"
    CLOSED = "closed"
    EXPIRED = "expired"


@dataclass
class TEESession:
    """An attested agent-to-agent messaging session."""

    session_id: str
    initiator_id: str
    responder_id: str
    initiator_public_key: bytes
    responder_public_key: bytes = b""
    private_key: bytes = b""
    shared_secret: bytes = b""
    state: SessionState | str = SessionState.PENDING
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime = field(default_factory=lambda: datetime.now(UTC) + timedelta(hours=1))
    nonce_counter: int = 0
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if isinstance(self.state, str):
            self.state = SessionState(self.state)
        if not self.session_id:
            raise ValueError("session_id is required")
        if not self.initiator_id or not self.responder_id:
            raise ValueError("initiator_id and responder_id are required")
        if self.expires_at <= self.created_at:
            raise ValueError("expires_at must be after created_at")
        if self.private_key and len(self.private_key) != X25519_KEY_SIZE:
            raise ValueError(f"private_key must be {X25519_KEY_SIZE} bytes")
        if self.initiator_public_key and len(self.initiator_public_key) != X25519_KEY_SIZE:
            raise ValueError(f"initiator_public_key must be {X25519_KEY_SIZE} bytes")
        if self.responder_public_key and len(self.responder_public_key) != X25519_KEY_SIZE:
            raise ValueError(f"responder_public_key must be {X25519_KEY_SIZE} bytes")

    def is_expired(self, now: datetime | None = None) -> bool:
        """Return True if the session has expired."""
        if now is None:
            now = datetime.now(UTC)
        return self.expires_at <= now

    def establish(self) -> None:
        """Derive the shared secret once the responder public key is known."""
        if self.responder_public_key == b"":
            raise TEEError("responder_public_key is required to establish session")
        if self.private_key == b"":
            raise TEEError("private_key is required to establish session")

        our_private = X25519PrivateKey.from_private_bytes(self.private_key)
        our_public = our_private.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        if our_public == self.initiator_public_key:
            peer_public = self.responder_public_key
        elif our_public == self.responder_public_key:
            peer_public = self.initiator_public_key
        else:
            raise TEEError("private_key does not match either public key")

        peer = X25519PublicKey.from_public_bytes(peer_public)
        self.shared_secret = our_private.exchange(peer)
        self.state = SessionState.ESTABLISHED

    def rotate_key(self, new_ephemeral_public_key: bytes) -> bytes:
        """Rotate the shared secret for forward secrecy."""
        if self.state != SessionState.ESTABLISHED:
            raise TEEError(f"cannot rotate key in session state {self.state}")
        if not self.shared_secret:
            raise TEEError("no shared secret to rotate")

        if len(new_ephemeral_public_key) == X25519_KEY_SIZE:
            # Real ECDH rotation with a fresh ephemeral and the peer's new public key.
            ephemeral = X25519PrivateKey.generate()
            peer = X25519PublicKey.from_public_bytes(new_ephemeral_public_key)
            new_shared = ephemeral.exchange(peer)
            self.shared_secret = hashlib.sha256(self.shared_secret + new_shared).digest()
        else:
            # Fall back to using the provided bytes as entropy for older callers.
            self.shared_secret = hashlib.sha256(self.shared_secret + new_ephemeral_public_key).digest()
        return self.shared_secret

    def next_nonce(self) -> int:
        """Return an incrementing nonce for replay protection."""
        if self.state != SessionState.ESTABLISHED:
            raise TEEError("session must be established to generate nonces")
        self.nonce_counter += 1
        return self.nonce_counter

    def close(self) -> None:
        """Close the session and clear the shared secret."""
        self.state = SessionState.CLOSED
        self.shared_secret = b""
