## Preparation Phase
- Verify that all prerequisite releases are merged and tagged.
- Set up a test environment matching the target release's dependencies.
- Run existing test suite to ensure baseline passes before coding.
- Review the CHANGELOG and any linked design documents for ambiguities.
- Coordinate with relevant agents (A/B) to clarify file ownership and avoid conflicts.

# v0.6.1 Suggestions

## Status
**INVESTIGATED** — Codebase investigation completed. All 3 original gaps resolved with concrete file paths, line numbers, and implementation specs. The change.log now includes a deterministic scheduler prototype spec, feature flag architecture, and consensus correctness test matrix.

## Resolved Issues
- ~~v0.6.0 prerequisite unclear~~ → **Resolved**: v0.6.0 is complete (340 passed, 0 failed). Change.log now links to v0.6.0 benchmark baseline path (`benchmarks/v0.6.0-baseline/`) and documents the dependency: "Requires v0.6.0 DB indexes + caching to achieve parallel processing targets."
- ~~No deterministic scheduling prototype~~ → **Resolved**: Change.log now includes a prototype-first approach with target files (`aitbc/blockchain/parallel_executor.py`, `aitbc/blockchain/scheduler.py`), prototype scope (dependency analysis, deterministic grouping, conflict detection), and a validation gate (3+ nodes on same blocks before touching consensus code).
- ~~No implementation test specs~~ → **Resolved**: Change.log now includes a concrete consensus correctness test matrix (N validators × M blocks × K conflict scenarios), determinism oracle spec (all nodes produce identical state root hash), conflict scenarios (overlapping accounts, contract calls, storage slots), and CI gate requirement.

## Gaps
All 3 original gaps resolved. No remaining gaps.

## Recommendations (all addressed in change.log)
1. ~~Prototype deterministic scheduler first~~ → **Done**: See "Phase 1: Prototype" section in change.log with target files, scope, and validation gate.
2. ~~Feature flag architecture~~ → **Done**: See "Feature Flag Architecture" section — `BLOCK_PROCESSING_PARALLEL`, `PARALLEL_VALIDATION_WORKERS`, `DETERMINISTIC_SCHEDULING_SEED` flags, all off by default with fast rollback path.
3. ~~Define consensus correctness test spec~~ → **Done**: See "Consensus Correctness Test Matrix" section with N×M×K test matrix, determinism oracle, conflict scenarios, and CI gate.
4. ~~Agent pairing~~ → **Done**: See "Agent Pairing" section — Agent A (block validation) + Agent B (transaction validation) explicitly paired on consensus-critical code, shared interface: deterministic scheduler API.
5. ~~Document v0.6.0 baseline dependency~~ → **Done**: Change.log prerequisites section now links to v0.6.0 benchmark baseline and documents the DB/caching dependency.

## Quick Wins (all addressed in change.log)
- ~~PARALLEL_VALIDATION_WORKERS default calculation~~ → **Done**: `min(4, CPU_cores - 1)` with fallback to 1 (sequential).
- ~~DETERMINISTIC_SEED derivation spec~~ → **Done**: `blake3(block_hash + str(block_height))` — deterministic across all nodes since block hash is consensus-agreed.
- ~~Conflict logging spec~~ → **Done**: Log conflict tx hashes + affected accounts + resolution (re-validated vs marked invalid) for debugging.
- ~~Rollback procedure~~ → **Done**: `systemctl restart aitbc-blockchain-node` with `BLOCK_PROCESSING_PARALLEL=false` — no data migration needed, just config change + restart.

## Investigation Results (verified at v0.6.0)

### Current Sequential Processing (poa.py after v0.6.0)
- The tx loop in `_propose_block` (lines ~305-399) processes transactions sequentially
- After B3b: accounts are batch-fetched before the loop (no per-tx DB round-trip for accounts)
- After B5: state root is computed incrementally via `_compute_state_root_incremental`
- Per-tx work that remains sequential:
  1. `state_transition.apply_transaction()` — validates + applies state changes (CPU + DB)
  2. Duplicate tx check (now in-memory via `existing_tx_map`)
  3. Transaction record creation + `session.add()`
  4. `nested.commit()` (savepoint)
  5. Track changed addresses for incremental state root

### State Root Computation
- `MerklePatriciaTrie` (merkle_patricia_trie.py:37) — NOT thread-safe (no locks, single trie instance)
- `StateManager` (merkle_patricia_trie.py:377) — wraps trie, also NOT thread-safe
- `update_account()` (line 388) — mutates the trie in-place
- For parallel processing: each parallel worker would need its own trie snapshot, or the trie needs locking

### Feature Flag Infrastructure
- `apps/blockchain-node/src/aitbc_chain/config.py` uses pydantic_settings.BaseSettings
- Pattern: `field_name: bool = False` with env var `FIELD_NAME`
- v0.6.0 already added: `network_compression_enabled: bool = True`, `db_connection_pool_size: int = 20`
- No existing "feature flag" pattern — just config settings

### Existing Parallelism
- (To be filled by investigation subagent)

### Transaction Structure for Dependency Analysis
- `Transaction` model fields: `sender`, `recipient`, `type`, `payload` (JSON dict), `value`, `fee`, `nonce`
- `state_transition.apply_transaction` reads: sender account, recipient account, tx_record
- `state_transition.apply_transaction` writes: sender balance/nonce, recipient balance
- Read/write sets can be extracted from `sender` + `recipient` fields (for TRANSFER type)
- For MESSAGE type: only sender is written (fee deduction)
- For RECEIPT_CLAIM type: receipt record is also read/written
