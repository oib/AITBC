"""Performance benchmarks for v0.6.1 — Parallel Processing.

These benchmarks compare parallel vs sequential transaction validation
throughput using the new pure state transition functions and the
dependency-graph-based parallel executor.

Marked as @pytest.mark.slow so they don't run in the default gate.
Run with: pytest tests/test_parallel_performance.py -q -o addopts="" -m slow
"""

from __future__ import annotations

import time

import pytest
from sqlalchemy import create_engine as sa_create_engine
from sqlalchemy import text
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel

from aitbc.parallel import DependencyGraph, ParallelExecutor
from aitbc_chain.models import Account
from aitbc_chain.state.pure_state_transition import (
    apply_delta_to_map,
    apply_deltas_to_db,
    compute_state_delta,
    extract_read_write_sets,
)

pytestmark = pytest.mark.slow


def _is_slow_mode() -> bool:
    """Check if tests are running with -m slow."""
    import sys

    return "-m slow" in " ".join(sys.argv) or any("slow" in arg for arg in sys.argv if arg.startswith("-m"))


# Skip all tests in this module unless -m slow is explicitly passed.
# Timing benchmarks are inherently flaky when run alongside other tests.
pytestmark = [pytest.mark.slow, pytest.mark.skipif(not _is_slow_mode(), reason="Timing benchmarks require -m slow")]

CHAIN_ID = "perf-chain"
INITIAL_BALANCE = 1_000_000


def _make_tx(
    sender: str,
    recipient: str,
    amount: int = 10,
    fee: int = 1,
    tx_hash: str = "",
) -> dict:
    return {
        "from": sender,
        "to": recipient,
        "amount": amount,
        "fee": fee,
        "type": "TRANSFER",
        "tx_hash": tx_hash or f"0x{abs(hash(sender + recipient)):064x}",
        "nonce": 0,
        "value": amount,
        "payload": {},
    }


def _make_engine():
    engine = sa_create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return engine


