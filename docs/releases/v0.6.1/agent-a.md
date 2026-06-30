# v0.6.1 Parallel Processing Architecture — Agent A Tasks

**Last Updated**: 2026-06-30
**Version**: 1.0

**Agent**: Agent A (Shared Core)

**Scope**: Create generic parallel processing utilities — dependency graph analysis and a parallel executor with deterministic result merging. These are blockchain-agnostic and reusable.

**Working directory**: `/opt/aitbc/aitbc/`

**Verification command**:
```bash
cd /opt/aitbc && ./venv/bin/python -m mypy --show-error-codes aitbc/ && ./venv/bin/python -m ruff check aitbc/ && ./venv/bin/python -m pytest tests/unit -q -o addopts=""
```

---

## Tasks

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| A1 | Create `DependencyGraph` — read/write set analysis, conflict detection, topological grouping | 🔴 P0 | `aitbc/parallel/dependency_graph.py` (new), `aitbc/parallel/__init__.py` (new) | ✅ |
| A2 | Create `ParallelExecutor` — thread pool with deterministic result merging + sequential fallback | 🔴 P0 | `aitbc/parallel/executor.py` (new), `aitbc/parallel/__init__.py` | ✅ |
| A3 | Unit tests for A1-A2 | High | `tests/unit/test_dependency_graph.py`, `tests/unit/test_parallel_executor.py` | ✅ |
| A4 | Verify mypy + ruff + pytest clean | Medium | — | ✅ |

---

## A1: DependencyGraph

Create `aitbc/parallel/dependency_graph.py` with a `DependencyGraph` class:

```python
class DependencyGraph:
    """Builds a transaction dependency graph from read/write sets.

    Transactions are partitioned into conflict-free groups that can be
    executed in parallel. Within each group, transactions are ordered
    deterministically (by their original index).
    """

    def __init__(self) -> None: ...

    def add_transaction(
        self, tx_id: str, read_set: frozenset[str], write_set: frozenset[str], index: int = 0
    ) -> None:
        """Add a transaction with its read/write sets.

        Args:
            tx_id: Unique transaction identifier (e.g., tx_hash).
            read_set: Set of account addresses read by this tx (sender, recipient).
            write_set: Set of account addresses written by this tx (sender, recipient).
            index: Original ordering index (for deterministic tie-breaking).
        """
        ...

    def get_conflict_groups(self) -> list[list[str]]:
        """Partition transactions into conflict-free groups.

        Returns a list of groups, where:
        - Each group contains transactions that conflict with each other
          (must be executed sequentially within the group).
        - Groups are independent and can be executed in parallel.
        - Within each group, transactions are ordered by their original index.
        - Groups are ordered by the minimum index of their members.

        Algorithm: greedy coloring. Assign each tx to the first group where
        it has no conflicts. If it conflicts with all existing groups, create
        a new group.
        """
        ...

    def get_execution_order(self) -> list[list[str]]:
        """Alias for get_conflict_groups — the execution order is the group order."""
        ...

    def conflict_rate(self) -> float:
        """Return the fraction of transactions that conflict with at least one other.

        Used to decide whether to fall back to sequential execution.
        """
        ...

    def stats(self) -> dict[str, Any]:
        """Return stats: total_txs, num_groups, max_group_size, conflict_rate."""
        ...
```

**Conflict definition**: Two transactions `A` and `B` conflict if:
- `A.write_set ∩ B.write_set ≠ ∅` (both write to the same account), OR
- `A.read_set ∩ B.write_set ≠ ∅` (A reads what B writes), OR
- `A.write_set ∩ B.read_set ≠ ∅` (A writes what B reads)

**Grouping algorithm**: Greedy assignment. For each tx (in index order), assign it to the first existing group where it has no conflicts with any member. If it conflicts with all existing groups, create a new group. This maximizes parallelism within each group boundary.

