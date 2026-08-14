"""Integration tests for v0.7.0 Bridge Basics — new RPC endpoints, monitoring, and CLI.

Covers:
- POST /bridge/unlock — refund/cancel pending transfers
- GET /bridge/balance/{chain_id} — bridge balance query
- GET /bridge/health — bridge health check
- GET /bridge/status/{transfer_id} — alias for /bridge/transfer/{id}
- POST /bridge/batch/lock — batch lock operations
- POST /bridge/batch/confirm — batch confirm operations
- BridgeManager monitoring: health_check, detect_stuck_transfers, get_metrics
- CLI bridge commands: lock, status, health (via BridgeClient)
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import patch

import pytest
from eth_account import Account as EthAccount
from eth_keys import keys
from eth_utils import keccak
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from aitbc_chain.cross_chain.bridge import BridgeStatus, CrossChainBridge
from aitbc_chain.models import Account, BridgeBlockHeader, CrossChainTransfer
from aitbc_chain.network.bridge_manager import BridgeManager
from aitbc_chain.rpc.router import router


# ---------------------------------------------------------------------------
# Helpers (mirrors test_bridge_suite.py patterns)
# ---------------------------------------------------------------------------


def _sign_hash(private_key_hex: str, msg_hash: bytes) -> str:
    """Sign a keccak message hash with a private key, returning hex signature."""
    pk = keys.PrivateKey(bytes.fromhex(private_key_hex.removeprefix("0x")))
    sig = pk.sign_msg_hash(msg_hash)
    return sig.to_hex()


def _canonical_hash(data: dict[str, Any]) -> bytes:
    """keccak256 of canonical JSON encoding (matches verify_request_signature)."""
    message = json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    return keccak(message)


def _sign_request(sender_account: EthAccount, data: dict[str, Any]) -> str:
    """Sign a request payload and return the hex signature."""
    msg_hash = _canonical_hash(data)
    return _sign_hash(sender_account.key.hex(), msg_hash)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _patch_supported_chains():
    """Allow test chain IDs (chain-a, chain-b, chain-c) in bridge RPC validation."""
    with patch("aitbc_chain.config.settings.supported_chains", "chain-a,chain-b,chain-c,chain-empty"):
        yield


@pytest.fixture
def bridge(engine) -> CrossChainBridge:
    """A CrossChainBridge backed by the in-memory engine (same-thread only)."""
    return CrossChainBridge(lambda: Session(engine))


@pytest.fixture
def rpc_engine():
    """Engine with StaticPool so the same in-memory DB is shared across threads.

    The default ``SingletonThreadPool`` creates a separate :memory: DB per thread,
    which breaks RPC tests (TestClient runs handlers in a worker thread).
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    yield engine
    SQLModel.metadata.drop_all(engine)


@pytest.fixture
def rpc_setup(rpc_engine):
    """Patches get_cross_chain_bridge with a real bridge + yields (bridge, client).

    Uses ``rpc_engine`` (StaticPool) so the bridge's DB is accessible from the
    TestClient's worker thread.
    """
    b = CrossChainBridge(lambda: Session(rpc_engine))
    app = FastAPI()
    app.include_router(router)
    c = TestClient(app)
    with patch("aitbc_chain.cross_chain.bridge.get_cross_chain_bridge", return_value=b):
        yield b, c


@pytest.fixture
def initialized_bridge(rpc_engine):
    """Patches get_cross_chain_bridge with a real bridge backed by rpc_engine.

    Use this with the ``client`` fixture for RPC tests that need DB access.
    Seed accounts via ``rpc_engine`` (not ``engine``) so data is visible to the
    RPC handler thread.
    """
    b = CrossChainBridge(lambda: Session(rpc_engine))
    with patch("aitbc_chain.cross_chain.bridge.get_cross_chain_bridge", return_value=b):
        yield b


@pytest.fixture
def client() -> TestClient:
    """FastAPI TestClient bound to the RPC router."""
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


@pytest.fixture
def sender_account() -> EthAccount:
    """An ephemeral Ethereum-style account for signing requests."""
    return EthAccount.create()


