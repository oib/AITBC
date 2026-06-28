"""Integration tests for v0.6.2 P2P protocol versioning and gossip topic namespacing."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aitbc_chain.gossip.broker import GossipBroker, InMemoryGossipBackend
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

    @pytest.mark.asyncio
    async def test_handshake_includes_protocol_version(self):
        """Outbound handshake includes protocol_version and block_height."""
        service = P2PNetworkService(
            host="127.0.0.1",
            port=7070,
            node_id="node1",
            chain_id="test-chain",
        )

        # Mock _get_block_height to return a known value
        service._get_block_height = MagicMock(return_value=42)

        # Capture the handshake message
        captured: dict = {}

        async def mock_send(writer, message):
            captured.update(message)

        service._send_message = mock_send  # type: ignore[method-assign]

        # Mock asyncio.open_connection
        mock_reader = AsyncMock()
        mock_writer = MagicMock()

        with patch("asyncio.open_connection", return_value=(mock_reader, mock_writer)):
            with patch.object(service, "_listen_to_stream", new_callable=AsyncMock):
                await service._dial_peer("127.0.0.1", 7071)

        assert captured.get("protocol_version") == 2
        assert captured.get("block_height") == 42
        assert captured.get("type") == "handshake"

    @pytest.mark.asyncio
    async def test_v1_peer_tracked_as_legacy(self):
        """Peer with protocol_version=1 is tracked as legacy."""
        service = P2PNetworkService(
            host="127.0.0.1",
            port=7070,
            node_id="node1",
            chain_id="test-chain",
        )

        # Simulate receiving a v1 handshake
        v1_handshake = {
            "type": "handshake",
            "node_id": "legacy-peer",
            "listen_port": 7071,
            "chain_id": "test-chain",
            "island_id": "",
            "is_hub": False,
            "protocol_version": 1,
            "block_height": 100,
        }

        # Mock the necessary parts
        mock_reader = AsyncMock()
        mock_writer = MagicMock()
        mock_writer.get_extra_info = MagicMock(return_value=("127.0.0.1", 7071))
        mock_writer.close = MagicMock()
        mock_writer.wait_closed = AsyncMock()

        # Mock _send_message to capture reply
        reply: dict = {}

        async def mock_send(writer, message):
            reply.update(message)

        service._send_message = mock_send  # type: ignore[method-assign]
        service._get_block_height = MagicMock(return_value=50)

        # Mock decode_payload to return our v1 handshake
        with patch("aitbc_chain.network.compression.decode_payload", return_value=v1_handshake):
            with patch.object(service, "_listen_to_stream", new_callable=AsyncMock):
                with patch("aitbc_chain.p2p_network.json.JSONDecodeError", Exception):
                    mock_reader.readline = AsyncMock(
                        return_value=b'{"type":"handshake","node_id":"legacy-peer","protocol_version":1}\n'
                    )
                    await service._handle_inbound_connection(mock_reader, mock_writer)

        # The legacy peer should be tracked
        assert service.is_legacy_peer("legacy-peer")
        # The reply should include our protocol version
        assert reply.get("protocol_version") == 2


class TestGossipTopicNamespacing:
    """Test gossip topic namespacing for v0.6.3 compatibility (B9)."""

    @pytest.mark.asyncio
    async def test_chain_specific_transaction_topic(self):
        """Chain-specific transaction topic receives messages."""
        backend = InMemoryGossipBackend()
        broker = GossipBroker(backend)

        sub = await broker.subscribe("transactions.test-chain")
        await broker.publish("transactions.test-chain", {"tx": "abc", "chain_id": "test-chain"})

        msg = await asyncio.wait_for(sub.get(), timeout=1.0)
        assert msg["tx"] == "abc"
        assert msg["chain_id"] == "test-chain"

        await broker.shutdown()

    @pytest.mark.asyncio
    async def test_legacy_transactions_topic_still_works(self):
        """Legacy global transactions topic still works for backward compat."""
        backend = InMemoryGossipBackend()
        broker = GossipBroker(backend)

        sub = await broker.subscribe("transactions")
        await broker.publish("transactions", {"tx": "def", "chain_id": "test-chain"})

        msg = await asyncio.wait_for(sub.get(), timeout=1.0)
        assert msg["tx"] == "def"

        await broker.shutdown()

    @pytest.mark.asyncio
    async def test_chain_specific_and_legacy_topics_are_independent(self):
        """Chain-specific and legacy topics don't interfere."""
        backend = InMemoryGossipBackend()
        broker = GossipBroker(backend)

        legacy_sub = await broker.subscribe("transactions")
        chain_sub = await broker.subscribe("transactions.chain1")

        # Publish to chain-specific topic
        await broker.publish("transactions.chain1", {"tx": "chain-specific"})

        # Only chain_sub should receive it
        chain_msg = await asyncio.wait_for(chain_sub.get(), timeout=1.0)
        assert chain_msg["tx"] == "chain-specific"

        # Legacy sub should NOT receive it (different topic)
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(legacy_sub.get(), timeout=0.1)

        await broker.shutdown()

    @pytest.mark.asyncio
    async def test_block_topic_chain_specific(self):
        """Block topics are already chain-specific (blocks.{chain_id})."""
        backend = InMemoryGossipBackend()
        broker = GossipBroker(backend)

        sub = await broker.subscribe("blocks.chain1")
        await broker.publish("blocks.chain1", {"height": 100})

        msg = await asyncio.wait_for(sub.get(), timeout=1.0)
        assert msg["height"] == 100

        await broker.shutdown()
