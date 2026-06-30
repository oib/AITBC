# v0.6.0 Database & Network Optimization — Agent B Tasks

**Last Updated**: 2026-06-30
**Version**: 1.0

**Agent**: Agent B (Apps & Infrastructure)

**Scope**: Add missing indexes, wire up connection pooling, eliminate N+1 queries, batch mempool operations, implement incremental state root, wire up shared HTTP pool + compression + block caching, and benchmark.

**Working directory**: `/opt/aitbc/apps/blockchain-node/`

**Verification command**:
```bash
cd /opt/aitbc && ./venv/bin/python -m pytest apps/blockchain-node/tests/ -q -o addopts="" --timeout=60
```

---

## Tasks

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| B1 | Add missing indexes to `base_models.py` + Alembic migration | 🔴 P0 | `base_models.py`, `migrations/versions/a1b2c3d4e5f6_add_performance_indexes.py` | ✅ |
| B2 | Wire up connection pooling in `database.py` using `aitbc/database/pooling.py` | 🔴 P0 | `database.py`, `config.py` | ✅ |
| B3 | Eliminate N+1 queries — `rpc/blocks.py`, `consensus/poa.py`, `sync.py` | 🔴 P0 | `rpc/blocks.py`, `consensus/poa.py`, `sync.py` | ✅ |
| B4 | Batch mempool operations — drain DELETE, remove per-tx commits | High | `mempool.py` | ✅ |
| B5 | Incremental state root — use existing `update_account()` instead of full recompute | High | `consensus/poa.py`, `tests/test_consensus.py` | ✅ |
| B6 | Wire up shared HTTP client pool — replace per-request clients in 5 files | High | `consensus/poa.py`, `chain_sync.py`, `network/hub_discovery.py`, `rpc/escrow_routes.py`, `main.py` | ✅ |
| B7 | Wire up compression + block header caching | Medium | `gossip/broker.py`, `chain_sync.py`, `p2p_network.py`, `rpc/blocks.py`, `consensus/poa.py`, `block_cache.py`, `network/compression.py` | ✅ |
| B8 | Performance benchmarks + verify targets | Medium | `apps/blockchain-node/tests/test_performance.py` (new) | ✅ |

---

## B1: Add missing indexes + Alembic migration

- **Add to `base_models.py`** (additive `index=True` or `Index()` in `__table_args__`):
  - `Block.parent_hash` — `Field(index=True)` (queried in `sync.py:542`)
  - `Transaction.sender` — `Field(index=True)` (queried for balance/transfer lookups)
  - `Transaction.recipient` — `Field(index=True)` (queried for incoming transfer lookups)
  - `CrossChainTransfer.status` — `Field(index=True)` (queried in `bridge.py:229`)
  - `Stake.status` — `Field(index=True)` (queried for active validator filtering)
  - `GovernanceProposal.status` — `Field(index=True)` (queried in `staking.py:365,415`)
- **Add composite indexes** via `Index()` in `__table_args__`:
  - `Transaction`: `Index("idx_tx_chain_height", "chain_id", "block_height")` (queried together in `blocks.py:139`)
  - `MempoolEntry`: `Index("idx_mempool_chain_fee", "chain_id", "fee")` (queried together in `mempool.py:256,276`)
- **Alembic migration**: Create `migrations/versions/xxx_add_performance_indexes.py` with `op.create_index(..., if_not_exists=True)` for each new index. Follow the existing migration style (see `50fb6691025c_add_chain_id.py`).
- **Verify**: `pytest apps/blockchain-node/tests/test_models.py -q` passes. New migration runs cleanly against a fresh DB.

---

## B2: Wire up connection pooling