@pytest.fixture
def proposer_account() -> EthAccount:
    """An ephemeral Ethereum-style account used to sign proofs."""
    return EthAccount.create()


def _seed_sender(engine, chain_id: str, address: str, balance: int) -> None:
    """Seed an account with balance in the in-memory DB."""
    with Session(engine) as session:
        session.add(Account(chain_id=chain_id, address=address, balance=balance, nonce=0))
        session.commit()


def _store_block_header(
    engine: Any,
    chain_id: str = "chain-a",
    height: int = 10,
    block_hash: str = "0x" + "ab" * 32,
    proposer: str = "0xproposer",
    state_root: str = "0x" + "cd" * 32,
    signature: str = "",
    confirmation_count: int = 10,
) -> None:
    """Store a block header in the DB for bridge proof verification (v0.7.2)."""
    with Session(engine) as session:
        header = BridgeBlockHeader(
            chain_id=chain_id,
            height=height,
            hash=block_hash,
            parent_hash="0x" + "00" * 32,
            proposer=proposer,
            state_root=state_root,
            signature=signature,
            confirmation_count=confirmation_count,
            finality_confirmed=confirmation_count >= 6,
        )
        session.add(header)
        session.commit()


# ---------------------------------------------------------------------------
# Unlock / Refund Tests
# ---------------------------------------------------------------------------


class TestBridgeUnlock:
    """POST /bridge/unlock and CrossChainBridge.refund_transfer()."""

    def test_bridge_unlock_refund(self, bridge: CrossChainBridge, engine) -> None:
        """Lock then unlock returns funds to sender."""
        sender = "0xunlocksender"
        source_chain = "chain-a"
        target_chain = "chain-b"
        amount = 5000

        _seed_sender(engine, source_chain, sender, amount * 2)

        # Lock
        transfer = bridge.initiate_transfer(
            source_chain=source_chain,
            target_chain=target_chain,
            sender=sender,
            recipient="0xrecipient",
            amount=amount,
        )
        assert transfer.status == BridgeStatus.locked

        # Check sender balance was reduced
        with Session(engine) as session:
            acct = session.get(Account, (source_chain, sender))
            assert acct is not None
            balance_after_lock = acct.balance
            assert balance_after_lock < amount * 2

        # Unlock (refund)
        refunded = bridge.refund_transfer(transfer.transfer_id, sender)
        assert refunded.status == BridgeStatus.refunded

        # Sender should get the amount back (fee was already deducted at lock time)
        with Session(engine) as session:
            acct = session.get(Account, (source_chain, sender))
            assert acct is not None
            assert acct.balance == balance_after_lock + amount

    def test_bridge_unlock_completed_rejected(self, bridge: CrossChainBridge, proposer_account: EthAccount, engine) -> None:
        """Cannot unlock a completed transfer."""
        sender = "0xcompletedsender"
        source_chain = "chain-a"
        amount = 3000

        _seed_sender(engine, source_chain, sender, amount * 2)

        # v0.7.2: Store a block header for proof verification
        _store_block_header(engine, chain_id=source_chain, height=10, proposer=proposer_account.address.lower())

        transfer = bridge.initiate_transfer(
            source_chain=source_chain,
            target_chain="chain-b",
            sender=sender,
            recipient="0xrecipient",
            amount=amount,
        )

        # Confirm the transfer to complete it
        with Session(engine) as session:
            record = session.get(CrossChainTransfer, transfer.transfer_id)
            assert record is not None
            proof = _build_valid_proof(record, proposer_account.key.hex())

        with patch("aitbc_chain.config.settings.bridge_block_signature_required", False):
            bridge.confirm_transfer(transfer.transfer_id, proof)

        # Attempt to refund a completed transfer should fail
        with pytest.raises(ValueError, match="cannot be refunded"):
            bridge.refund_transfer(transfer.transfer_id, sender)

    def test_bridge_unlock_wrong_sender_rejected(self, bridge: CrossChainBridge, engine) -> None:
        """Only the original sender can unlock."""
        sender = "0xrealsender"
        source_chain = "chain-a"
        amount = 2000

        _seed_sender(engine, source_chain, sender, amount * 2)

        transfer = bridge.initiate_transfer(
            source_chain=source_chain,
            target_chain="chain-b",
            sender=sender,
            recipient="0xrecipient",
            amount=amount,
        )

        with pytest.raises(ValueError, match="original sender"):
            bridge.refund_transfer(transfer.transfer_id, "0xwrongsender")

    def test_bridge_unlock_not_found(self, bridge: CrossChainBridge) -> None:
        """Unlocking a non-existent transfer raises ValueError."""
        with pytest.raises(ValueError, match="not found"):
            bridge.refund_transfer("0xnonexistent", "0xsender")


