"""Encrypted agent-to-agent channels bound to attested identities (v0.14.1 §A2).

``TEEChannel`` sends and receives messages through an established
``TEESession``. Messages are encrypted with AES-GCM using the session's
X25519 shared secret. Production TEEs should run the AEAD inside the enclave
so the shared secret never leaves the enclave boundary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .errors import TEEError
from .session import TEESession, SessionState, X25519_KEY_SIZE

#: AES-GCM nonce size in bytes.
GCM_NONCE_SIZE = 12


class ChannelState(StrEnum):
    """Lifecycle state of a TEE-backed channel."""

    PENDING = "pending"
    OPEN = "open"
    CLOSED = "closed"


@dataclass
class ChannelMessage:
    """A single encoded message on a channel."""

    message_id: str
    sender_id: str
    payload: bytes
    nonce: int
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class TEEChannel:
    """Channel bound to an established TEE session."""

    channel_id: str
    session: TEESession
    peer_id: str
    state: ChannelState | str = ChannelState.PENDING
    messages: list[ChannelMessage] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if isinstance(self.state, str):
            self.state = ChannelState(self.state)
        if not self.channel_id:
            raise ValueError("channel_id is required")
        if not self.peer_id:
            raise ValueError("peer_id is required")

    def open(self) -> None:
        """Open the channel once the underlying session is established."""
        if self.session.state != SessionState.ESTABLISHED:
            raise TEEError("cannot open channel: session not established")
        if len(self.session.shared_secret) != X25519_KEY_SIZE:
            raise TEEError("session shared secret is not a valid AES-GCM key")
        self.state = ChannelState.OPEN

    def close(self) -> None:
        """Close the channel."""
        self.state = ChannelState.CLOSED

    def _nonce_bytes(self, nonce: int) -> bytes:
        """Encode the integer nonce as a fixed-size AES-GCM nonce."""
        return nonce.to_bytes(GCM_NONCE_SIZE, "big")

    def encode(self, payload: bytes | str) -> ChannelMessage:
        """Encode a payload for the channel."""
        if self.state != ChannelState.OPEN:
            raise TEEError(f"cannot encode on channel in state {self.state}")
        if isinstance(payload, str):
            payload = payload.encode("utf-8")

        nonce = self.session.next_nonce()
        nonce_bytes = self._nonce_bytes(nonce)
        ciphertext = AESGCM(self.session.shared_secret).encrypt(nonce_bytes, payload, None)
        message = ChannelMessage(
            message_id=f"{self.channel_id}-{len(self.messages)}",
            sender_id=self.session.initiator_id,
            payload=ciphertext,
            nonce=nonce,
        )
        self.messages.append(message)
        return message

    def decode(self, message: ChannelMessage) -> bytes:
        """Decode a received message payload."""
        if self.state != ChannelState.OPEN:
            raise TEEError(f"cannot decode on channel in state {self.state}")
        nonce_bytes = self._nonce_bytes(message.nonce)
        return AESGCM(self.session.shared_secret).decrypt(nonce_bytes, message.payload, None)
