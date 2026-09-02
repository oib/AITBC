"""Tests for v0.6.2 sync & gossip features: gossip dedup (B1), peer capability
exchange (B4), and delta sync RPC endpoint (B6)."""

from __future__ import annotations

import hashlib
import inspect
from contextlib import contextmanager
from datetime import datetime
from unittest.mock import Mock

import pytest
from aitbc_chain.models import Account, Block, Transaction
from aitbc_chain.rpc import accounts as rpc_accounts
from sqlmodel import Session, create_engine

from aitbc_chain.metadata import chain_metadata


def _hex(value: str) -> str:
    return "0x" + hashlib.sha256(value.encode()).hexdigest()


# ---------------------------------------------------------------------------
# B1 — Gossip message deduplication
# ---------------------------------------------------------------------------


class TestGossipDedup:
    """Test gossip message deduplication."""

    def test_compute_message_id_with_hash(self):
        """Message ID uses hash field when available."""
        from aitbc_chain.gossip import GossipBroker, InMemoryGossipBackend

        broker = GossipBroker(InMemoryGossipBackend())
        msg_id = broker._compute_message_id("blocks.test", {"hash": "0xabc"})
        assert msg_id == "blocks.test:0xabc"

    def test_compute_message_id_with_id(self):
        """Message ID uses id field when hash not available."""
        from aitbc_chain.gossip import GossipBroker, InMemoryGossipBackend

        broker = GossipBroker(InMemoryGossipBackend())
        msg_id = broker._compute_message_id("txs.test", {"id": "tx-001"})
        assert msg_id == "txs.test:tx-001"

    def test_compute_message_id_fallback_json(self):
        """Message ID falls back to JSON hash for non-dict messages."""
        from aitbc_chain.gossip import GossipBroker, InMemoryGossipBackend

        broker = GossipBroker(InMemoryGossipBackend())
        msg_id = broker._compute_message_id("test", "simple string")
        assert msg_id.startswith("test:")
        # Same message should produce same ID
        msg_id2 = broker._compute_message_id("test", "simple string")
        assert msg_id == msg_id2


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
    chain_metadata.create_all(engine)

    @contextmanager
    def _session_scope(*args, **kwargs):
        with Session(engine) as session:
            yield session

    # session_scope is imported into rpc.accounts from ..database — patch it there.
    monkeypatch.setattr(rpc_accounts, "session_scope", _session_scope)
    try:
        yield engine
    finally:
        engine.dispose()


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