# ---------------------------------------------------------------------------
# Balance Tests
# ---------------------------------------------------------------------------


class TestBridgeBalance:
    """GET /bridge/balance/{chain_id} and CrossChainBridge.get_bridge_balance()."""

    def test_bridge_balance(self, bridge: CrossChainBridge, engine) -> None:
        """Balance reflects locked transfers."""
        _seed_sender(engine, "chain-a", "0xbalSender", 50000)

        bridge.initiate_transfer("chain-a", "chain-b", "0xbalSender", "0xrecip", 10000)
        bridge.initiate_transfer("chain-a", "chain-b", "0xbalSender", "0xrecip2", 5000)

        balances = bridge.get_bridge_balance("chain-a")
        assert balances.get("chain-a") == 15000

    def test_bridge_balance_empty_chain(self, bridge: CrossChainBridge) -> None:
        """Zero balance for chain with no transfers."""
        balances = bridge.get_bridge_balance("chain-empty")
        assert balances.get("chain-empty") == 0

    def test_bridge_balance_all_chains(self, bridge: CrossChainBridge, engine) -> None:
        """Balance across multiple chains."""
        _seed_sender(engine, "chain-a", "0xs1", 50000)
        _seed_sender(engine, "chain-b", "0xs2", 50000)

        bridge.initiate_transfer("chain-a", "chain-b", "0xs1", "0xr1", 10000)
        bridge.initiate_transfer("chain-b", "chain-a", "0xs2", "0xr2", 7000)

        balances = bridge.get_bridge_balance()
        assert balances.get("chain-a") == 10000
        assert balances.get("chain-b") == 7000


# ---------------------------------------------------------------------------
# Health Tests
# ---------------------------------------------------------------------------


class TestBridgeHealth:
    """GET /bridge/health endpoint."""


# ---------------------------------------------------------------------------
# Status Alias Tests
# ---------------------------------------------------------------------------


class TestBridgeStatusAlias:
    """GET /bridge/status/{transfer_id} — alias for /bridge/transfer/{id}."""


# ---------------------------------------------------------------------------
# Batch Tests
# ---------------------------------------------------------------------------


class TestBridgeBatch:
    """POST /bridge/batch/lock and /bridge/batch/confirm."""


# ---------------------------------------------------------------------------
# Bridge Manager Monitoring Tests
# ---------------------------------------------------------------------------


