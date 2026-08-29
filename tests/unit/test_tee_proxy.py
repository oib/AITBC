"""Tests for the edge TEE proxy."""

from __future__ import annotations


from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from cryptography.hazmat.primitives.serialization import PrivateFormat
from edge_app.tee_proxy import TEEProxy


def _generate_peer_keypair() -> tuple[bytes, bytes]:
    private = X25519PrivateKey.generate()
    public = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    private_bytes = private.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return private_bytes, public


def test_tee_proxy_round_trip() -> None:
    """Two TEE proxies can exchange an encrypted payload."""
    peer_private, peer_public = _generate_peer_keypair()
    edge = TEEProxy(edge_id="edge-1")

    # Register channel with peer public key.
    edge.register_channel("ch-1", "peer-1", peer_public_key=peer_public)
    edge.open_channel("ch-1", peer_public_key=peer_public)

    payload = {"type": "heartbeat", "seq": 1}
    out = edge.route_to_channel("ch-1", payload)
    assert out["delivered"] is True
    assert out["channel_id"] == "ch-1"
    assert out["payload"] != payload

    # The peer can decrypt using its own channel constructed with the shared
    # secret. Build it from the edge public key in the proxy.
    peer_public_for_edge = edge.channels["ch-1"].session.initiator_public_key
    peer_proxy = TEEProxy(edge_id="peer-1")
    peer_proxy.register_channel("ch-1", "edge-1", peer_public_key=peer_public_for_edge)
    peer_proxy.channels["ch-1"].session.initiator_public_key = peer_public
    peer_proxy.channels["ch-1"].session.private_key = peer_private
    peer_proxy.open_channel("ch-1")

    decoded = peer_proxy.receive_from_channel(
        "ch-1",
        payload=out["payload"],
        nonce=out["nonce"],
    )
    assert decoded == payload
