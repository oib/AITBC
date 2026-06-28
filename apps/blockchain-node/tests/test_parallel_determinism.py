"""Determinism tests for parallel transaction validation.

Verifies that parallel tx validation produces identical state roots to
sequential validation for the same set of transactions. This is the most
critical test file for v0.6.1 — if any test fails, the parallel path is
non-deterministic and must not be enabled in production.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import Session

from aitbc.parallel import DependencyGraph, ParallelExecutor
from aitbc_chain.models import Account, Block
from aitbc_chain.state.merkle_patricia_trie import StateManager
from aitbc_chain.state.pure_state_transition import (
    StateDelta,
    apply_delta_to_map,
    apply_deltas_to_db,
    compute_state_delta,
    extract_read_write_sets,
)


@pytest.fixture
def test_db() -> Generator[Session]:
    """Create a test database session."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Block.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _make_tx(
    sender: str,
    recipient: str,
    amount: int = 10,
    fee: int = 1,
    tx_hash: str = "",
    tx_type: str = "TRANSFER",
    payload: dict | None = None,
) -> dict:
    """Create a transaction data dict."""
    return {
        "from": sender,
        "to": recipient,
        "amount": amount,
        "fee": fee,
        "type": tx_type,
        "tx_hash": tx_hash or f"0x{abs(hash(sender + recipient + str(amount))):064x}",
        "nonce": 0,
        "value": amount,
        "payload": payload or {},
    }


def _make_account_map(accounts: dict[str, tuple[int, int]]) -> dict[str, Account]:
    """Create an account_map from {address: (balance, nonce)}."""
    return {
        addr: Account(chain_id="test-chain", address=addr, balance=bal, nonce=nonce) for addr, (bal, nonce) in accounts.items()
    }


def _compute_state_root_from_map(account_map: dict[str, Account]) -> str:
    """Compute state root from an account_map using StateManager."""
    state_manager = StateManager()
    for address, account in sorted(account_map.items()):
        state_manager.update_account(address, account.balance, account.nonce)
    return "0x" + state_manager.get_root().hex()


def _run_sequential(
    account_map: dict[str, Account],
    txs: list[dict],
    chain_id: str = "test-chain",
) -> tuple[dict[str, Account], list[StateDelta]]:
    """Run sequential validation — process txs one at a time.

    Returns (final_account_map, list_of_successful_deltas).
    """
    processed_hashes: set[str] = set()
    successful_deltas: list[StateDelta] = []
    for tx_data in txs:
        tx_data_copy = tx_data.copy()
        sender = tx_data_copy.get("from", "")
        sender_account = account_map.get(sender)
        tx_data_copy["nonce"] = sender_account.nonce if sender_account else 0
        tx_data_copy["value"] = tx_data_copy.get("amount", 0)
        delta = compute_state_delta(account_map, tx_data_copy, chain_id, tx_data.get("tx_hash", ""), processed_hashes)
        if delta.success:
            apply_delta_to_map(account_map, delta, chain_id)
            processed_hashes.add(delta.tx_hash)
            successful_deltas.append(delta)
    return account_map, successful_deltas


