"""BRIDGE-ROOT-FOLLOW-1 — follower-side bridge_state_root shadow check.

Pins the shadow contract: default-off flag touches nothing; at/above the
V-4 boundary the carried root is compared against a root re-derived from the
sealed BRIDGE_LOCK transactions only (never the local CrossChainTransfer
table); a mismatch logs + counts and the block is imported with the carried
root stored unchanged.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlmodel import Session, create_engine, select

from aitbc_chain.base_models import Account, Block
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.cross_chain.bridge_leaf import lock_leaf_value, unknown_lock_leaf
from aitbc_chain.cross_chain.bridge_root_shadow import run_shadow_check
from aitbc_chain.metrics import metrics_registry
from aitbc_chain.sync import ChainSync
from aitbc.crypto.crypto import derive_ethereum_address

CHAIN = "root-shadow"
T0 = datetime(2026, 1, 1, tzinfo=UTC)
V2_HEIGHT = 50000
PROPOSER = derive_ethereum_address("0x" + "bb" * 32)
RECIPIENT = derive_ethereum_address("0x" + "cc" * 32)

HEIGHT = 51000  # >= boundary 30000 and >= V2_HEIGHT


@pytest.fixture(autouse=True)
def _reset_metrics():
    metrics_registry.reset()
    yield
    metrics_registry.reset()


@pytest.fixture()
def shadow_on(monkeypatch: pytest.MonkeyPatch):
    from aitbc_chain.config import settings

    monkeypatch.setattr(settings, "bridge_root_shadow_check", True)
    monkeypatch.setattr(settings, "bridge_lock_leaf_v2_height", V2_HEIGHT)
    return settings


@pytest.fixture()
def session_factory(tmp_path, monkeypatch):
    monkeypatch.setenv("AITBC_DATA_DIR", str(tmp_path))
    engine = create_engine(f"sqlite:///{tmp_path}/chain.db")
    chain_metadata.create_all(engine)

    @contextmanager
    def factory():
        with Session(engine) as session:
            yield session
            session.commit()

    return factory


def _seed_genesis(session_factory) -> None:
    with session_factory() as session:
        session.add(Account(chain_id=CHAIN, address=PROPOSER, balance=10**9, nonce=0))
        session.add(
            Block(
                chain_id=CHAIN,
                height=0,
                hash="0x" + "00" * 32,
                parent_hash="0x00",
                proposer="genesis",
                timestamp=T0,
                tx_count=0,
            )
        )
        session.commit()


def _lock_tx(tx_hash: str, **payload: Any) -> dict[str, Any]:
    """A BRIDGE_LOCK row as ``/rpc/blocks-range`` serves it."""
    return {
        "sender": PROPOSER,
        "type": "BRIDGE_LOCK",
        "tx_hash": tx_hash,
        "chain_id": CHAIN,
        "payload": payload,
        "envelope": None,
    }


def _seal_root(items: list[tuple[str, str]], height: int) -> str:
    """The root consensus would seal: trie key tx_hash, value leaf."""
    from aitbc_chain.state.merkle_patricia_trie import MerklePatriciaTrie

    trie = MerklePatriciaTrie()
    for tx_hash, leaf in items:
        trie.put(tx_hash.encode(), leaf.encode())
    return "0x" + trie.get_root().hex()


def _block(height: int, txs: list[dict[str, Any]], bridge_root: str | None) -> dict[str, Any]:
    data: dict[str, Any] = {
        "chain_id": CHAIN,
        "height": height,
        "hash": f"0x{height:064x}",
        "parent_hash": "0x" + "00" * 32,
        "proposer": PROPOSER,
        "timestamp": T0.isoformat(),
        "tx_count": len(txs),
        "block_metadata": '{"state_transition_version": 8}',
        "signature": "",
        "transactions": txs,
    }
    if bridge_root is not None:
        data["bridge_state_root"] = bridge_root
    return data


class TestShadowCheck:
    def test_matching_v2_block_is_quiet(self, shadow_on, caplog: pytest.LogCaptureFixture) -> None:
        tx_hash = "0x" + "ab" * 32
        leaf = lock_leaf_value(tx_hash, 5000, "evm:1", RECIPIENT, HEIGHT)
        txs = [_lock_tx(tx_hash, transfer_id=tx_hash, amount=5000, target_chain="evm:1", recipient=RECIPIENT)]
        block = _block(HEIGHT, txs, _seal_root([(tx_hash, leaf)], HEIGHT))
        with caplog.at_level(logging.WARNING):
            out = run_shadow_check(block, txs, chain_id=CHAIN)
        assert out == {"checked": 1, "match": 1, "mismatch": 0, "underivable": 0}
        assert metrics_registry._counters.get("bridge_root_shadow_checked_total") == 1.0
        assert metrics_registry._counters.get("bridge_root_shadow_mismatch_total") is None
        assert "BRIDGE-ROOT-SHADOW" not in caplog.text

    def test_envelope_fallback_matches(self, shadow_on) -> None:
        """GAP-47 shape: payload empty, derivable fields on the tx envelope."""
        tx_hash = "0x" + "cd" * 32
        leaf = lock_leaf_value(tx_hash, 7, "evm:1", RECIPIENT, HEIGHT)
        txs = [
            {
                "sender": PROPOSER,
                "type": "BRIDGE_LOCK",
                "tx_hash": tx_hash,
                "chain_id": CHAIN,
                "payload": {},
                "transfer_id": tx_hash,
                "amount": 7,
                "target_chain": "evm:1",
                "target_recipient": RECIPIENT,
            }
        ]
        block = _block(HEIGHT, txs, _seal_root([(tx_hash, leaf)], HEIGHT))
        assert run_shadow_check(block, txs, chain_id=CHAIN)["match"] == 1

    def test_tampered_root_warns_and_counts(self, shadow_on, caplog: pytest.LogCaptureFixture) -> None:
        tx_hash = "0x" + "ef" * 32
        txs = [_lock_tx(tx_hash, transfer_id=tx_hash, amount=5000, target_chain="evm:1", recipient=RECIPIENT)]
        block = _block(HEIGHT, txs, "0x" + "ff" * 32)
        with caplog.at_level(logging.WARNING):
            out = run_shadow_check(block, txs, chain_id=CHAIN)
        assert out["mismatch"] == 1
        assert metrics_registry._counters.get("bridge_root_shadow_mismatch_total") == 1.0
        assert "[BRIDGE-ROOT-SHADOW] root mismatch at height 51000" in caplog.text

    def test_v1_lock_below_v2_height(self, shadow_on) -> None:
        """A pre-v2 lock seals the three-field leaf — no recipient needed."""
        tx_hash = "0x" + "aa" * 32
        leaf = lock_leaf_value(tx_hash, 9, "evm:1", "", V2_HEIGHT - 1)
        txs = [_lock_tx(tx_hash, transfer_id=tx_hash, amount=9, target_chain="evm:1")]
        block = _block(V2_HEIGHT - 1, txs, _seal_root([(tx_hash, leaf)], V2_HEIGHT - 1))
        assert run_shadow_check(block, txs, chain_id=CHAIN)["match"] == 1

    def test_empty_locks_matches_empty_root(self, shadow_on) -> None:
        block = _block(HEIGHT, [], _seal_root([], HEIGHT))
        assert run_shadow_check(block, [], chain_id=CHAIN)["match"] == 1

    def test_no_carried_root_returns_none(self, shadow_on) -> None:
        block = _block(HEIGHT, [], None)
        assert run_shadow_check(block, [], chain_id=CHAIN) is None
        assert metrics_registry._counters.get("bridge_root_shadow_checked_total") is None

    def test_below_boundary_skipped(self, shadow_on) -> None:
        block = _block(29999, [], "0x" + "ff" * 32)
        assert run_shadow_check(block, [], chain_id=CHAIN) is None
        assert metrics_registry._counters.get("bridge_root_shadow_mismatch_total") is None

    def test_underivable_lock_counts_and_compares(self, shadow_on) -> None:
        """No derivable leaf data → consensus' unknown-leaf fallback, still
        compared (mismatch shows the producer did NOT seal an unknown leaf)."""
        tx_hash = "0x" + "99" * 32
        txs = [_lock_tx(tx_hash)]  # empty payload, no envelope fields
        block = _block(HEIGHT, txs, _seal_root([(tx_hash, unknown_lock_leaf(tx_hash))], HEIGHT))
        out = run_shadow_check(block, txs, chain_id=CHAIN)
        assert out["underivable"] == 1
        assert out["match"] == 1  # producer sealed the same unknown leaf
        assert metrics_registry._counters.get("bridge_root_shadow_underivable_total") == 1.0

    def test_flag_off_returns_none_and_costs_nothing(self, caplog: pytest.LogCaptureFixture) -> None:
        tx_hash = "0x" + "ab" * 32
        txs = [_lock_tx(tx_hash, transfer_id=tx_hash, amount=1, target_chain="evm:1", recipient=RECIPIENT)]
        block = _block(HEIGHT, txs, "0x" + "ff" * 32)
        with caplog.at_level(logging.WARNING):
            assert run_shadow_check(block, txs, chain_id=CHAIN) is None
        assert metrics_registry._counters.get("bridge_root_shadow_checked_total") is None
        assert metrics_registry._counters.get("bridge_root_shadow_mismatch_total") is None
        assert "BRIDGE-ROOT-SHADOW" not in caplog.text


class TestImportStoresCarriedRoot:
    """Full ``import_block`` path at height 1 (sequential onto genesis) with
    the shadow boundary lowered to 1 — the check fires on a real import."""

    @pytest.fixture()
    def low_boundary(self, monkeypatch: pytest.MonkeyPatch):
        from aitbc_chain.config import settings

        monkeypatch.setattr(settings, "bridge_lock_guard_boundary", 1)

    def test_tampered_root_imported_and_stored_unchanged(
        self, session_factory, shadow_on, low_boundary, caplog: pytest.LogCaptureFixture
    ) -> None:
        _seed_genesis(session_factory)
        sync = ChainSync(session_factory, chain_id=CHAIN, validate_signatures=False)
        tampered = "0x" + "ff" * 32
        block = _block(1, [], tampered)  # no locks: derived = empty root ≠ carried
        with caplog.at_level(logging.WARNING):
            result = sync.import_block(block, transactions=[], skip_state_root_validation=True)
        assert result.accepted, getattr(result, "reason", result)
        with session_factory() as session:
            stored_root = session.exec(select(Block.bridge_state_root).where(Block.chain_id == CHAIN, Block.height == 1)).one()
        assert stored_root == tampered  # carried root stored verbatim
        assert metrics_registry._counters.get("bridge_root_shadow_mismatch_total") == 1.0
        assert "imported unchanged" in caplog.text

    def test_flag_off_import_carries_no_check(self, session_factory, low_boundary, caplog: pytest.LogCaptureFixture) -> None:
        _seed_genesis(session_factory)
        sync = ChainSync(session_factory, chain_id=CHAIN, validate_signatures=False)
        tampered = "0x" + "ff" * 32
        block = _block(1, [], tampered)
        with caplog.at_level(logging.WARNING):
            result = sync.import_block(block, transactions=[], skip_state_root_validation=True)
        assert result.accepted, getattr(result, "reason", result)
        assert metrics_registry._counters.get("bridge_root_shadow_mismatch_total") is None
        assert "BRIDGE-ROOT-SHADOW" not in caplog.text
