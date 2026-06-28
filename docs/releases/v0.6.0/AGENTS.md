# v0.6.0 — Agent Task Assignment

**Release Theme**: Database & Network Optimization — query indexing, connection pooling, N+1 elimination, batch writes, block header caching, network compression, and shared HTTP client pooling. No parallel processing (that's v0.6.1).

**Goal**: Achieve measurable DB/network/caching performance gains with low regression risk. All changes are additive (indexes, pools, cache layers, batch fetches) — the sequential transaction loop in `poa.py` and full state root recompute architecture stay as-is; only the I/O around them is optimized.

> **Scope constraint**: No parallel processing, no architectural changes to the tx loop. Block import rate / tx validation latency targets are v0.6.1. This release targets: query latency <5ms (95th percentile), cache hit rate >80%, mempool query latency <5ms, network compression >50%.

> **Prerequisites**: [v0.5.18](../v0.5.18/change.log) (green blockchain-node test suite — the regression baseline).

---

## Status Baseline — Verified Code Targets (from subagent investigation)

| Issue | Location | Impact |
|-------|----------|--------|
| No connection pooling | `apps/blockchain-node/src/aitbc_chain/database.py:82,92,106` | New engine per call, no pool reuse |
| Shared pooling utility unused | `aitbc/database/pooling.py:15-70` (`create_pooled_engine`) | Exists, not wired up |
| Missing index: `Block.parent_hash` | `base_models.py:37` | Full table scan during sync (`sync.py:542`) |
| Missing indexes: `Transaction.sender/recipient` | `base_models.py:89-90` | Full table scan on balance/transfer queries |
| Missing index: `CrossChainTransfer.status` | `base_models.py:202` | Full scan on pending-transfer queries (`bridge.py:229`) |
| Missing composite index: `(chain_id, fee)` on mempool | `mempool.py:20` | Mempool queries filter by chain_id but only fee is indexed |
| N+1 query: `get_blocks_range` | `rpc/blocks.py:127-142` | 1 query per block for transactions (101 queries for 100 blocks) |
| N+1 query: block proposal | `consensus/poa.py:239-327` | 3 DB calls per tx (sender, recipient, duplicate check) = 300 per 100-tx block |
| N+1 query: account sync | `sync.py:433-451` | 1 `session.get()` per remote account (10,000 for 10K accounts) |
| Per-tx mempool commits | `mempool.py:244,329` | Commit on every `add` and `remove` |
| Per-tx DELETE loop in drain | `mempool.py:303-311` | DELETE per tx instead of batch |
| State root full recompute | `state/merkle_patricia_trie.py:402-419` | Loads ALL accounts, creates new trie per block. `update_account()` exists (line 388) but is unused |
| HTTP clients created per-request | `poa.py:594,627`, `chain_sync.py:105,206`, `hub_discovery.py:100,131`, `escrow_routes.py:58`, `main.py:398` | New httpx/aiohttp client per call — no connection reuse |
| Zero network compression | `gossip/broker.py:326-329`, `chain_sync.py:186`, `p2p_network.py:141` | All JSON, uncompressed |
| `BlockchainCache` uses `chain_id: int` | `aitbc/caching/blockchain_cache.py:40,44,48,...` | Codebase uses `chain_id: str` ("ait-hub") — type mismatch |
| Block header caching absent | — | `BlockchainCache` has `get_block`/`set_block` but nobody calls them |
| Alembic migrations exist | `apps/blockchain-node/migrations/versions/` (3 migrations) | New indexes go here with `if_not_exists=True` |

---

## Task Split Overview

| Agent | Domain | Tasks | Files |
|-------|--------|-------|-------|
| **Agent A** | Shared core (`aitbc/`) | 7 items | `aitbc/caching/`, `aitbc/network/`, `aitbc/database/`, `tests/unit/` |
| **Agent B** | Apps & infrastructure | 8 items | `apps/blockchain-node/src/aitbc_chain/` (models, database, rpc, consensus, sync, mempool, state, gossip, network), `apps/blockchain-node/migrations/`, `tests/` |

**Conflict boundary**: Agent A owns `aitbc/` (except `constants.py`, `log_utils/`). Agent B owns `apps/`. No shared files are edited by both agents. Coordination is via "Agent A creates shared utility → Agent B consumes it" — see Coordination Protocol.

---

## Agent A — Shared Core (`aitbc/`)

**Scope**: Fix the `BlockchainCache` type mismatch, add an in-process block header cache, create a shared async HTTP connection pool, add a compression utility, and add benchmarking helpers. All consumed by Agent B.

**Working directory**: `/opt/aitbc/aitbc/`

**Verification command**:
```bash
cd /opt/aitbc && ./venv/bin/python -m mypy --show-error-codes aitbc/ && ./venv/bin/python -m ruff check aitbc/ && ./venv/bin/python -m pytest tests/unit -q -o addopts=""
```

### Tasks

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| A1 | Fix `BlockchainCache` — `chain_id: int` → `str`, add `get_block_by_hash`/`set_block_by_hash`, fix `block_number` → `height` naming | 🔴 P0 | `aitbc/caching/blockchain_cache.py` | ⬜ |
| A2 | Add in-process `BlockHeaderCache` (LRU, no Redis dependency) for hot-path block header access | High | `aitbc/caching/block_header_cache.py` (new), `aitbc/caching/__init__.py` | ⬜ |
| A3 | Add shared async HTTP connection pool — reusable `httpx.AsyncClient` singleton with configurable pool limits | High | `aitbc/network/http_pool.py` (new), `aitbc/network/__init__.py` | ⬜ |
| A4 | Add compression utility — gzip + zstd helpers for network payloads | Medium | `aitbc/network/compression.py` (new), `aitbc/network/__init__.py` | ⬜ |
| A5 | Add benchmarking helpers — context managers for timing DB queries, network transfers, cache hits/misses | Medium | `aitbc/benchmark.py` (new) | ⬜ |
| A6 | Unit tests for A1–A4 | High | `tests/unit/test_blockchain_cache.py`, `tests/unit/test_block_header_cache.py`, `tests/unit/test_http_pool.py`, `tests/unit/test_compression.py` | ⬜ |
| A7 | Verify mypy + ruff clean across all new/modified files | Medium | — | ⬜ |

### Agent A — Detailed Instructions

#### A1: Fix BlockchainCache typing + add block-by-hash

- **Problem**: `BlockchainCache` types `chain_id` as `int` throughout (lines 40, 44, 48, 52, 57, 65, 72, 79, 86, 93, 100, 107, 117, 127, 137). The codebase uses `chain_id: str` (e.g., `"ait-hub"`, `"ait-island1"`). The cache is unusable as-is.
- **Fix**: Change all `chain_id: int` → `chain_id: str` in `blockchain_cache.py`. Update `generate_block_key` to accept `height: int` (rename from `block_number`). Add `get_block_by_hash(hash: str, chain_id: str)` / `set_block_by_hash(hash: str, chain_id: str, block_data: Any)` methods — the codebase frequently looks up blocks by hash, not just height.
- **Verify**: `mypy aitbc/caching/` clean. `pytest tests/unit/test_blockchain_cache.py` passes.

#### A2: In-process BlockHeaderCache

- **Problem**: `BlockchainCache` requires Redis. The block import hot path needs a fast in-process cache for recently-seen block headers (no Redis round-trip per block).
- **Fix**: Create `aitbc/caching/block_header_cache.py` with a `BlockHeaderCache` class:
  - LRU eviction (configurable max size, default 1000)
  - Per-chain namespaces (key = `chain_id:height` and `chain_id:hash`)
  - `get(height, chain_id)`, `get_by_hash(hash, chain_id)`, `set(header, chain_id)`, `invalidate(chain_id, height)`
  - Thread-safe (asyncio lock or simple dict — blockchain-node is single-threaded for block processing)
- Export from `aitbc/caching/__init__.py` as `BlockHeaderCache`.
- **Verify**: Unit test: insert 100 headers, verify LRU evicts oldest, verify per-chain isolation.

#### A3: Shared async HTTP connection pool

- **Problem**: 6 files in blockchain-node create `httpx.AsyncClient` per-request (no connection reuse). Agent B will replace them, but needs a shared pool utility to wire up.
- **Fix**: Create `aitbc/network/http_pool.py` with:
  ```python
  class SharedHttpClient:
      """Singleton async HTTP client with connection pooling."""
      def __init__(self, max_connections: int = 100, max_keepalive: int = 20, timeout: float = 30.0): ...
      async def get(self, url, **kwargs) -> httpx.Response: ...
      async def post(self, url, **kwargs) -> httpx.Response: ...
      async def close(self): ...
  ```
  - Uses a single `httpx.AsyncClient` with `httpx.Limits(max_connections=..., max_keepalive_connections=...)`
  - Lazy-init: client created on first use, reused thereafter
  - Export from `aitbc/network/__init__.py`
- **Verify**: Unit test: two `get()` calls reuse the same underlying client (mock the transport).

#### A4: Compression utility

- **Problem**: Zero compression for block/tx propagation. JSON payloads are large.
- **Fix**: Create `aitbc/network/compression.py` with:
  ```python
  def compress(data: bytes | str, algorithm: str = "gzip") -> bytes: ...
  def decompress(data: bytes, algorithm: str = "gzip") -> bytes: ...
  def compress_json(obj: Any, algorithm: str = "gzip") -> bytes: ...
  def decompress_json(data: bytes, algorithm: str = "gzip") -> Any: ...
  ```
  - Support `gzip` (stdlib `gzip`) and `zstd` (if `zstandard` package available, else fall back to gzip)
  - `compress_json`: `json.dumps(separators=(",", ":"))` → encode → compress
  - `decompress_json`: decompress → decode → `json.loads`
  - Export from `aitbc/network/__init__.py`
- **Verify**: Unit test: compress/decompress round-trip, verify compressed size < raw size for typical block JSON.

#### A5: Benchmarking helpers

- Create `aitbc/benchmark.py` with:
  ```python
  @contextmanager
  def timed(label: str): ...  # logs elapsed time

  class QueryTimer: ...  # accumulates DB query times

  class CacheMetrics: ...  # tracks hit/miss counts
  ```
- Keep it simple — no external dependencies. Used by Agent B's benchmarks (B8).

#### A6: Unit tests

- `tests/unit/test_blockchain_cache.py` — A1: chain_id as str, block-by-hash, invalidation
- `tests/unit/test_block_header_cache.py` — A2: LRU eviction, per-chain isolation, get/set
- `tests/unit/test_http_pool.py` — A3: client reuse, lazy init, close
- `tests/unit/test_compression.py` — A4: round-trip, size reduction, JSON variants

#### A7: Verify clean

- `mypy aitbc/` — 0 errors
- `ruff check aitbc/` — 0 errors
- `pytest tests/unit -q` — all pass

---

## Agent B — Apps & Infrastructure

**Scope**: Add missing indexes, wire up connection pooling, eliminate N+1 queries, batch mempool operations, implement incremental state root, wire up shared HTTP pool + compression + block caching, and benchmark.

**Working directory**: `/opt/aitbc/apps/blockchain-node/`

**Verification command**:
```bash
cd /opt/aitbc && ./venv/bin/python -m pytest apps/blockchain-node/tests/ -q -o addopts="" --timeout=60
```

### Tasks

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

### Agent B — Detailed Instructions

#### B1: Add missing indexes + Alembic migration

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

#### B2: Wire up connection pooling

- **Problem**: `database.py:82,92,106` creates engines with `create_engine(sqlite_url)` — no pool config. The shared `aitbc/database/pooling.py:create_pooled_engine()` exists with proper QueuePool/StaticPool.
- **Fix**: Replace direct `create_engine` calls with `create_pooled_engine` from `aitbc.database.pooling`. For SQLite, use `use_static_pool=True` (SQLite doesn't benefit from QueuePool — single writer). For PostgreSQL (if configured), use QueuePool with configurable pool size from env.
- Also replace direct `Session(engine)` with `sessionmaker(engine)` factory pattern (lines 156, 171).
- **Verify**: `pytest apps/blockchain-node/tests/ -q` — no regressions. Engine is shared, not recreated.

#### B3: Eliminate N+1 queries

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

#### B4: Batch mempool operations

- **`drain` (mempool.py:303-311)**: Replace per-tx DELETE loop with a single `DELETE FROM mempool WHERE chain_id = ? AND tx_hash IN (...)` query.
- **`add` (mempool.py:244)**: Remove per-tx `session.commit()`. Let the caller commit (or add a `batch_add` method that takes a list and commits once).
- **`remove` (mempool:329)**: Remove per-tx `session.commit()`. Add a `batch_remove(hashes: list[str])` method.
- **Verify**: `pytest apps/blockchain-node/tests/test_mempool.py -q` passes (update tests if commit behavior changed).

#### B5: Incremental state root

- **Problem**: `poa.py:34-44` (`_compute_state_root`) loads ALL accounts and creates a new trie per block. `StateManager.update_account()` (line 388) exists but is unused.
- **Fix**: Maintain a persistent `MerklePatriciaTrie` instance per chain (cached in the `PoAProposer` or a `StateManager` singleton). After each tx's state transition, call `update_account(address, balance, nonce)` to incrementally update the trie. The state root is then `trie.get_root()` — no full recompute needed.
- **In `poa.py`**: Replace the `_compute_state_root(session, chain_id)` call (line 341) with the incremental root from the maintained trie.
- **In `sync.py`**: When importing blocks, after applying state transitions, use the incremental update path. For initial sync (full state import), keep the full recompute as a fallback.
- **⚠️ Risk**: This changes the state root computation path. Must verify that the incremental root matches the full recompute root for the same state. Add a test that compares both methods.
- **Verify**: New test: `test_incremental_state_root_matches_full_recompute` — apply 100 txs incrementally, then full recompute, assert roots match.

#### B6: Wire up shared HTTP client pool

- **Problem**: 6 files create `httpx.AsyncClient` per-request. Agent A's `SharedHttpClient` (A3) provides a pooled alternative.
- **Fix**: Replace `async with httpx.AsyncClient(timeout=...) as client:` with `await shared_client.get/post(...)` in:
  - `consensus/poa.py:594,627` — genesis block/allocations fetch
  - `chain_sync.py:105,206` — broadcast/import (replace `aiohttp.ClientSession` too, or keep aiohttp but make it a shared session)
  - `network/hub_discovery.py:100,131` — hub discovery
  - `rpc/escrow_routes.py:58` — escrow RPC
  - `main.py:398` — startup health check
- Import `SharedHttpClient` from `aitbc.network`.
- **Verify**: `pytest apps/blockchain-node/tests/ -q` — no regressions. No new `httpx.AsyncClient()` calls in the diff.

#### B7: Wire up compression + block header caching

**Compression** (using A4's `compress_json`/`decompress_json`):
- `gossip/broker.py:326-329` — compress messages before publish, decompress on receive
- `chain_sync.py:186` — compress block data before Redis publish
- `p2p_network.py:141` — compress P2P TCP payloads
- Add a `NETWORK_COMPRESSION_ENABLED=true` env flag (default true) so it can be disabled for debugging

**Block header caching** (using A1's fixed `BlockchainCache` + A2's `BlockHeaderCache`):
- `rpc/blocks.py` — cache `get_block` responses using `BlockHeaderCache` (in-process, hot path) + `BlockchainCache` (Redis, cold path)
- `rpc/accounts.py` — already has Redis caching; wire up `BlockchainCache` for consistency
- Invalidate cache on new block import (`poa.py` after `session.commit()`)
- **Verify**: `pytest apps/blockchain-node/tests/test_rpc_router.py -q` passes. New test: cache hit returns same data as DB query.

#### B8: Performance benchmarks

- Create `apps/blockchain-node/tests/test_performance.py` with:
  - `test_db_query_latency` — measure block/tx/account query times, assert <5ms 95th percentile
  - `test_cache_hit_rate` — insert 100 blocks, query them 1000 times, assert >80% cache hit
  - `test_mempool_query_latency` — measure `get_pending` / `drain` latency, assert <5ms
  - `test_compression_ratio` — compress a typical block JSON, assert >50% size reduction
  - `test_batch_vs_individual_writes` — compare batch vs per-tx mempool adds
- Use Agent A's `aitbc/benchmark.py` helpers (A5).
- Mark as `@pytest.mark.slow` so they don't run in the default gate.
- **Verify**: `pytest apps/blockchain-node/tests/test_performance.py -q -m slow` passes.

---

## Coordination Protocol

### File Ownership

| File | Owner | Notes |
|------|-------|-------|
| `aitbc/caching/blockchain_cache.py` | Agent A | A1: fix typing + add methods |
| `aitbc/caching/block_header_cache.py` | Agent A | A2: new file |
| `aitbc/caching/__init__.py` | Agent A | A2: export new class |
| `aitbc/network/http_pool.py` | Agent A | A3: new file |
| `aitbc/network/compression.py` | Agent A | A4: new file |
| `aitbc/network/__init__.py` | Agent A | A3, A4: export new utilities |
| `aitbc/benchmark.py` | Agent A | A5: new file |
| `aitbc/database/pooling.py` | Agent A | Already exists — no changes expected |
| `apps/blockchain-node/src/aitbc_chain/base_models.py` | Agent B | B1: add indexes |
| `apps/blockchain-node/migrations/versions/` | Agent B | B1: new migration |
| `apps/blockchain-node/src/aitbc_chain/database.py` | Agent B | B2: wire up pooling |
| `apps/blockchain-node/src/aitbc_chain/rpc/blocks.py` | Agent B | B3a, B7: N+1 fix + caching |
| `apps/blockchain-node/src/aitbc_chain/consensus/poa.py` | Agent B | B3b, B5, B6: N+1 fix + state root + HTTP pool |
| `apps/blockchain-node/src/aitbc_chain/sync.py` | Agent B | B3c, B5, B6: N+1 fix + state root + HTTP pool |
| `apps/blockchain-node/src/aitbc_chain/mempool.py` | Agent B | B4: batch operations |
| `apps/blockchain-node/src/aitbc_chain/state/merkle_patricia_trie.py` | Agent B | B5: incremental state root |
| `apps/blockchain-node/src/aitbc_chain/gossip/broker.py` | Agent B | B7: compression |
| `apps/blockchain-node/src/aitbc_chain/chain_sync.py` | Agent B | B6, B7: HTTP pool + compression |
| `apps/blockchain-node/src/aitbc_chain/p2p_network.py` | Agent B | B7: compression |

### Dependency Graph

```
Phase 1 (Agent A — parallel, no dependencies):
  A1 fix BlockchainCache typing
  A2 BlockHeaderCache
  A3 SharedHttpClient
  A4 compression utility
  A5 benchmarking helpers
  A6 unit tests
  A7 verify clean

Phase 2 (Agent B — after A1-A4 are merged):
  B1 indexes + migration        (independent of A)
  B2 connection pooling         (uses existing aitbc/database/pooling.py — no A dependency)
  B3 N+1 elimination            (independent of A)
  B4 batch mempool              (independent of A)

Phase 3 (Agent B — after A1-A4 + B1-B4):
  B5 incremental state root     (independent of A)
  B6 wire up HTTP pool          (depends on A3)
  B7 wire up compression+cache  (depends on A1, A2, A4)
  B8 benchmarks                 (depends on A5, all B tasks)
```

**B1–B4 can start in parallel with A1–A7** — they don't depend on Agent A's new utilities (B2 uses the already-existing `aitbc/database/pooling.py`). Only B6, B7, B8 depend on Agent A's new code.

---

## Success Criteria

- ✅ All new indexes added + Alembic migration runs cleanly
- ✅ Connection pooling wired up (no bare `create_engine` calls in `database.py`)
- ✅ N+1 queries eliminated in `blocks.py`, `poa.py`, `sync.py` (verified by query count in tests)
- ✅ Mempool `drain` uses batch DELETE; `add`/`remove` don't commit per-tx
- ✅ Incremental state root matches full recompute (verified by test)
- ✅ No per-request `httpx.AsyncClient()` in blockchain-node (all use `SharedHttpClient`)
- ✅ Network compression enabled (gossip, P2P, Redis pub/sub)
- ✅ Block header caching operational (in-process LRU + Redis)
- ✅ `BlockchainCache` uses `chain_id: str` (matches codebase)
- ✅ Performance benchmarks pass (query <5ms, cache >80%, compression >50%)
- ✅ `pytest apps/blockchain-node/tests/` — 0 failed, 0 errors
- ✅ `pytest tests/unit` — 0 failed (Agent A's new tests pass)
- ✅ `mypy aitbc/` + `ruff check .` — clean
- ✅ No parallel processing changes (sequential tx loop unchanged)
