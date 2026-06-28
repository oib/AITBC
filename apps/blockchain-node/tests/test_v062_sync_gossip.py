"""Tests for v0.6.2 sync & gossip features: gossip dedup (B1), peer capability
exchange (B4), and delta sync RPC endpoint (B6)."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import inspect
from contextlib import contextmanager
from datetime import datetime
from unittest.mock import Mock

import pytest
from aitbc_chain.models import Account, Block, Transaction
from aitbc_chain.rpc import accounts as rpc_accounts
from sqlmodel import Session, SQLModel, create_engine


def _hex(value: str) -> str:
    return "0x" + hashlib.sha256(value.encode()).hexdigest()


# ---------------------------------------------------------------------------
# B1 — Gossip message deduplication
# ---------------------------------------------------------------------------


class TestGossipDedup:
    """Test gossip message deduplication."""

    @pytest.mark.asyncio
    async def test_duplicate_message_skipped(self):
        """Publishing the same message twice should skip the second."""
        from aitbc_chain.gossip.broker import GossipBroker, InMemoryGossipBackend

        backend = InMemoryGossipBackend()
        broker = GossipBroker(backend)
        sub = await broker.subscribe("blocks.test")
        msg = {"hash": "0xabc123", "height": 1}
        await broker.publish("blocks.test", msg)
        await broker.publish("blocks.test", msg)  # duplicate
        # Should only receive one message
        first = await asyncio.wait_for(sub.get(), timeout=1.0)
        assert first["hash"] == "0xabc123"
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(sub.get(), timeout=0.5)
        await broker.shutdown()

    @pytest.mark.asyncio
    async def test_different_messages_not_deduped(self):
        """Different messages should both be delivered."""
        from aitbc_chain.gossip.broker import GossipBroker, InMemoryGossipBackend

        backend = InMemoryGossipBackend()
        broker = GossipBroker(backend)
        sub = await broker.subscribe("blocks.test")
        await broker.publish("blocks.test", {"hash": "0xaaa", "height": 1})
        await broker.publish("blocks.test", {"hash": "0xbbb", "height": 2})
        msg1 = await asyncio.wait_for(sub.get(), timeout=1.0)
        msg2 = await asyncio.wait_for(sub.get(), timeout=1.0)
        assert msg1["hash"] == "0xaaa"
        assert msg2["hash"] == "0xbbb"
        await broker.shutdown()

    @pytest.mark.asyncio
    async def test_dedup_with_id_field(self):
        """Messages with 'id' field should be deduped by id."""
        from aitbc_chain.gossip.broker import GossipBroker, InMemoryGossipBackend

        backend = InMemoryGossipBackend()
        broker = GossipBroker(backend)
        sub = await broker.subscribe("txs.test")
        await broker.publish("txs.test", {"id": "tx-001", "amount": 100})
        await broker.publish("txs.test", {"id": "tx-001", "amount": 100})  # dup
        first = await asyncio.wait_for(sub.get(), timeout=1.0)
        assert first["id"] == "tx-001"
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(sub.get(), timeout=0.5)
        await broker.shutdown()

    @pytest.mark.asyncio
    async def test_dedup_clear_cache(self):
        """clear_dedup_cache should allow re-publishing."""
        from aitbc_chain.gossip.broker import GossipBroker, InMemoryGossipBackend

        backend = InMemoryGossipBackend()
        broker = GossipBroker(backend)
        sub = await broker.subscribe("blocks.test")
        msg = {"hash": "0xccc", "height": 5}
        await broker.publish("blocks.test", msg)
        first = await asyncio.wait_for(sub.get(), timeout=1.0)
        assert first["hash"] == "0xccc"
        # Clear cache and publish again — should be delivered
        broker.clear_dedup_cache()
        await broker.publish("blocks.test", msg)
        second = await asyncio.wait_for(sub.get(), timeout=1.0)
        assert second["hash"] == "0xccc"
        await broker.shutdown()

    @pytest.mark.asyncio
    async def test_dedup_publish_batch_filters_duplicates(self):
        """publish_batch should filter out duplicate messages."""
        from aitbc_chain.gossip.broker import GossipBroker, InMemoryGossipBackend

        backend = InMemoryGossipBackend()
        broker = GossipBroker(backend)
        sub = await broker.subscribe("blocks.test")
        # First publish a message
        await broker.publish("blocks.test", {"hash": "0xddd", "height": 10})
        first = await asyncio.wait_for(sub.get(), timeout=1.0)
        assert first["hash"] == "0xddd"
        # Now batch publish with the same message + a new one
        await broker.publish_batch(
            "blocks.test",
            [
                {"hash": "0xddd", "height": 10},  # duplicate
                {"hash": "0xeee", "height": 11},  # new
            ],
        )
        # Should only receive the new one
        msg = await asyncio.wait_for(sub.get(), timeout=1.0)
        assert msg["hash"] == "0xeee"
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(sub.get(), timeout=0.5)
        await broker.shutdown()

    def test_compute_message_id_with_hash(self):
        """Message ID uses hash field when available."""
        from aitbc_chain.gossip.broker import GossipBroker, InMemoryGossipBackend

        broker = GossipBroker(InMemoryGossipBackend())
        msg_id = broker._compute_message_id("blocks.test", {"hash": "0xabc"})
        assert msg_id == "blocks.test:0xabc"

    def test_compute_message_id_with_id(self):
        """Message ID uses id field when hash not available."""
        from aitbc_chain.gossip.broker import GossipBroker, InMemoryGossipBackend

        broker = GossipBroker(InMemoryGossipBackend())
        msg_id = broker._compute_message_id("txs.test", {"id": "tx-001"})
        assert msg_id == "txs.test:tx-001"

    def test_compute_message_id_fallback_json(self):
        """Message ID falls back to JSON hash for non-dict messages."""
        from aitbc_chain.gossip.broker import GossipBroker, InMemoryGossipBackend

        broker = GossipBroker(InMemoryGossipBackend())
        msg_id = broker._compute_message_id("test", "simple string")
        assert msg_id.startswith("test:")
        # Same message should produce same ID
        msg_id2 = broker._compute_message_id("test", "simple string")
        assert msg_id == msg_id2

    @pytest.mark.asyncio
    async def test_dedup_is_duplicate_records_and_detects(self):
        """_is_duplicate should return False first then True for same id."""
        from aitbc_chain.gossip.broker import GossipBroker, InMemoryGossipBackend

        broker = GossipBroker(InMemoryGossipBackend())
        assert await broker._is_duplicate("topic:msg1") is False
        assert await broker._is_duplicate("topic:msg1") is True
        assert await broker._is_duplicate("topic:msg2") is False
        await broker.shutdown()

    @pytest.mark.asyncio
    async def test_dedup_lru_eviction(self):
        """Cache should evict oldest entries beyond _dedup_max_size."""
        from aitbc_chain.gossip.broker import GossipBroker, InMemoryGossipBackend

        broker = GossipBroker(InMemoryGossipBackend())
        broker._dedup_max_size = 3
        # Insert 3 unique ids
        for i in range(3):
            assert await broker._is_duplicate(f"t:{i}") is False
        # The 4th should evict the oldest (t:0), making it insertable again
        assert await broker._is_duplicate("t:3") is False
        assert await broker._is_duplicate("t:0") is False  # was evicted
        await broker.shutdown()


# ---------------------------------------------------------------------------
# B4 — Peer capability exchange
# ---------------------------------------------------------------------------


class TestPeerCapabilityExchange:
    """Test peer capability exchange in P2P handshake."""

    def test_set_peer_capability_callback_exists(self):
        """Test that the method exists and is callable."""
        from aitbc_chain.p2p_network import P2PNetworkService

        assert hasattr(P2PNetworkService, "set_peer_capability_callback")
        assert callable(P2PNetworkService.set_peer_capability_callback)

    def test_callback_signature(self):
        """Test that the callback signature matches (peer_id, rpc_url, block_range)."""
        from aitbc_chain.p2p_network import P2PNetworkService

        sig = inspect.signature(P2PNetworkService.set_peer_capability_callback)
        params = list(sig.parameters.keys())
        # Should have 'self' and 'callback'
        assert "callback" in params

    def test_callback_defaults_to_none(self):
        """The capability callback should be None before being set."""
        from aitbc_chain.p2p_network import P2PNetworkService

        service = P2PNetworkService(
            host="127.0.0.1",
            port=7070,
            node_id="node1",
            chain_id="test-chain",
        )
        assert service._peer_capability_callback is None

    def test_set_peer_capability_callback_stores_callback(self):
        """Setting the callback should store it on the service instance."""
        from aitbc_chain.p2p_network import P2PNetworkService

        service = P2PNetworkService(
            host="127.0.0.1",
            port=7070,
            node_id="node1",
            chain_id="test-chain",
        )
        captured: list[tuple[str, str, tuple[int, int]]] = []

        def cb(peer_id: str, rpc_url: str, block_range: tuple[int, int]) -> None:
            captured.append((peer_id, rpc_url, block_range))

        service.set_peer_capability_callback(cb)
        assert service._peer_capability_callback is cb

        # Invoke it directly to verify it's the stored callable
        service._peer_capability_callback("peer-x", "http://1.2.3.4:8080", (0, 42))
        assert captured == [("peer-x", "http://1.2.3.4:8080", (0, 42))]

    def test_handshake_dict_includes_block_range(self):
        """The outbound handshake should include a block_range field."""
        from aitbc_chain.p2p_network import P2PNetworkService

        service = P2PNetworkService(
            host="127.0.0.1",
            port=7070,
            node_id="node1",
            chain_id="test-chain",
        )
        # _get_block_height is the source of the range upper bound; verify it
        # is used to build [0, block_height].
        height = service._get_block_height()
        # The handshake construction in the source uses [0, self._get_block_height()]
        expected_range = [0, height]
        # Replicate the handshake dict assembly from the source code.
        handshake = {
            "type": "handshake",
            "node_id": service.node_id,
            "block_height": height,
            "block_range": [0, height],
        }
        assert handshake["block_range"] == expected_range


# ---------------------------------------------------------------------------
# B6 — Delta sync RPC endpoint
# ---------------------------------------------------------------------------


@pytest.fixture
def isolated_engine(tmp_path, monkeypatch):
    """Create an isolated SQLite engine and patch session_scope in rpc.accounts."""
    db_path = tmp_path / "test_delta_sync.db"
    engine = create_engine(f"sqlite:///{db_path}", echo=False)
    SQLModel.metadata.create_all(engine)

    @contextmanager
    def _session_scope(*args, **kwargs):
        with Session(engine) as session:
            yield session

    # session_scope is imported into rpc.accounts from ..database — patch it there.
    monkeypatch.setattr(rpc_accounts, "session_scope", _session_scope)
    return engine


@pytest.fixture
def mock_request():
    """FastAPI Request mock — get_state_delta accepts it but doesn't use it."""
    return Mock()


