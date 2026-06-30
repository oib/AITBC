# v0.6.1 — Agent Task Assignment

**Last Updated**: 2026-06-30
**Version**: 1.0

**Release Theme**: Parallel Processing Architecture — parallel transaction validation via dependency analysis, deterministic scheduling, and pure state transitions.

**Goal**: Enable the blockchain node to validate transactions in parallel within a block, dramatically increasing throughput. The key insight: most transactions touch different accounts, so they can be validated independently. Conflicting transactions (same sender/recipient) are serialized. A feature flag allows toggling between parallel and sequential execution for safety.

> **Scope constraint**: This release parallelizes **transaction validation within a single block**. Parallel block validation (multiple blocks at once) is deferred — it requires pipelining across block boundaries and is lower priority. The parallel execution must produce **identical state roots** to the sequential path — this is a hard consensus requirement.

> **Prerequisites**: [v0.6.0](../v0.6.0/change.log) (DB & Network Optimization — batch-fetching, incremental state root, connection pooling). The v0.6.0 batch-fetching in `poa.py:276-305` (all accounts pre-fetched into `account_map`) is the foundation for parallel execution.

> **Risk**: High. Changes to consensus-critical code. Mitigated by: (1) feature flag defaulting to sequential, (2) determinism tests comparing parallel vs sequential output, (3) fallback to sequential on conflict threshold exceeded.

---

## Documentation Structure

This release documentation has been split into topic-focused files:

- **[Overview](./overview.md)** - Release overview, status baseline, architecture, and task split overview
- **[Agent A Tasks](./agent-a.md)** - Shared core implementation (DependencyGraph, ParallelExecutor, unit tests)
- **[Agent B Tasks](./agent-b.md)** - Apps & infrastructure implementation (pure state transitions, parallel validation wiring, determinism tests)

---

## Quick Navigation

