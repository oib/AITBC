"""Edge proxy that routes messages into TEE-backed channels (Agent B v0.14.1 B2).

ponytail: This is an in-memory skeleton. Production needs a real TEE channel
(see `aitbc.tee.channel` once Agent A lands it) and an attested key-exchange
session before routing any plaintext.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ChannelStatus(StrEnum):
    """Status of a TEE-backed channel."""

    PENDING = "pending"
    OPEN = "open"
    CLOSED = "closed"


@dataclass
class TEEChannel:
    """In-memory TEE channel placeholder."""

    channel_id: str
    peer_id: str
    status: ChannelStatus = ChannelStatus.PENDING
    messages: list[dict[str, Any]] = field(default_factory=list)

    def post(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Queue a message on the channel and return delivery metadata."""
        envelope = {"channel_id": self.channel_id, "peer_id": self.peer_id, "payload": payload}
        self.messages.append(envelope)
        return {"delivered": True, "channel_id": self.channel_id, "sequence": len(self.messages) - 1}


class TEEProxy:
    """Edge-side proxy for routing traffic into TEE-backed channels."""

    def __init__(self) -> None:
        self.channels: dict[str, TEEChannel] = {}

    def register_channel(self, channel_id: str, peer_id: str) -> TEEChannel:
        """Register or retrieve a channel."""
        if channel_id not in self.channels:
            self.channels[channel_id] = TEEChannel(channel_id=channel_id, peer_id=peer_id)
        return self.channels[channel_id]

    def open_channel(self, channel_id: str) -> TEEChannel:
        """Mark a channel as open."""
        channel = self.channels[channel_id]
        channel.status = ChannelStatus.OPEN
        return channel

    def route_to_channel(self, channel_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Route a payload into an existing TEE channel."""
        if channel_id not in self.channels:
            raise KeyError(f"channel {channel_id} not registered")
        channel = self.channels[channel_id]
        if channel.status != ChannelStatus.OPEN:
            raise RuntimeError(f"channel {channel_id} is not open")
        return channel.post(payload)
