"""Edge proxy that routes messages into TEE-backed channels (Agent B v0.14.1 B2).

The proxy creates an X25519 ECDH session for each registered channel and uses
``aitbc.tee.TEEChannel`` for AES-GCM encryption. The peer's public key is
required before the channel can be opened; until then the channel remains
pending.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, cast

from aitbc.tee import ChannelState, TEEChannel, TEESession
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from cryptography.hazmat.primitives.serialization import PrivateFormat

X25519_KEY_SIZE = 32


def _generate_x25519_keypair() -> tuple[bytes, bytes]:
    """Return (private_key, public_key) as 32-byte raw X25519 key bytes."""
    private_key = X25519PrivateKey.generate()
    public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    private_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return private_bytes, public_key


@dataclass
class _ChannelInfo:
    """Internal state for a registered TEE channel."""

    peer_id: str
    session: TEESession
    channel: TEEChannel | None = None
    peer_public_key: bytes = b""


class TEEProxy:
    """Edge-side proxy for routing traffic into TEE-backed channels."""

    def __init__(self, edge_id: str = "edge") -> None:
        self.edge_id = edge_id
        self.channels: dict[str, _ChannelInfo] = {}

    def register_channel(
        self,
        channel_id: str,
        peer_id: str,
        peer_public_key: bytes | None = None,
    ) -> dict[str, Any]:
        """Register a channel and generate an ephemeral edge key pair.

        The channel cannot be opened until the peer's public key is known.
        """
        if channel_id in self.channels:
            info = self.channels[channel_id]
            if peer_public_key:
                info.peer_public_key = peer_public_key
                info.session.responder_public_key = peer_public_key
            return {
                "channel_id": channel_id,
                "peer_id": info.peer_id,
                "edge_public_key": info.session.initiator_public_key,
            }

        private_key, public_key = _generate_x25519_keypair()
        session = TEESession(
            session_id=channel_id,
            initiator_id=self.edge_id,
            responder_id=peer_id,
            initiator_public_key=public_key,
            responder_public_key=peer_public_key or b"",
            private_key=private_key,
        )
        self.channels[channel_id] = _ChannelInfo(
            peer_id=peer_id,
            session=session,
            peer_public_key=peer_public_key or b"",
        )
        return {
            "channel_id": channel_id,
            "peer_id": peer_id,
            "edge_public_key": public_key,
        }

    def open_channel(
        self,
        channel_id: str,
        peer_public_key: bytes | None = None,
    ) -> dict[str, Any]:
        """Open the channel once the peer's public key is known."""
        if channel_id not in self.channels:
            raise KeyError(f"channel {channel_id} not registered")

        info = self.channels[channel_id]
        if peer_public_key:
            info.peer_public_key = peer_public_key
            info.session.responder_public_key = peer_public_key

        if not info.session.responder_public_key:
            raise ValueError("peer_public_key is required to open a TEE channel")

        info.session.establish()
        info.channel = TEEChannel(
            channel_id=channel_id,
            session=info.session,
            peer_id=info.peer_id,
        )
        info.channel.open()
        return {
            "channel_id": channel_id,
            "peer_id": info.peer_id,
            "state": "open",
            "edge_public_key": info.session.initiator_public_key,
            "peer_public_key": info.session.responder_public_key,
        }

    def route_to_channel(self, channel_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Route a payload through an open TEE channel."""
        if channel_id not in self.channels:
            raise KeyError(f"channel {channel_id} not registered")
        info = self.channels[channel_id]
        if info.channel is None or info.channel.state != ChannelState.OPEN:
            raise RuntimeError(f"channel {channel_id} is not open")

        message = info.channel.encode(json.dumps(payload).encode("utf-8"))
        return {
            "delivered": True,
            "channel_id": channel_id,
            "sequence": len(info.channel.messages) - 1,
            "message_id": message.message_id,
            "nonce": message.nonce,
            "payload": message.payload,
        }

    def receive_from_channel(self, channel_id: str, payload: bytes, nonce: int) -> dict[str, Any]:
        """Decode a payload received from the peer through the channel."""
        if channel_id not in self.channels:
            raise KeyError(f"channel {channel_id} not registered")
        info = self.channels[channel_id]
        if info.channel is None or info.channel.state != ChannelState.OPEN:
            raise RuntimeError(f"channel {channel_id} is not open")

        from aitbc.tee import ChannelMessage

        message = ChannelMessage(
            message_id=f"{channel_id}-rx",
            sender_id=info.peer_id,
            payload=payload,
            nonce=nonce,
        )
        plaintext = info.channel.decode(message)
        return cast(dict[str, Any], json.loads(plaintext.decode("utf-8")))