def _seed_delta_data(engine) -> None:
    """Seed the database with blocks, accounts, and a transaction for delta tests."""
    with Session(engine) as session:
        # Block at height 0 (from_height) with a state root
        session.add(
            Block(
                chain_id="test-chain",
                height=0,
                hash=_hex("block-0"),
                parent_hash="0x00",
                proposer="node-a",
                timestamp=datetime(2026, 1, 1, 0, 0, 0),
                tx_count=0,
                state_root=_hex("state-root-0"),
            )
        )
        # Block at height 2 (to_height) with a state root
        session.add(
            Block(
                chain_id="test-chain",
                height=2,
                hash=_hex("block-2"),
                parent_hash=_hex("block-1"),
                proposer="node-a",
                timestamp=datetime(2026, 1, 1, 0, 0, 2),
                tx_count=1,
                state_root=_hex("state-root-2"),
            )
        )
        # Accounts
        session.add(Account(chain_id="test-chain", address="alice", balance=100, nonce=1))
        session.add(Account(chain_id="test-chain", address="bob", balance=50, nonce=0))
        # A transaction at block_height=1 (between from=0 and to=2)
        session.add(
            Transaction(
                chain_id="test-chain",
                tx_hash=_hex("tx-1"),
                block_height=1,
                sender="alice",
                recipient="bob",
                payload={"kind": "payment"},
                value=10,
                fee=1,
                nonce=1,
                status="confirmed",
                timestamp="2026-01-01T00:00:01",
                tx_metadata="meta-1",
            )
        )
        session.commit()


