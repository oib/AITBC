"""Confidential messaging session with forward secrecy (v0.14.1 §A2).

Provides ``TEESession`` and ``SessionState`` primitives for key exchange,
replay-protected nonces, and shared-secret rotation. The shared-secret
derivation is a simulator-friendly hash; production code should use a real
Diffie-Hellman key agreement inside the enclave.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

from .errors import TEEError


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

    def is_expired(self, now: datetime | None = None) -> bool:
        """Return True if the session has expired."""
        if now is None:
            now = datetime.now(UTC)
        return self.expires_at <= now

    def establish(self) -> None:
        """Derive the shared secret once the responder public key is known."""
        if self.responder_public_key == b"":
            raise TEEError("responder_public_key is required to establish session")
        # ponytail: simulated ECDH; production should perform real DH inside the enclave.
        self.shared_secret = hashlib.sha256(self.initiator_public_key + self.responder_public_key).digest()
        self.state = SessionState.ESTABLISHED

    def rotate_key(self, new_ephemeral_public_key: bytes) -> bytes:
        """Rotate the shared secret for forward secrecy."""
        if self.state != SessionState.ESTABLISHED:
            raise TEEError(f"cannot rotate key in session state {self.state}")
        if not self.shared_secret:
            raise TEEError("no shared secret to rotate")
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
