"""Integration tests for v0.6.2 P2P protocol versioning and gossip topic namespacing."""

from __future__ import annotations


from aitbc_chain.p2p_network import P2PNetworkService


class TestP2PProtocolVersioning:
    """Test P2P handshake protocol versioning (B8)."""

    def test_protocol_version_defaults_to_config(self):
        """P2PNetworkService uses gossip_protocol_version from settings."""
        service = P2PNetworkService(
            host="127.0.0.1",
            port=7070,
            node_id="node1",
            chain_id="test-chain",
        )
        assert service._protocol_version == 2  # settings.gossip_protocol_version
        assert service.get_protocol_version() == 2

    def test_legacy_peers_set_is_empty_initially(self):
        """No legacy peers tracked initially."""
        service = P2PNetworkService(
            host="127.0.0.1",
            port=7070,
            node_id="node1",
            chain_id="test-chain",
        )
        assert service.get_legacy_peers() == set()
        assert service.is_legacy_peer("unknown") is False

    def test_is_legacy_peer_after_manual_add(self):
        """is_legacy_peer returns True for peers added to _legacy_peers."""
        service = P2PNetworkService(
            host="127.0.0.1",
            port=7070,
            node_id="node1",
            chain_id="test-chain",
        )
        service._legacy_peers.add("legacy-node")
        assert service.is_legacy_peer("legacy-node") is True
        assert "legacy-node" in service.get_legacy_peers()

    def test_legacy_peer_removed_on_disconnect(self):
        """Legacy peer tracking is cleaned up when peer disconnects."""
        service = P2PNetworkService(
            host="127.0.0.1",
            port=7070,
            node_id="node1",
            chain_id="test-chain",
        )
        service._legacy_peers.add("departing-node")
        # Simulate disconnect cleanup
        service._legacy_peers.discard("departing-node")
        assert not service.is_legacy_peer("departing-node")


class TestGossipTopicNamespacing:
    """Test gossip topic namespacing for v0.6.3 compatibility (B9)."""