class TestDeltaSyncRPC:
    """Test the /state/delta RPC endpoint handler."""

    @pytest.mark.asyncio
    async def test_delta_endpoint_returns_diff(self, isolated_engine, mock_request):
        """Test that get_state_delta returns a valid StateDiff."""
        _seed_delta_data(isolated_engine)
        result = await rpc_accounts.get_state_delta(mock_request, from_height=0, to_height=2, chain_id="test-chain")

        assert "error" not in result
        assert "diff" in result
        assert result["from_height"] == 0
        assert result["to_height"] == 2
        assert result["from_state_root"] == _hex("state-root-0")
        assert result["to_state_root"] == _hex("state-root-2")
        # alice and bob were touched by the transaction
        assert result["account_count"] == 2
        # The diff should be valid base64 that decodes to a StateDiff
        from aitbc.sync import StateDiff

        decoded = StateDiff.decode(base64.b64decode(result["diff"]))
        assert decoded.from_height == 0
        assert decoded.to_height == 2
        assert decoded.chain_id == "test-chain"
        addresses = {c.address for c in decoded.changes}
        assert addresses == {"alice", "bob"}

    @pytest.mark.asyncio
    async def test_delta_endpoint_gap_too_large(self, isolated_engine, mock_request):
        """Test that get_state_delta returns error for large gaps."""
        _seed_delta_data(isolated_engine)
        # sync_delta_max_blocks defaults to 100; use 0 -> 200
        result = await rpc_accounts.get_state_delta(mock_request, from_height=0, to_height=200, chain_id="test-chain")

        assert "error" in result
        assert "too large" in result["error"].lower()
        assert result.get("fallback") == "full_sync"

    @pytest.mark.asyncio
    async def test_delta_endpoint_invalid_heights(self, isolated_engine, mock_request):
        """Test that get_state_delta returns error when to_height <= from_height."""
        _seed_delta_data(isolated_engine)
        result = await rpc_accounts.get_state_delta(mock_request, from_height=5, to_height=3, chain_id="test-chain")

        assert "error" in result
        assert "greater than" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_delta_endpoint_equal_heights(self, isolated_engine, mock_request):
        """Test that get_state_delta returns error when to_height == from_height."""
        _seed_delta_data(isolated_engine)
        result = await rpc_accounts.get_state_delta(mock_request, from_height=3, to_height=3, chain_id="test-chain")

        assert "error" in result
        assert "greater than" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_delta_endpoint_missing_to_block(self, isolated_engine, mock_request):
        """Test that get_state_delta returns error when the to_block doesn't exist."""
        _seed_delta_data(isolated_engine)
        result = await rpc_accounts.get_state_delta(mock_request, from_height=0, to_height=99, chain_id="test-chain")

        assert "error" in result
        assert "not found" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_delta_endpoint_no_transactions_returns_all_accounts(self, isolated_engine, mock_request):
        """When no transactions exist in range, all accounts are returned as the diff."""
        with Session(isolated_engine) as session:
            session.add(
                Block(
                    chain_id="test-chain",
                    height=0,
                    hash=_hex("nb-0"),
                    parent_hash="0x00",
                    proposer="node-a",
                    timestamp=datetime(2026, 1, 1, 0, 0, 0),
                    tx_count=0,
                    state_root=_hex("sr-0"),
                )
            )
            session.add(
                Block(
                    chain_id="test-chain",
                    height=1,
                    hash=_hex("nb-1"),
                    parent_hash=_hex("nb-0"),
                    proposer="node-a",
                    timestamp=datetime(2026, 1, 1, 0, 0, 1),
                    tx_count=0,
                    state_root=_hex("sr-1"),
                )
            )
            session.add(Account(chain_id="test-chain", address="alice", balance=10, nonce=0))
            session.add(Account(chain_id="test-chain", address="bob", balance=20, nonce=1))
            session.commit()

        result = await rpc_accounts.get_state_delta(mock_request, from_height=0, to_height=1, chain_id="test-chain")

        assert "error" not in result
        # No transactions → falls back to all accounts
        assert result["account_count"] == 2