### Overview
- [Status Baseline](./overview.md#status-baseline--verified-code-targets-from-subagent-investigation)
- [Architecture: Parallel Tx Validation Approach](./overview.md#architecture-parallel-tx-validation-approach)
- [Task Split Overview](./overview.md#task-split-overview)

### Agent A (Shared Core)
- [Scope](./agent-a.md#scope)
- [Tasks](./agent-a.md#tasks)
- [DependencyGraph](./agent-a.md#a1-dependencygraph)
- [ParallelExecutor](./agent-a.md#a2-parallelexecutor)
- [Unit tests](./agent-a.md#a3-unit-tests)
- [Verify clean](./agent-a.md#a4-verify-clean)

### Agent B (Apps & Infrastructure)
- [Scope](./agent-b.md#scope)
- [Tasks](./agent-b.md#tasks)
- [Pure state transition](./agent-b.md#b1-pure-state-transition)
- [Wire up parallel tx validation in poa.py](./agent-b.md#b2-wire-up-parallel-tx-validation-in-poapy)
- [Wire up parallel tx validation in sync.py](./agent-b.md#b3-wire-up-parallel-tx-validation-in-syncpy)
- [Fix mempool ordering determinism](./agent-b.md#b4-fix-mempool-ordering-determinism)
- [Add parallel processing config](./agent-b.md#b5-add-parallel-processing-config)
- [Apply incremental state root to sync path](./agent-b.md#b6-apply-incremental-state-root-to-sync-path)
- [Determinism tests](./agent-b.md#b7-determinism-tests)
- [Performance benchmarks](./agent-b.md#b8-performance-benchmarks)

---

## Status Baseline — Verified Code Targets (from subagent investigation)

| Component | Location | Current State | v0.6.1 Target |
|-----------|----------|---------------|---------------|
| **Sequential tx loop** | `consensus/poa.py:308-404` | One tx at a time, nested transaction per tx | Parallel groups, pure state deltas |
| **Impure state transition** | `state/state_transition.py:127-213` | `apply_transaction` does SQL UPDATEs directly on session | Separate `compute_state_delta` (pure) from `apply_delta` (DB write) |
| **Sync verification** | `sync.py:609-687` | Re-runs tx loop sequentially, full state root recompute | Parallel validation + incremental state root |
| **Mempool ordering** | `mempool.py:109` | `sorted(key=lambda t: (-t.fee, t.received_at))` — `received_at` uses `time.time()` (non-deterministic) | Tie-break by `tx_hash` (deterministic) |
| **State root determinism** | `state/merkle_patricia_trie.py:402-419` | `sorted(accounts.items())` — order-independent, tested | No change needed — already deterministic |
| **Account model** | `base_models.py:170-178` | `chain_id`, `address`, `balance`, `nonce` | No change needed |
| **Config** | `config.py:107-109` | `max_txs_per_block: int = 500`, no parallelism config | Add `parallel_tx_validation`, `parallel_workers`, `conflict_threshold` |
| **Batch-fetched accounts** | `poa.py:276-294` (v0.6.0) | All sender/recipient accounts pre-fetched into `account_map` | Foundation for parallel execution — reused as in-memory state |
| **Incremental state root** | `poa.py:49-81` (v0.6.0) | Builds trie from `account_map`, updates only changed addresses | Reused for parallel path — compute from in-memory deltas |
| **No parallelism utilities** | `aitbc/` | None | New `aitbc/parallel/` module with `DependencyGraph` + `ParallelExecutor` |

### Architecture: Parallel Tx Validation Approach

```
┌──────────────────────────────────────────────────────────────────┐
│ _propose_block (poa.py)                                          │
│                                                                  │
│ 1. Drain mempool → pending_txs (deterministic order)             │
│ 2. Batch-fetch accounts → account_map (already done in v0.6.0)   │
│ 3. Build dependency graph from tx read/write sets                │
│ 4. Partition into conflict-free groups (topological sort)        │
│ 5. Execute each group in parallel:                               │
│    - compute_state_delta(account_map, tx) → (delta, ok, err)     │
│    - Pure function, no DB access, no session                     │
│ 6. Apply deltas to account_map in deterministic order            │
│ 7. Write final state to DB (batch UPDATE)                        │
│ 8. Compute state root from account_map (incremental)             │
│ 9. Create block with state_root                                  │
│                                                                  │
│ Feature flag: parallel_tx_validation=false → sequential fallback │
└──────────────────────────────────────────────────────────────────┘
```

**Why this works**:
- **Deterministic**: The dependency graph is built from tx data (sender/recipient), not timing. Groups are ordered by tx index. Deltas are applied in tx index order within each group.
- **Pure state transitions**: `compute_state_delta` takes `(account_map, tx_data)` and returns `(delta, success, error)` — no DB access, no side effects. This makes parallel execution safe.
- **Conflict detection**: Two txs conflict if they share any address in their read/write sets. Conflicting txs are serialized within a group.
- **Fallback**: If conflict rate exceeds threshold (>50% of txs conflict), fall back to sequential execution.

---

## Task Split Overview

| Agent | Domain | Tasks | Files |
|-------|--------|-------|-------|
| **Agent A** | Shared core (`aitbc/`) | 4 items | `aitbc/parallel/`, `tests/unit/` |
| **Agent B** | Apps & infrastructure | 8 items | `apps/blockchain-node/src/aitbc_chain/` (state, consensus, sync, mempool, config), `tests/` |

**Conflict boundary**: Agent A owns `aitbc/parallel/` (new module). Agent B owns `apps/blockchain-node/`. No shared files. Agent B consumes Agent A's `DependencyGraph` and `ParallelExecutor` — see Coordination Protocol.

---

**Documentation Version**: 1.0
**Last Updated**: 2026-06-30
**Release**: v0.6.1 — Parallel Processing Architecture

---

## Agent A — Shared Core (`aitbc/`)

**Scope**: Create generic parallel processing utilities — dependency graph analysis and a parallel executor with deterministic result merging. These are blockchain-agnostic and reusable.

**Working directory**: `/opt/aitbc/aitbc/`

**Verification command**:
```bash
cd /opt/aitbc && ./venv/bin/python -m mypy --show-error-codes aitbc/ && ./venv/bin/python -m ruff check aitbc/ && ./venv/bin/python -m pytest tests/unit -q -o addopts=""
```

### Tasks

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| A1 | Create `DependencyGraph` — read/write set analysis, conflict detection, topological grouping | 🔴 P0 | `aitbc/parallel/dependency_graph.py` (new), `aitbc/parallel/__init__.py` (new) | ✅ |
| A2 | Create `ParallelExecutor` — thread pool with deterministic result merging + sequential fallback | 🔴 P0 | `aitbc/parallel/executor.py` (new), `aitbc/parallel/__init__.py` | ✅ |
| A3 | Unit tests for A1-A2 | High | `tests/unit/test_dependency_graph.py`, `tests/unit/test_parallel_executor.py` | ✅ |
| A4 | Verify mypy + ruff + pytest clean | Medium | — | ✅ |

### Agent A — Detailed Instructions

#### A1: DependencyGraph

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

#### A2: ParallelExecutor

Create `aitbc/parallel/executor.py` with a `ParallelExecutor` class:

```python
from concurrent.futures import ThreadPoolExecutor
from typing import TypeVar

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

#### A3: Unit tests

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

#### A4: Verify clean

- `mypy aitbc/` — 0 errors
- `ruff check aitbc/` — 0 errors
- `pytest tests/unit -q` — all pass

---

## Agent B — Apps & Infrastructure

**Scope**: Refactor state transitions to separate pure validation from DB mutation, wire up parallel tx validation in `poa.py` and `sync.py`, fix mempool determinism, add config, and write determinism tests.

**Working directory**: `/opt/aitbc/apps/blockchain-node/`

**Verification command**:
```bash
cd /opt/aitbc && ./venv/bin/python -m pytest apps/blockchain-node/tests/ -q -o addopts="" --timeout=60
```

### Tasks

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| B1 | Create `pure_state_transition.py` — pure `compute_state_delta` function (no DB access) | 🔴 P0 | `state/pure_state_transition.py` (new) | ✅ |
| B2 | Wire up parallel tx validation in `poa.py` using `DependencyGraph` + `ParallelExecutor` | 🔴 P0 | `consensus/poa.py` | ✅ |
| B3 | Wire up parallel tx validation in `sync.py` (verification path) | High | `sync.py` | ✅ |
| B4 | Fix mempool ordering determinism — replace `received_at` tie-breaker with `tx_hash` | High | `mempool.py` | ✅ |
| B5 | Add parallel processing config to `config.py` | High | `config.py` | ✅ |
| B6 | Apply incremental state root to sync path (replace full recompute) | Medium | `sync.py` | ✅ |
| B7 | Determinism tests — parallel vs sequential produce identical state roots | 🔴 P0 | `apps/blockchain-node/tests/test_parallel_determinism.py` (new) | ✅ |
| B8 | Performance benchmarks — parallel vs sequential throughput | Medium | `apps/blockchain-node/tests/test_parallel_performance.py` (new) | ✅ |

### Agent B — Detailed Instructions

#### B1: Pure state transition

Create `apps/blockchain-node/src/aitbc_chain/state/pure_state_transition.py`:

```python
from dataclasses import dataclass

@dataclass
class StateDelta:
    """State change resulting from a transaction."""
    sender: str
    recipient: str
    sender_balance_change: int  # negative (debit)
    recipient_balance_change: int  # positive (credit)
    sender_nonce_change: int  # +1
    success: bool
    error: str = ""
    tx_type: str = "TRANSFER"

def compute_state_delta(
    account_map: dict[str, Account],
    tx_data: dict[str, Any],
    chain_id: str,
) -> StateDelta:
    """Compute the state delta for a transaction WITHOUT modifying the DB.

    Pure function — reads from account_map (in-memory), returns a StateDelta.
    Does NOT touch the session, does NOT execute SQL, does NOT invalidate cache.

    Args:
        account_map: In-memory account state (pre-fetched from DB).
        tx_data: Transaction data (from, to, amount, fee, type, etc.).
        chain_id: Chain identifier.

    Returns:
        StateDelta with balance/nonce changes, or success=False with error.
    """
    # Validate sender exists
    sender = tx_data.get("from")
    recipient = tx_data.get("to")
    # ... validation logic from apply_transaction, but reading from account_map ...
    # Return StateDelta(sender=..., recipient=..., sender_balance_change=-total_cost, ...)
    ...

def apply_delta_to_map(
    account_map: dict[str, Account],
    delta: StateDelta,
    chain_id: str,
) -> None:
    """Apply a StateDelta to the in-memory account_map.

    Mutates account_map in place. Does NOT touch the DB.
    Creates new Account entries for new recipients.
    """
    ...

def apply_deltas_to_db(
    session: Session,
    deltas: list[StateDelta],
    chain_id: str,
) -> None:
    """Write accumulated state deltas to the DB in a single batch.

    Groups all sender debits and recipient credits into batch UPDATEs.
    Much faster than per-tx SQL UPDATEs.
    """
    ...
```

**Key**: `compute_state_delta` replicates the validation logic from `state_transition.apply_transaction` (lines 127-213) but:
- Reads from `account_map` instead of `session.get(Account, ...)`
- Returns a `StateDelta` instead of executing SQL
- Does NOT call `session.flush()`, `session.execute()`, or invalidate Redis cache
- Handles all tx types: TRANSFER, MESSAGE, RECEIPT_CLAIM, etc.

**The existing `apply_transaction` stays as-is** — it's the sequential fallback path. The new `compute_state_delta` is the parallel path.

#### B2: Wire up parallel tx validation in poa.py

Modify `_propose_block` in `consensus/poa.py` (lines 308-404) to support parallel execution:

```python
# After batch-fetching accounts (line 305), add:
if self._config.parallel_tx_validation:
    state_root = self._propose_block_parallel(session, pending_txs, account_map, existing_tx_map, next_height, parent_hash, timestamp)
else:
    state_root = self._propose_block_sequential(session, pending_txs, account_map, existing_tx_map, next_height, parent_hash, timestamp)
```

**`_propose_block_sequential`**: Extract the existing sequential loop (lines 308-404) into a method. No behavior change — this is the fallback.

**`_propose_block_parallel`**: New method:
1. Build `DependencyGraph` from pending_txs:
   - For each tx, `read_set = {sender, recipient}`, `write_set = {sender, recipient}`
   - `index` = position in pending_txs (deterministic ordering)
2. Get conflict groups: `groups = graph.get_conflict_groups()`
3. Check conflict rate: if `graph.conflict_rate() > self._config.conflict_threshold`, fall back to sequential
4. For each group, use `ParallelExecutor.execute_group(group, lambda tx: compute_state_delta(account_map, tx.content, chain_id))`
5. Apply deltas to `account_map` in tx index order (deterministic)
6. Track `changed_addresses` from all successful deltas
7. Write deltas to DB via `apply_deltas_to_db(session, successful_deltas, chain_id)`
8. Create `Transaction` records for all successful txs
9. Compute state root via `_compute_state_root_incremental(session, chain_id, account_map, changed_addresses)`
10. Return state root

**Feature flag**: `self._config.parallel_tx_validation` (bool, default `False`). Must be explicitly enabled.

**⚠️ Critical**: The parallel path must produce the **exact same state root** as the sequential path for the same set of transactions. B7 verifies this.

#### B3: Wire up parallel tx validation in sync.py

Modify `_append_block` in `sync.py` (lines 609-687) to support parallel verification:

1. Add the same feature flag check: `if settings.parallel_tx_validation:`
2. For the parallel path:
   - Batch-fetch all accounts for the chain (similar to poa.py:276-294)
   - Build dependency graph from block's transactions
   - Execute `compute_state_delta` in parallel groups
   - Apply deltas to account_map
   - Write to DB via `apply_deltas_to_db`
   - Compute state root incrementally (B6)
   - Compare with block's state_root
3. Keep the sequential path as fallback

**Note**: The sync path currently uses `state_transition.apply_transaction` (line 627) and full state root recompute (line 648). The parallel path replaces both.

#### B4: Fix mempool ordering determinism

**Problem**: `mempool.py:109` sorts by `(-t.fee, t.received_at)`. `received_at` is set via `time.time()` (line 81), which varies across validators. If two txs have the same fee, different validators may order them differently, leading to different block contents and state roots.

**Fix**: Change the sort key from `(-t.fee, t.received_at)` to `(-t.fee, t.tx_hash)` in:
- `InMemoryMempool.drain` (line 109)
- `InMemoryMempool.get_pending_transactions` (line 155)
- `DatabaseMempool.drain` (line 341) — change `ORDER BY fee DESC, received_at ASC` to `ORDER BY fee DESC, tx_hash ASC`
- `DatabaseMempool.get_pending_transactions` — same change

**`tx_hash` is deterministic** — it's a hash of the transaction content, same across all validators.

**Verify**: `pytest apps/blockchain-node/tests/test_mempool.py -q` passes. Add a test that verifies same-fee txs are ordered by tx_hash.

#### B5: Add parallel processing config

Add to `config.py` (in the `ProposerConfig` or `Settings` class, whichever is appropriate):

```python
# Parallel processing
parallel_tx_validation: bool = False  # Feature flag — default off for safety
parallel_workers: int = 4  # Thread pool size for parallel tx validation
conflict_threshold: float = 0.5  # Fall back to sequential if >50% of txs conflict
```

Also add env var support (following existing config patterns):
```bash
# /etc/aitbc/blockchain.env
PARALLEL_TX_VALIDATION=true
PARALLEL_WORKERS=4
CONFLICT_THRESHOLD=0.5
```

**Verify**: Config loads correctly with and without env vars.

#### B6: Apply incremental state root to sync path

**Problem**: `sync.py:648` loads ALL accounts for state root verification: `accounts = session.exec(select(Account).where(Account.chain_id == self._chain_id)).all()`. This is the full recompute path that v0.6.0's B5 optimized in `poa.py` but didn't apply to `sync.py`.

**Fix**: Replace the full recompute in `sync.py:645-687` with the incremental approach:
1. Track `changed_addresses` during tx processing (same as poa.py)
2. Use `_compute_state_root_incremental(session, chain_id, account_map, changed_addresses)` instead of `state_manager.compute_state_root(account_dict)`
3. Import `_compute_state_root_incremental` from `consensus/poa.py` or extract it to a shared utility in `state/`

**If extracting to shared utility**: Create `state/state_root_utils.py` with `compute_state_root_incremental(session, chain_id, account_map, changed_addresses)` and `compute_state_root_full(session, chain_id)`. Import from both `poa.py` and `sync.py`.

**Verify**: `pytest apps/blockchain-node/tests/test_sync.py -q` passes. State root verification still rejects mismatched blocks.

#### B7: Determinism tests

Create `apps/blockchain-node/tests/test_parallel_determinism.py`:

```python
class TestParallelDeterminism:
    """Verify that parallel tx validation produces identical state roots
    to sequential validation for the same set of transactions."""

    def test_no_conflicts_parallel_matches_sequential(self):
        """10 txs, all different accounts — parallel and sequential produce
        identical state roots."""
        ...

    def test_all_conflicts_parallel_matches_sequential(self):
        """10 txs, all same sender — parallel falls back to sequential,
        state roots match."""
        ...

    def test_partial_conflicts_parallel_matches_sequential(self):
        """20 txs, 5 conflict (same sender), 15 independent — state roots match."""
        ...

    def test_mixed_tx_types_parallel_matches_sequential(self):
        """Mix of TRANSFER, MESSAGE, RECEIPT_CLAIM — state roots match."""
        ...

    def test_parallel_results_deterministic_across_runs(self):
        """Run parallel validation 10 times with same input — all produce
        identical state roots (no race conditions)."""
        ...

    def test_conflict_threshold_fallback(self):
        """When conflict_rate > threshold, falls back to sequential."""
        ...
```

**This is the most critical test file.** If any test fails, the parallel path is non-deterministic and must not be enabled in production.

**Test approach**: For each test case:
1. Create a set of transactions and initial account state
2. Run sequential validation → record state root
3. Reset state
4. Run parallel validation → record state root
5. Assert state roots are identical

#### B8: Performance benchmarks

Create `apps/blockchain-node/tests/test_parallel_performance.py`:

```python
@pytest.mark.slow
class TestParallelPerformance:
    """Benchmark parallel vs sequential tx validation."""

    def test_parallel_faster_than_sequential_no_conflicts(self):
        """100 non-conflicting txs — parallel should be faster."""
        ...

    def test_parallel_faster_than_sequential_partial_conflicts(self):
        """100 txs, 20% conflict — parallel should still be faster."""
        ...

    def test_sequential_faster_when_all_conflict(self):
        """100 txs, all conflict — sequential should be faster (no parallel overhead)."""
        ...

    def test_throughput_improvement(self):
        """Measure TPS improvement: sequential vs parallel with 4 workers."""
        ...
```

Mark as `@pytest.mark.slow` — only run with `-m slow`.

---

## Coordination Protocol

### File Ownership

| File | Owner | Notes |
|------|-------|-------|
| `aitbc/parallel/dependency_graph.py` | Agent A | A1: new file |
| `aitbc/parallel/executor.py` | Agent A | A2: new file |
| `aitbc/parallel/__init__.py` | Agent A | A1, A2: exports |
| `tests/unit/test_dependency_graph.py` | Agent A | A3 |
| `tests/unit/test_parallel_executor.py` | Agent A | A3 |
| `apps/blockchain-node/src/aitbc_chain/state/pure_state_transition.py` | Agent B | B1: new file |
| `apps/blockchain-node/src/aitbc_chain/state/state_root_utils.py` | Agent B | B6: new file (if extracting shared utility) |
| `apps/blockchain-node/src/aitbc_chain/consensus/poa.py` | Agent B | B2: wire up parallel path |
| `apps/blockchain-node/src/aitbc_chain/sync.py` | Agent B | B3, B6: parallel verification + incremental state root |
| `apps/blockchain-node/src/aitbc_chain/mempool.py` | Agent B | B4: deterministic ordering |
| `apps/blockchain-node/src/aitbc_chain/config.py` | Agent B | B5: parallel config |
| `apps/blockchain-node/tests/test_parallel_determinism.py` | Agent B | B7 |
| `apps/blockchain-node/tests/test_parallel_performance.py` | Agent B | B8 |

### Dependency Graph

```
Phase 1 (Agent A — parallel, no dependencies):
  A1 DependencyGraph
  A2 ParallelExecutor
  A3 unit tests
  A4 verify clean

Phase 2 (Agent B — after A1-A2 are merged):
  B1 pure_state_transition.py     (independent of A)
  B4 mempool determinism          (independent of A)
  B5 parallel config              (independent of A)

Phase 3 (Agent B — after A1-A2 + B1):
  B2 wire up parallel in poa.py   (depends on A1, A2, B1)
  B3 wire up parallel in sync.py  (depends on A1, A2, B1)
  B6 incremental state root sync  (independent of A, but touches sync.py — coordinate with B3)

Phase 4 (Agent B — after B2, B3):
  B7 determinism tests            (depends on B2, B3)
  B8 performance benchmarks       (depends on B2, B3)
```

**B1, B4, B5 can start in parallel with A1-A4** — they don't depend on Agent A's new utilities. Only B2, B3 depend on Agent A's `DependencyGraph` and `ParallelExecutor`. B7, B8 depend on B2, B3 being complete.

---

## Success Criteria

- ✅ `DependencyGraph` correctly partitions transactions into conflict-free groups
- ✅ `ParallelExecutor` executes groups in parallel with deterministic result ordering
- ✅ `compute_state_delta` is a pure function (no DB access, no side effects)
- ✅ Parallel tx validation in `poa.py` produces **identical state roots** to sequential
- ✅ Parallel tx validation in `sync.py` produces **identical state roots** to sequential
- ✅ Mempool ordering is deterministic (tx_hash tie-breaker, not time.time())
- ✅ Feature flag `parallel_tx_validation` defaults to `False` (safe rollout)
- ✅ Conflict threshold fallback works (>50% conflicts → sequential)
- ✅ Incremental state root applied to sync path (no more full recompute)
- ✅ All determinism tests pass (parallel vs sequential, 10 runs identical)
- ✅ Performance benchmarks show improvement for non-conflicting txs
- ✅ `pytest apps/blockchain-node/tests/` — 0 failed, 0 errors
- ✅ `pytest tests/unit` — 0 failed (Agent A's new tests pass)
- ✅ `mypy aitbc/` + `ruff check .` — clean
- ✅ No consensus failures in multi-validator testing