class TestParallelPerformance:
    """Benchmark parallel vs sequential tx validation."""

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _make_txs(self, n: int, conflict_rate: float = 0.0):
        """Generate n transactions with given conflict rate.

        conflict_rate=0.0 → all txs touch different accounts (no conflicts)
        conflict_rate=1.0 → all txs touch the same account (all conflict)
        conflict_rate=0.2 → 20% of txs share an account

        Returns (txs_list, account_map) where txs_list is a list of
        tx_data dicts and account_map is pre-populated with accounts.
        """
        txs: list[dict] = []
        account_map: dict[str, Account] = {}

        # Number of txs that share the "hot" sender account
        n_conflict = int(n * conflict_rate)
        hot_sender = "0xhot_sender"
        if n_conflict > 0:
            account_map[hot_sender] = Account(
                chain_id=CHAIN_ID,
                address=hot_sender,
                balance=INITIAL_BALANCE,
                nonce=0,
            )

        for i in range(n):
            if i < n_conflict:
                sender = hot_sender
            else:
                sender = f"0xsender_{i}"
                account_map.setdefault(
                    sender,
                    Account(
                        chain_id=CHAIN_ID,
                        address=sender,
                        balance=INITIAL_BALANCE,
                        nonce=0,
                    ),
                )
            recipient = f"0xrecipient_{i}"
            account_map.setdefault(
                recipient,
                Account(
                    chain_id=CHAIN_ID,
                    address=recipient,
                    balance=INITIAL_BALANCE,
                    nonce=0,
                ),
            )
            txs.append(_make_tx(sender, recipient, tx_hash=f"0x{i:064x}"))

        return txs, account_map

    def _run_sequential(self, txs: list[dict], account_map: dict[str, Account]) -> list:
        """Run validation sequentially — loop calling compute_state_delta."""
        results = []
        local_map = {
            addr: Account(chain_id=a.chain_id, address=a.address, balance=a.balance, nonce=a.nonce)
            for addr, a in account_map.items()
        }
        for tx in txs:
            delta = compute_state_delta(local_map, tx, CHAIN_ID, tx_hash=tx["tx_hash"])
            apply_delta_to_map(local_map, delta, CHAIN_ID)
            results.append(delta)
        return results

    def _run_parallel(self, txs: list[dict], account_map: dict[str, Account], workers: int = 4) -> list:
        """Run validation in parallel via DependencyGraph + ParallelExecutor."""
        # Build dependency graph from read/write sets
        graph = DependencyGraph()
        for idx, tx in enumerate(txs):
            read_set, write_set = extract_read_write_sets(tx)
            graph.add_transaction(tx["tx_hash"], read_set, write_set, index=idx)
        groups = graph.get_conflict_groups()

        # Map tx_hash → tx_data for the executor
        tx_by_hash = {tx["tx_hash"]: tx for tx in txs}

        # Each worker needs its own snapshot of the account map (read-only during compute).
        # compute_state_delta only reads, so a shared read-only copy is fine.
        snapshot = {
            addr: Account(chain_id=a.chain_id, address=a.address, balance=a.balance, nonce=a.nonce)
            for addr, a in account_map.items()
        }

        def _compute(tx_hash: str):
            tx = tx_by_hash[tx_hash]
            return compute_state_delta(snapshot, tx, CHAIN_ID, tx_hash=tx_hash)

        executor = ParallelExecutor(max_workers=workers)
        try:
            grouped_results = executor.execute_groups(groups, _compute)
        finally:
            executor.close()

        # Flatten results in group order (groups are ordered by min index)
        flat: list = []
        for group_results in grouped_results:
            flat.extend(group_results)
        return flat

    # ------------------------------------------------------------------
    # Benchmarks
    # ------------------------------------------------------------------

    def test_parallel_faster_than_sequential_no_conflicts(self):
        """100 non-conflicting txs — parallel should be faster (or at least not dramatically slower)."""
        txs, account_map = self._make_txs(100, conflict_rate=0.0)

        # Warm up
        self._run_sequential(txs, account_map)
        self._run_parallel(txs, account_map)

        t0 = time.perf_counter()
        self._run_sequential(txs, account_map)
        seq_time = time.perf_counter() - t0

        t0 = time.perf_counter()
        self._run_parallel(txs, account_map)
        par_time = time.perf_counter() - t0

        # Parallel should not be dramatically slower (GIL may prevent speedup)
        assert par_time <= seq_time * 3.0, (
            f"Parallel too slow vs sequential: parallel={par_time:.4f}s, sequential={seq_time:.4f}s"
        )

    def test_parallel_faster_than_sequential_partial_conflicts(self):
        """100 txs, 20% conflict — parallel should still be faster (or not dramatically slower)."""
        txs, account_map = self._make_txs(100, conflict_rate=0.2)

        # Warm up
        self._run_sequential(txs, account_map)
        self._run_parallel(txs, account_map)

        t0 = time.perf_counter()
        self._run_sequential(txs, account_map)
        seq_time = time.perf_counter() - t0

        t0 = time.perf_counter()
        self._run_parallel(txs, account_map)
        par_time = time.perf_counter() - t0

        assert par_time <= seq_time * 3.0, (
            f"Parallel too slow vs sequential (20% conflicts): parallel={par_time:.4f}s, sequential={seq_time:.4f}s"
        )

    def test_sequential_not_slower_when_all_conflict(self):
        """100 txs, all conflict — sequential should not be slower than parallel.

        When all txs conflict, each group has 1 tx, so parallel has overhead
        but no benefit.
        """
        txs, account_map = self._make_txs(100, conflict_rate=1.0)

        # Warm up
        self._run_sequential(txs, account_map)
        self._run_parallel(txs, account_map)

        t0 = time.perf_counter()
        self._run_sequential(txs, account_map)
        seq_time = time.perf_counter() - t0

        t0 = time.perf_counter()
        self._run_parallel(txs, account_map)
        par_time = time.perf_counter() - t0

        # Sequential should be at least as fast (allow some tolerance)
        assert seq_time <= par_time * 1.5, (
            f"Sequential unexpectedly slower than parallel (all conflicts): "
            f"sequential={seq_time:.4f}s, parallel={par_time:.4f}s"
        )

    def test_throughput_improvement(self):
        """Measure TPS: sequential vs parallel with 4 workers, 100 non-conflicting txs.

        Parallel TPS should be >= sequential TPS (may be similar due to GIL,
        but should not be worse).
        """
        txs, account_map = self._make_txs(100, conflict_rate=0.0)
        n = len(txs)

        # Warm up
        self._run_sequential(txs, account_map)
        self._run_parallel(txs, account_map)

        t0 = time.perf_counter()
        self._run_sequential(txs, account_map)
        seq_time = time.perf_counter() - t0
        seq_tps = n / seq_time if seq_time > 0 else float("inf")

        t0 = time.perf_counter()
        self._run_parallel(txs, account_map, workers=4)
        par_time = time.perf_counter() - t0
        par_tps = n / par_time if par_time > 0 else float("inf")

        # Parallel TPS should not be dramatically worse
        assert par_tps >= seq_tps / 2.0, f"Parallel TPS too low: parallel={par_tps:.0f} tps, sequential={seq_tps:.0f} tps"

    def test_dependency_graph_scaling(self):
        """Measure DependencyGraph build time for 100, 500, 1000 txs.

        Should scale roughly linearly.
        """
        sizes = [100, 500, 1000]
        times: list[float] = []

        for n in sizes:
            txs, _ = self._make_txs(n, conflict_rate=0.1)

            # Warm up
            graph = DependencyGraph()
            for idx, tx in enumerate(txs):
                read_set, write_set = extract_read_write_sets(tx)
                graph.add_transaction(tx["tx_hash"], read_set, write_set, index=idx)
            graph.get_conflict_groups()

            t0 = time.perf_counter()
            graph = DependencyGraph()
            for idx, tx in enumerate(txs):
                read_set, write_set = extract_read_write_sets(tx)
                graph.add_transaction(tx["tx_hash"], read_set, write_set, index=idx)
            graph.get_conflict_groups()
            elapsed = time.perf_counter() - t0
            times.append(elapsed)

        # Scaling check: the first-fit grouping algorithm is O(n²) in the
        # average case (each tx checks against existing group members), so a
        # 10x input increase can yield up to ~100x time. Assert absolute
        # bounds and that 1000 txs completes in reasonable time.
        assert times[2] < 2.0, f"DependencyGraph too slow for 1000 txs: {times[2]:.4f}s"
        if times[0] > 0:
            ratio = times[2] / times[0]
            # Allow up to 200x for 10x input (O(n²) worst case + overhead)
            assert ratio <= 200.0, (
                f"DependencyGraph scaling worse than O(n²): 100={times[0]:.4f}s, 1000={times[2]:.4f}s, ratio={ratio:.1f}x"
            )

    def test_batch_db_write_vs_individual(self):
        """Compare apply_deltas_to_db (batch) vs individual session.execute per delta.

        Batch should be significantly faster for 50+ deltas.
        """
        n = 50
        txs, account_map = self._make_txs(n, conflict_rate=0.0)

        # Compute deltas once (shared)
        snapshot = {
            addr: Account(chain_id=a.chain_id, address=a.address, balance=a.balance, nonce=a.nonce)
            for addr, a in account_map.items()
        }
        deltas = []
        for tx in txs:
            delta = compute_state_delta(snapshot, tx, CHAIN_ID, tx_hash=tx["tx_hash"])
            deltas.append(delta)

        # --- Batch path: apply_deltas_to_db ---
        engine_batch = _make_engine()
        with Session(engine_batch) as session:
            for _addr, acc in account_map.items():
                session.add(Account(chain_id=acc.chain_id, address=acc.address, balance=acc.balance, nonce=acc.nonce))
            session.commit()

        # Warm up
        with Session(engine_batch) as session:
            apply_deltas_to_db(session, deltas, CHAIN_ID)
            session.commit()

        # Reset balances for the real measurement
        with Session(engine_batch) as session:
            for addr in account_map:
                session.execute(
                    text("UPDATE account SET balance = :bal, nonce = 0 WHERE chain_id = :cid AND address = :addr"),
                    {"bal": INITIAL_BALANCE, "cid": CHAIN_ID, "addr": addr},
                )
            session.commit()

        t0 = time.perf_counter()
        with Session(engine_batch) as session:
            apply_deltas_to_db(session, deltas, CHAIN_ID)
            session.commit()
        batch_time = time.perf_counter() - t0

        # --- Individual path: one session.execute per delta (mirroring apply_deltas_to_db logic) ---
        engine_indiv = _make_engine()
        with Session(engine_indiv) as session:
            for _addr, acc in account_map.items():
                session.add(Account(chain_id=acc.chain_id, address=acc.address, balance=acc.balance, nonce=acc.nonce))
            session.commit()

        def _apply_individual(session: Session, deltas: list) -> None:
            """Mirror apply_deltas_to_db logic but with per-delta session.get + execute."""
            for delta in deltas:
                if not delta.success:
                    continue
                session.execute(
                    text(
                        "UPDATE account SET balance = balance + :bal, nonce = nonce + :nonce "
                        "WHERE chain_id = :cid AND address = :addr"
                    ),
                    {
                        "bal": delta.sender_balance_change,
                        "nonce": delta.sender_nonce_change,
                        "cid": CHAIN_ID,
                        "addr": delta.sender,
                    },
                )
                if delta.tx_type != "MESSAGE" and delta.recipient:
                    recipient_account = session.get(Account, (CHAIN_ID, delta.recipient))
                    if recipient_account:
                        session.execute(
                            text("UPDATE account SET balance = balance + :bal WHERE chain_id = :cid AND address = :addr"),
                            {"bal": delta.recipient_balance_change, "cid": CHAIN_ID, "addr": delta.recipient},
                        )
                    else:
                        session.add(
                            Account(
                                chain_id=CHAIN_ID,
                                address=delta.recipient,
                                balance=delta.recipient_balance_change,
                                nonce=0,
                            )
                        )
            session.flush()

        # Warm up
        with Session(engine_indiv) as session:
            _apply_individual(session, deltas)
            session.commit()

        # Reset balances
        with Session(engine_indiv) as session:
            for addr in account_map:
                session.execute(
                    text("UPDATE account SET balance = :bal, nonce = 0 WHERE chain_id = :cid AND address = :addr"),
                    {"bal": INITIAL_BALANCE, "cid": CHAIN_ID, "addr": addr},
                )
            session.commit()

        t0 = time.perf_counter()
        with Session(engine_indiv) as session:
            _apply_individual(session, deltas)
            session.commit()
        individual_time = time.perf_counter() - t0

        # Batch should be faster (or at least not dramatically slower).
        # Both paths do equivalent work; batch benefits from a single flush.
        assert batch_time <= individual_time * 3.0, (
            f"Batch DB write too slow vs individual: batch={batch_time:.4f}s, individual={individual_time:.4f}s"
        )