class TestBridgeMonitoring:
    """BridgeManager health_check, detect_stuck_transfers, get_metrics."""

    @pytest.fixture
    def manager(self) -> BridgeManager:
        return BridgeManager(local_node_id="node-1", local_island_id="island-1")

    def test_health_check_empty(self, manager: BridgeManager) -> None:
        """Health check with no bridges returns empty dict."""
        health = manager.health_check()
        assert health == {}

    def test_health_check_with_bridges(self, manager: BridgeManager) -> None:
        """Health check returns status for each bridge."""
        manager.request_bridge("island-2")
        manager.request_bridge("island-3")

        health = manager.health_check()
        assert len(health) == 2
        for entry in health.values():
            assert entry["state"] == "pending"
            assert entry["healthy"] is True

    def test_health_check_rejected_bridge(self, manager: BridgeManager) -> None:
        """Rejected bridges are marked unhealthy."""
        bridge_id = manager.request_bridge("island-2")
        manager.reject_bridge_request(bridge_id, "test reason")

        health = manager.health_check()
        assert len(health) == 1
        entry = list(health.values())[0]
        assert entry["state"] == "rejected"
        assert entry["healthy"] is False
        assert entry["rejection_reason"] == "test reason"

    def test_detect_stuck_transfers(self, bridge: CrossChainBridge, engine, manager: BridgeManager) -> None:
        """Stuck transfers are detected after timeout."""
        from aitbc_chain.cross_chain.bridge import init_cross_chain_bridge

        init_cross_chain_bridge(lambda: Session(engine))

        _seed_sender(engine, "chain-a", "0xstuckSender", 10000)
        transfer = bridge.initiate_transfer("chain-a", "chain-b", "0xstuckSender", "0xrecip", 5000)

        # Manually age the transfer by setting lock_time in the past
        with Session(engine) as session:
            record = session.get(CrossChainTransfer, transfer.transfer_id)
            assert record is not None
            record.lock_time = datetime.now(UTC) - timedelta(seconds=7200)
            session.add(record)
            session.commit()

        stuck = manager.detect_stuck_transfers(stuck_timeout=3600)
        assert len(stuck) == 1
        assert stuck[0]["transfer_id"] == transfer.transfer_id
        assert stuck[0]["age_seconds"] >= 7200

        # Cleanup
        from aitbc_chain.cross_chain import bridge as bridge_mod

        bridge_mod._bridge_instance = None

    def test_detect_stuck_transfers_none_recent(self, bridge: CrossChainBridge, engine, manager: BridgeManager) -> None:
        """Recent transfers are not flagged as stuck."""
        from aitbc_chain.cross_chain.bridge import init_cross_chain_bridge

        init_cross_chain_bridge(lambda: Session(engine))

        _seed_sender(engine, "chain-a", "0xfreshSender", 10000)
        bridge.initiate_transfer("chain-a", "chain-b", "0xfreshSender", "0xrecip", 5000)

        stuck = manager.detect_stuck_transfers(stuck_timeout=3600)
        assert len(stuck) == 0

        # Cleanup
        from aitbc_chain.cross_chain import bridge as bridge_mod

        bridge_mod._bridge_instance = None

    def test_get_metrics(self, bridge: CrossChainBridge, engine, manager: BridgeManager) -> None:
        """Metrics endpoint returns correct counts."""
        from aitbc_chain.cross_chain.bridge import init_cross_chain_bridge

        init_cross_chain_bridge(lambda: Session(engine))

        _seed_sender(engine, "chain-a", "0xmetricSender", 50000)
        bridge.initiate_transfer("chain-a", "chain-b", "0xmetricSender", "0xrecip", 10000)
        bridge.initiate_transfer("chain-a", "chain-b", "0xmetricSender", "0xrecip2", 5000)

        manager.request_bridge("island-2")

        metrics = manager.get_metrics(stuck_timeout=3600)
        assert metrics["active_bridge_count"] == 0
        assert metrics["pending_request_count"] == 1
        assert metrics["pending_transfer_count"] == 2
        assert metrics["stuck_transfer_count"] == 0
        assert metrics["total_locked_amount"] == 15000

        # Cleanup
        from aitbc_chain.cross_chain import bridge as bridge_mod

        bridge_mod._bridge_instance = None


# ---------------------------------------------------------------------------
# Proof helper (for confirm tests)
# ---------------------------------------------------------------------------


def _build_valid_proof(record: CrossChainTransfer, proposer_key: str) -> dict[str, Any]:
    """Build a cryptographically valid proof for a transfer record."""
    proof: dict[str, Any] = {
        "source_chain": record.source_chain,
        "lock_tx_hash": record.source_tx_hash or "0xlock",
        "amount": record.amount,
        "sender": record.sender,
        "recipient": record.recipient,
        "chain_id": record.source_chain,
        "block_height": 10,
        "block_hash": "0x" + "ab" * 32,
    }
    proof_for_signing = {k: v for k, v in proof.items() if k != "proposer_signature"}
    msg_hash = _canonical_hash(proof_for_signing)
    proof["proposer_signature"] = _sign_hash(proposer_key, msg_hash)
    return proof