**Determinism**: The grouping is deterministic because:
- Txs are processed in index order
- Group assignment is greedy (first-fit)
- Within each group, txs are sorted by index

Export from `aitbc/parallel/__init__.py` as `DependencyGraph`.

---

## A2: ParallelExecutor

Create `aitbc/parallel/executor.py` with a `ParallelExecutor` class:

```python
from concurrent.futures import ThreadPoolExecutor
from typing import TypeVar, Callable, Any

T = TypeVar("T")
R = TypeVar("R")

class ParallelExecutor:
    """Executes groups of tasks in parallel with deterministic result ordering.

    Each group is executed as a batch of parallel tasks. Results are returned
    in the same order as the input groups, preserving determinism.
    """

    def __init__(self, max_workers: int = 4) -> None: ...

    def execute_groups[T, R](
        self,
        groups: list[list[T]],
        fn: Callable[[T], R],
    ) -> list[list[R]]:
        """Execute groups of tasks in parallel.

        Within each group, tasks are executed in parallel (thread pool).
        Groups are executed sequentially (group 1, then group 2, etc.)
        to preserve dependency ordering.

        Returns results in the same structure as input: list of lists,
        where results[i][j] = fn(groups[i][j]).
        """
        ...

    def execute_sequential[T, R](
        self,
        items: list[T],
        fn: Callable[[T], R],
    ) -> list[R]:
        """Fallback: execute items sequentially. Returns results in order."""
        ...

    def close(self) -> None:
        """Shut down the thread pool."""
        ...
```

**Key design decisions**:
- Uses `ThreadPoolExecutor` (not asyncio) because `compute_state_delta` is CPU-bound, not I/O-bound. The GIL limits true parallelism for pure Python, but the state delta computation involves enough Python bytecode to benefit from thread-level parallelism on multi-core systems. If benchmarks show GIL contention, a `ProcessPoolExecutor` variant can be added later.
- Groups are executed **sequentially** (not all groups in parallel) because groups represent dependency levels — group 2's txs may depend on group 1's state changes.
- Within each group, tasks are executed in **parallel** since they don't conflict.
- Results are returned in input order, preserving determinism.

Export from `aitbc/parallel/__init__.py` as `ParallelExecutor`.

---

## A3: Unit tests

**`tests/unit/test_dependency_graph.py`**:
- `test_no_conflicts_all_in_one_group` — 5 txs, all different accounts → 1 group of 5
- `test_all_conflict_separate_groups` — 5 txs, all same account → 5 groups of 1
- `test_partial_conflict` — 3 txs where tx1 and tx3 conflict, tx2 is independent → 2 groups
- `test_deterministic_ordering` — same input always produces same groups
- `test_conflict_rate` — 4 txs, 2 conflict → 0.5
- `test_stats` — verify total_txs, num_groups, max_group_size
- `test_read_write_conflict` — tx1 reads A, tx2 writes A → conflict
- `test_write_write_conflict` — tx1 writes A, tx2 writes A → conflict
- `test_index_ordering_within_group` — within a group, txs sorted by index

**`tests/unit/test_parallel_executor.py`**:
- `test_execute_groups_parallel` — 3 groups, verify results in correct order
- `test_execute_sequential` — fallback path
- `test_empty_groups` — empty input → empty output
- `test_single_group` — 1 group of 5 tasks → 1 result list of 5
- `test_deterministic_results` — same input always produces same output
- `test_close_cleanup` — executor closes cleanly

---

## A4: Verify clean

- `mypy aitbc/` — 0 errors
- `ruff check aitbc/` — 0 errors
- `pytest tests/unit -q` — all pass

---

## Related Topics

- [Overview](./overview.md) - Release overview and status baseline
- [Agent B Tasks](./agent-b.md) - Apps & infrastructure implementation details

---

**Documentation Version**: 1.0
**Last Updated**: 2026-06-30
**Release**: v0.6.1 — Parallel Processing Architecture
**Agent**: Agent A (Shared Core)