def _run_parallel(
    account_map: dict[str, Account],
    txs: list[dict],
    chain_id: str = "test-chain",
    max_workers: int = 4,
) -> tuple[dict[str, Account], list[StateDelta]]:
    """Run parallel validation — use DependencyGraph + ParallelExecutor.

    Returns (final_account_map, list_of_successful_deltas).
    """
    # Build dependency graph
    graph = DependencyGraph()
    tx_by_hash: dict[str, dict] = {}
    for idx, tx_data in enumerate(txs):
        read_set, write_set = extract_read_write_sets(tx_data)
        tx_hash = tx_data.get("tx_hash", f"tx{idx}")
        graph.add_transaction(tx_hash, read_set, write_set, index=idx)
        tx_by_hash[tx_hash] = tx_data

    groups = graph.get_conflict_groups()
    processed_hashes: set[str] = set()

    # Prepare tx_data with nonce from account_map
    tx_data_map: dict[str, dict] = {}
    for tx_data in txs:
        tx_hash = tx_data.get("tx_hash", "")
        tx_data_copy = tx_data.copy()
        sender = tx_data_copy.get("from", "")
        sender_account = account_map.get(sender)
        tx_data_copy["nonce"] = sender_account.nonce if sender_account else 0
        tx_data_copy["value"] = tx_data_copy.get("amount", 0)
        tx_data_map[tx_hash] = tx_data_copy

    all_deltas: list[tuple[int, StateDelta]] = []
    executor = ParallelExecutor(max_workers=max_workers)
    try:
        for group in groups:
            # Update nonces from account_map before processing each group
            # (conflicting txs in later groups need updated nonces from earlier groups)
            for tx_hash in group:
                tx_data = tx_data_map[tx_hash]
                sender = tx_data.get("from", "")
                sender_account = account_map.get(sender)
                if sender_account:
                    tx_data["nonce"] = sender_account.nonce

            group_items = [(tx_hash, tx_data_map[tx_hash]) for tx_hash in group]

            def compute_fn(item: tuple[str, dict]) -> StateDelta:
                tx_hash, tx_data = item
                return compute_state_delta(account_map, tx_data, chain_id, tx_hash, processed_hashes)

            results = executor.execute_groups([group_items], compute_fn)
            group_deltas = results[0] if results else []

            for i, (tx_hash, _) in enumerate(group_items):
                delta = group_deltas[i]
                if delta.success:
                    apply_delta_to_map(account_map, delta, chain_id)
                    processed_hashes.add(tx_hash)
                    all_deltas.append((i, delta))
    finally:
        executor.close()

    # Sort by original index for deterministic ordering
    all_deltas.sort(key=lambda x: x[0])
    successful_deltas = [d for _, d in all_deltas]
    return account_map, successful_deltas


def _deep_copy_account_map(account_map: dict[str, Account]) -> dict[str, Account]:
    """Deep copy an account_map (create new Account objects)."""
    return {
        addr: Account(chain_id=acc.chain_id, address=acc.address, balance=acc.balance, nonce=acc.nonce)
        for addr, acc in account_map.items()
    }


