"""Encrypted agent-to-agent channels bound to attested identities (v0.14.1 §A2).

``TEEChannel`` sends and receives messages through an established
``TEESession``. The actual encryption is a simulator placeholder; production
relies on AES-GCM or ChaCha20-Poly1305 inside the TEE using the shared secret.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from .errors import TEEError
from .session import TEESession, SessionState


class ChannelState(StrEnum):
    """Lifecycle state of a TEE-backed channel."""

    PENDING = "pending"
    OPEN = "open"
    CLOSED = "closed"


@dataclass
class TEEMessage:
    """A single encrypted message on a TEE channel."""

    message_id: str
    sender_id: str
    payload: bytes
    nonce: int
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class TEEChannel:
    """Encrypted channel bound to an established TEE session."""

    channel_id: str
    session: TEESession
    peer_id: str
    state: ChannelState | str = ChannelState.PENDING
    messages: list[TEEMessage] = field(default_factory=list)
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
        self.state = ChannelState.OPEN

    def close(self) -> None:
        """Close the channel."""
        self.state = ChannelState.CLOSED

    def send(self, payload: bytes | str) -> TEEMessage:
        """Send an encrypted message on the channel."""
        if self.state != ChannelState.OPEN:
            raise TEEError(f"cannot send on channel in state {self.state}")
        if isinstance(payload, str):
            payload = payload.encode("utf-8")
        # ponytail: base64 placeholder for enclave-side authenticated encryption.
        ciphertext = base64.b64encode(payload)
        message = TEEMessage(
            message_id=f"{self.channel_id}-{len(self.messages)}",
            sender_id=self.session.initiator_id,
            payload=ciphertext,
            nonce=self.session.next_nonce(),
        )
        self.messages.append(message)
        return message

    def receive(self, message: TEEMessage) -> bytes:
        """Decrypt and return a received message payload."""
        if self.state != ChannelState.OPEN:
            raise TEEError(f"cannot receive on channel in state {self.state}")
        return base64.b64decode(message.payload)
