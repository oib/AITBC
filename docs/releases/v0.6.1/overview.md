# v0.6.1 Parallel Processing Architecture — Overview

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
- [Status Baseline](#status-baseline--verified-code-targets-from-subagent-investigation)
- [Architecture: Parallel Tx Validation Approach](#architecture-parallel-tx-validation-approach)
- [Task Split Overview](#task-split-overview)

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

---

## Architecture: Parallel Tx Validation Approach

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

## Related Topics

- [Agent A Tasks](./agent-a.md) - Shared core implementation details
- [Agent B Tasks](./agent-b.md) - Apps & infrastructure implementation details

---

**Documentation Version**: 1.0
**Last Updated**: 2026-06-30
**Release**: v0.6.1 — Parallel Processing Architecture