class TestParallelDeterminism:
    """Verify that parallel tx validation produces identical state roots
    to sequential validation for the same set of transactions."""

    def test_no_conflicts_parallel_matches_sequential(self) -> None:
        """10 txs, all different accounts — parallel and sequential produce
        identical state roots."""
        # Setup: 20 accounts with sufficient balance
        accounts = {f"addr_{i}": (10000, 0) for i in range(20)}
        txs = [_make_tx(f"addr_{i}", f"addr_{i + 10}", amount=100, fee=1) for i in range(10)]

        # Run sequential
        seq_map = _make_account_map(accounts)
        seq_map, seq_deltas = _run_sequential(seq_map, txs)
        seq_root = _compute_state_root_from_map(seq_map)

        # Run parallel
        par_map = _make_account_map(accounts)
        par_map, par_deltas = _run_parallel(par_map, txs)
        par_root = _compute_state_root_from_map(par_map)

        assert seq_root == par_root, f"State root mismatch: seq={seq_root}, par={par_root}"
        assert len(seq_deltas) == len(par_deltas)
        assert len(seq_deltas) == 10  # all should succeed

    def test_all_conflicts_parallel_matches_sequential(self) -> None:
        """10 txs, all same sender — parallel falls back to sequential-like
        behavior (each tx in its own group), state roots match."""
        accounts = {"sender": (100000, 0)}
        # Add recipients
        for i in range(10):
            accounts[f"recv_{i}"] = (0, 0)
        txs = [_make_tx("sender", f"recv_{i}", amount=100, fee=1) for i in range(10)]

        # Run sequential
        seq_map = _make_account_map(accounts)
        seq_map, seq_deltas = _run_sequential(seq_map, txs)
        seq_root = _compute_state_root_from_map(seq_map)

        # Run parallel
        par_map = _make_account_map(accounts)
        par_map, par_deltas = _run_parallel(par_map, txs)
        par_root = _compute_state_root_from_map(par_map)

        assert seq_root == par_root, f"State root mismatch: seq={seq_root}, par={par_root}"
        assert len(seq_deltas) == len(par_deltas)

    def test_partial_conflicts_parallel_matches_sequential(self) -> None:
        """20 txs, 5 conflict (same sender), 15 independent — state roots match."""
        accounts = {f"addr_{i}": (10000, 0) for i in range(40)}
        # 5 txs from same sender (conflicting)
        txs = [_make_tx("shared_sender", f"recv_{i}", amount=50, fee=1) for i in range(5)]
        accounts["shared_sender"] = (100000, 0)
        # 15 independent txs
        for i in range(15):
            txs.append(_make_tx(f"addr_{i}", f"addr_{i + 20}", amount=100, fee=1))

        # Run sequential
        seq_map = _make_account_map(accounts)
        seq_map, seq_deltas = _run_sequential(seq_map, txs)
        seq_root = _compute_state_root_from_map(seq_map)

        # Run parallel
        par_map = _make_account_map(accounts)
        par_map, par_deltas = _run_parallel(par_map, txs)
        par_root = _compute_state_root_from_map(par_map)

        assert seq_root == par_root, f"State root mismatch: seq={seq_root}, par={par_root}"
        assert len(seq_deltas) == len(par_deltas)

    def test_mixed_tx_types_parallel_matches_sequential(self) -> None:
        """Mix of TRANSFER and MESSAGE — state roots match."""
        accounts = {f"addr_{i}": (10000, 0) for i in range(20)}
        txs = [
            _make_tx("addr_0", "addr_10", amount=100, fee=1, tx_type="TRANSFER"),
            _make_tx("addr_1", "addr_11", amount=0, fee=1, tx_type="MESSAGE"),
            _make_tx("addr_2", "addr_12", amount=50, fee=2, tx_type="TRANSFER"),
            _make_tx("addr_3", "addr_13", amount=0, fee=1, tx_type="MESSAGE"),
            _make_tx("addr_4", "addr_14", amount=200, fee=1, tx_type="TRANSFER"),
            _make_tx("addr_5", "addr_15", amount=0, fee=3, tx_type="MESSAGE"),
            _make_tx("addr_6", "addr_16", amount=75, fee=1, tx_type="TRANSFER"),
            _make_tx("addr_7", "addr_17", amount=0, fee=1, tx_type="MESSAGE"),
            _make_tx("addr_8", "addr_18", amount=30, fee=1, tx_type="TRANSFER"),
            _make_tx("addr_9", "addr_19", amount=0, fee=2, tx_type="MESSAGE"),
        ]

        # Run sequential
        seq_map = _make_account_map(accounts)
        seq_map, seq_deltas = _run_sequential(seq_map, txs)
        seq_root = _compute_state_root_from_map(seq_map)

        # Run parallel
        par_map = _make_account_map(accounts)
        par_map, par_deltas = _run_parallel(par_map, txs)
        par_root = _compute_state_root_from_map(par_map)

        assert seq_root == par_root, f"State root mismatch: seq={seq_root}, par={par_root}"
        assert len(seq_deltas) == len(par_deltas)

    def test_parallel_results_deterministic_across_runs(self) -> None:
        """Run parallel validation 10 times with same input — all produce
        identical state roots (no race conditions)."""
        accounts = {f"addr_{i}": (10000, 0) for i in range(20)}
        txs = [_make_tx(f"addr_{i}", f"addr_{i + 10}", amount=100, fee=1) for i in range(10)]

        roots: list[str] = []
        for _ in range(10):
            par_map = _make_account_map(accounts)
            par_map, _ = _run_parallel(par_map, txs)
            roots.append(_compute_state_root_from_map(par_map))

        assert all(r == roots[0] for r in roots), f"Non-deterministic results: {roots}"

    def test_conflict_threshold_fallback(self) -> None:
        """When conflict_rate > threshold, falls back to sequential.
        Verify the DependencyGraph correctly reports high conflict rate."""
        accounts = {"sender": (1000000, 0)}
        for i in range(10):
            accounts[f"recv_{i}"] = (0, 0)
        txs = [_make_tx("sender", f"recv_{i}", amount=100, fee=1) for i in range(10)]

        # Build graph and check conflict rate
        graph = DependencyGraph()
        for idx, tx_data in enumerate(txs):
            read_set, write_set = extract_read_write_sets(tx_data)
            graph.add_transaction(tx_data.get("tx_hash", f"tx{idx}"), read_set, write_set, index=idx)

        # All txs share the same sender → all conflict
        assert graph.conflict_rate() == 1.0
        groups = graph.get_conflict_groups()
        # Each tx should be in its own group (all conflict with each other)
        assert len(groups) == 10
        assert all(len(g) == 1 for g in groups)

    def test_empty_txs_parallel_matches_sequential(self) -> None:
        """Empty tx list — both paths produce same (initial) state root."""
        accounts = {f"addr_{i}": (1000, 0) for i in range(5)}

        seq_map = _make_account_map(accounts)
        seq_map, seq_deltas = _run_sequential(seq_map, [])
        seq_root = _compute_state_root_from_map(seq_map)

        par_map = _make_account_map(accounts)
        par_map, par_deltas = _run_parallel(par_map, [])
        par_root = _compute_state_root_from_map(par_map)

        assert seq_root == par_root
        assert len(seq_deltas) == 0
        assert len(par_deltas) == 0

    def test_single_tx_parallel_matches_sequential(self) -> None:
        """Single tx — both paths produce same state root."""
        accounts = {"sender": (10000, 0), "recipient": (0, 0)}
        txs = [_make_tx("sender", "recipient", amount=500, fee=1)]

        seq_map = _make_account_map(accounts)
        seq_map, _ = _run_sequential(seq_map, txs)
        seq_root = _compute_state_root_from_map(seq_map)

        par_map = _make_account_map(accounts)
        par_map, _ = _run_parallel(par_map, txs)
        par_root = _compute_state_root_from_map(par_map)

        assert seq_root == par_root

    def test_insufficient_balance_rejected_both_paths(self) -> None:
        """Txs with insufficient balance are rejected in both paths — same state root."""
        accounts = {"poor_sender": (5, 0), "rich_sender": (10000, 0), "recipient": (0, 0)}
        txs = [
            _make_tx("poor_sender", "recipient", amount=100, fee=1),  # should fail
            _make_tx("rich_sender", "recipient", amount=100, fee=1),  # should succeed
        ]

        seq_map = _make_account_map(accounts)
        seq_map, seq_deltas = _run_sequential(seq_map, txs)
        seq_root = _compute_state_root_from_map(seq_map)

        par_map = _make_account_map(accounts)
        par_map, par_deltas = _run_parallel(par_map, txs)
        par_root = _compute_state_root_from_map(par_map)

        assert seq_root == par_root
        assert len(seq_deltas) == 1  # only rich_sender's tx succeeds
        assert len(par_deltas) == 1

    def test_db_write_consistency(self, test_db: Session) -> None:
        """Verify that apply_deltas_to_db produces the same DB state as
        sequential individual writes."""
        chain_id = "test-chain"
        accounts = {"sender": (10000, 0), "recipient": (0, 0)}

        # Create accounts in DB
        for addr, (bal, nonce) in accounts.items():
            acc = Account(chain_id=chain_id, address=addr, balance=bal, nonce=nonce)
            test_db.add(acc)
        test_db.flush()

        # Compute deltas
        account_map = _make_account_map(accounts)
        txs = [_make_tx("sender", "recipient", amount=500, fee=1)]
        _, deltas = _run_sequential(account_map, txs)
        assert len(deltas) == 1

        # Apply to DB
        apply_deltas_to_db(test_db, deltas, chain_id)
        test_db.commit()

        # Verify DB state
        sender = test_db.get(Account, (chain_id, "sender"))
        recipient = test_db.get(Account, (chain_id, "recipient"))
        assert sender is not None
        assert recipient is not None
        assert sender.balance == 10000 - 501  # 500 + 1 fee
        assert sender.nonce == 1
        assert recipient.balance == 500

    def test_large_tx_set_parallel_matches_sequential(self) -> None:
        """100 txs with mixed conflicts — state roots match (stress test)."""
        accounts = {f"addr_{i}": (100000, 0) for i in range(200)}
        # 3 senders that will conflict (each sends 10 txs)
        for shared in ["shared_a", "shared_b", "shared_c"]:
            accounts[shared] = (1000000, 0)
        txs = []
        # 30 conflicting txs (3 shared senders × 10 txs each)
        for shared in ["shared_a", "shared_b", "shared_c"]:
            for i in range(10):
                txs.append(_make_tx(shared, f"recv_{shared}_{i}", amount=100, fee=1))
                accounts[f"recv_{shared}_{i}"] = (0, 0)
        # 70 independent txs
        for i in range(70):
            txs.append(_make_tx(f"addr_{i}", f"addr_{i + 100}", amount=50, fee=1))

        # Run sequential
        seq_map = _make_account_map(accounts)
        seq_map, seq_deltas = _run_sequential(seq_map, txs)
        seq_root = _compute_state_root_from_map(seq_map)

        # Run parallel
        par_map = _make_account_map(accounts)
        par_map, par_deltas = _run_parallel(par_map, txs)
        par_root = _compute_state_root_from_map(par_map)

        assert seq_root == par_root, f"State root mismatch with 100 txs: seq={seq_root}, par={par_root}"
        assert len(seq_deltas) == len(par_deltas)