- **Problem**: `database.py:82,92,106` creates engines with `create_engine(sqlite_url)` — no pool config. The shared `aitbc/database/pooling.py:create_pooled_engine()` exists with proper QueuePool/StaticPool.
- **Fix**: Replace direct `create_engine` calls with `create_pooled_engine` from `aitbc.database.pooling`. For SQLite, use `use_static_pool=True` (SQLite doesn't benefit from QueuePool — single writer). For PostgreSQL (if configured), use QueuePool with configurable pool size from env.
- Also replace direct `Session(engine)` with `sessionmaker(engine)` factory pattern (lines 156, 171).
- **Verify**: `pytest apps/blockchain-node/tests/ -q` — no regressions. Engine is shared, not recreated.

---

## B3: Eliminate N+1 queries

**B3a: `rpc/blocks.py:127-142`** — `get_blocks_range` fetches transactions per-block in a loop:
- Replace the per-block `select(Transaction).where(... block_height == b.height)` loop with a single query: fetch all transactions for the block height range using `WHERE chain_id = ? AND block_height BETWEEN ? AND ?`, then group by `block_height` in memory.

**B3b: `consensus/poa.py:239-327`** — block proposal does 3 DB calls per tx:
- Before the tx loop, batch-fetch all unique sender and recipient accounts in 2 queries: `SELECT * FROM account WHERE chain_id = ? AND address IN (...)`.
- Build a dict `{address: Account}` for O(1) lookup in the loop.
- Batch-fetch duplicate check: `SELECT tx_hash FROM transaction WHERE chain_id = ? AND tx_hash IN (...)`.
- **Keep the sequential processing loop** — only eliminate the per-tx DB round-trips. The actual state transition logic stays unchanged (v0.6.1 will parallelize it).

**B3c: `sync.py:433-451`** — account state sync does `session.get()` per remote account:
- Batch-fetch all existing accounts for the chain in one query: `SELECT * FROM account WHERE chain_id = ?`.
- Build a dict, then merge remote accounts in memory (insert/update as needed).
- **Verify**: `pytest apps/blockchain-node/tests/test_sync.py -q` passes.

---

## B4: Batch mempool operations

- **`drain` (mempool.py:303-311)**: Replace per-tx DELETE loop with a single `DELETE FROM mempool WHERE chain_id = ? AND tx_hash IN (...)` query.
- **`add` (mempool.py:244)**: Remove per-tx `session.commit()`. Let the caller commit (or add a `batch_add` method that takes a list and commits once).
- **`remove` (mempool:329)**: Remove per-tx `session.commit()`. Add a `batch_remove(hashes: list[str])` method.
- **Verify**: `pytest apps/blockchain-node/tests/test_mempool.py -q` passes (update tests if commit behavior changed).

---

## B5: Incremental state root

- **Problem**: `poa.py:34-44` (`_compute_state_root`) loads ALL accounts and creates a new trie per block. `StateManager.update_account()` (line 388) exists but is unused.
- **Fix**: Maintain a persistent `MerklePatriciaTrie` instance per chain (cached in the `PoAProposer` or a `StateManager` singleton). After each tx's state transition, call `update_account(address, balance, nonce)` to incrementally update the trie. The state root is then `trie.get_root()` — no full recompute needed.
- **In `poa.py`**: Replace the `_compute_state_root(session, chain_id)` call (line 341) with the incremental root from the maintained trie.
- **In `sync.py`**: When importing blocks, after applying state transitions, use the incremental update path. For initial sync (full state import), keep the full recompute as a fallback.
- **⚠️ Risk**: This changes the state root computation path. Must verify that the incremental root matches the full recompute root for the same state. Add a test that compares both methods.
- **Verify**: New test: `test_incremental_state_root_matches_full_recompute` — apply 100 txs incrementally, then full recompute, assert roots match.

---

## B6: Wire up shared HTTP client pool

- **Problem**: 6 files create `httpx.AsyncClient` per-request. Agent A's `SharedHttpClient` (A3) provides a pooled alternative.
- **Fix**: Replace `async with httpx.AsyncClient(timeout=...) as client:` with `await shared_client.get/post(...)` in:
  - `consensus/poa.py:594,627` — genesis block/allocations fetch
  - `chain_sync.py:105,206` — broadcast/import (replace `aiohttp.ClientSession` too, or keep aiohttp but make it a shared session)
  - `network/hub_discovery.py:100,131` — hub discovery
  - `rpc/escrow_routes.py:58` — escrow RPC
  - `main.py:398` — startup health check
- Import `SharedHttpClient` from `aitbc.network`.
- **Verify**: `pytest apps/blockchain-node/tests/ -q` — no regressions. No new `httpx.AsyncClient()` calls in the diff.

---

## B7: Wire up compression + block header caching

**Compression** (using A4's `compress_json`/`decompress_json`):
- `gossip/broker.py:326-329` — compress messages before publish, decompress on receive
- `chain_sync.py:186` — compress block data before Redis publish
- `p2p_network.py:141` — compress P2P TCP payloads
- Add a `NETWORK_COMPRESSION_ENABLED=true` env flag (default true) so it can be disabled for debugging

**Block header caching** (using A2's `BlockHeaderCache`):
- `rpc/blocks.py` — cache block headers on `get_block_by_hash` and `get_block_by_height`
- `consensus/poa.py` — cache headers during block proposal (avoid re-fetching parent)
- Initialize `BlockHeaderCache(max_size=1000)` in the blockchain-node startup
- **Verify**: `pytest apps/blockchain-node/tests/ -q` passes. Cache hit rate >80% in benchmarks (B8).

---

## B8: Performance benchmarks + verify targets

Create `apps/blockchain-node/tests/test_performance.py` with:

```python
@pytest.mark.slow
class TestPerformance:
    def test_query_latency_p95(self):
        """Verify query latency <5ms (95th percentile)."""
        ...

    def test_cache_hit_rate(self):
        """Verify cache hit rate >80%."""
        ...

    def test_mempool_query_latency(self):
        """Verify mempool query latency <5ms."""
        ...

    def test_network_compression_ratio(self):
        """Verify network compression >50%."""
        ...

    def test_block_import_rate(self):
        """Measure block import rate (baseline for v0.6.1)."""
        ...
```

Mark as `@pytest.mark.slow` — only run with `-m slow`.

**Verify targets**:
- Query latency <5ms (95th percentile)
- Cache hit rate >80%
- Mempool query latency <5ms
- Network compression >50%

---

## Related Topics

- [Overview](./overview.md) - Release overview and status baseline
- [Agent A Tasks](./agent-a.md) - Shared core implementation details

---

**Documentation Version**: 1.0
**Last Updated**: 2026-06-30
**Release**: v0.6.0 — Database & Network Optimization
**Agent**: Agent B (Apps & Infrastructure)
