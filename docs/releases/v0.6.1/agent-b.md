# v0.6.1 Parallel Processing Architecture — Agent B Tasks

**Last Updated**: 2026-06-30
**Version**: 1.0

**Agent**: Agent B (Apps & Infrastructure)

**Scope**: Refactor state transitions to separate pure validation from DB mutation, wire up parallel tx validation in `poa.py` and `sync.py`, fix mempool determinism, add config, and write determinism tests.

**Working directory**: `/opt/aitbc/apps/blockchain-node/`

**Verification command**:
```bash
cd /opt/aitbc && ./venv/bin/python -m pytest apps/blockchain-node/tests/ -q -o addopts="" --timeout=60
```

---

## Tasks

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

---

## B1: Pure state transition

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

---

## B2: Wire up parallel tx validation in poa.py

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

---

## B3: Wire up parallel tx validation in sync.py

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

---

## B4: Fix mempool ordering determinism

**Problem**: `mempool.py:109` sorts by `(-t.fee, t.received_at)`. `received_at` is set via `time.time()` (line 81), which varies across validators. If two txs have the same fee, different validators may order them differently, leading to different block contents and state roots.

**Fix**: Change the sort key from `(-t.fee, t.received_at)` to `(-t.fee, t.tx_hash)` in:
- `InMemoryMempool.drain` (line 109)
- `InMemoryMempool.get_pending_transactions` (line 155)
- `DatabaseMempool.drain` (line 341) — change `ORDER BY fee DESC, received_at ASC` to `ORDER BY fee DESC, tx_hash ASC`
- `DatabaseMempool.get_pending_transactions` — same change

**`tx_hash` is deterministic** — it's a hash of the transaction content, same across all validators.

**Verify**: `pytest apps/blockchain-node/tests/test_mempool.py -q` passes. Add a test that verifies same-fee txs are ordered by tx_hash.

---

## B5: Add parallel processing config

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

---

## B6: Apply incremental state root to sync path

**Problem**: `sync.py:648` loads ALL accounts for state root verification: `accounts = session.exec(select(Account).where(Account.chain_id == self._chain_id)).all()`. This is the full recompute path that v0.6.0's B5 optimized in `poa.py` but didn't apply to `sync.py`.

**Fix**: Replace the full recompute in `sync.py:645-687` with the incremental approach:
1. Track `changed_addresses` during tx processing (same as poa.py)
2. Use `_compute_state_root_incremental(session, chain_id, account_map, changed_addresses)` instead of `state_manager.compute_state_root(account_dict)`
3. Import `_compute_state_root_incremental` from `consensus/poa.py` or extract it to a shared utility in `state/`

**If extracting to shared utility**: Create `state/state_root_utils.py` with `compute_state_root_incremental(session, chain_id, account_map, changed_addresses)` and `compute_state_root_full(session, chain_id)`. Import from both `poa.py` and `sync.py`.

**Verify**: `pytest apps/blockchain-node/tests/test_sync.py -q` passes. State root verification still rejects mismatched blocks.

---

## B7: Determinism tests

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

---

## B8: Performance benchmarks

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

## Related Topics

- [Overview](./overview.md) - Release overview and status baseline
- [Agent A Tasks](./agent-a.md) - Shared core implementation details

---

**Documentation Version**: 1.0
**Last Updated**: 2026-06-30
**Release**: v0.6.1 — Parallel Processing Architecture
**Agent**: Agent B (Apps & Infrastructure)
