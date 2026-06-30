# v0.6.0 Database & Network Optimization — Overview

**Last Updated**: 2026-06-30
**Version**: 1.0

**Release Theme**: Database & Network Optimization — query indexing, connection pooling, N+1 elimination, batch writes, block header caching, network compression, and shared HTTP client pooling. No parallel processing (that's v0.6.1).

**Goal**: Achieve measurable DB/network/caching performance gains with low regression risk. All changes are additive (indexes, pools, cache layers, batch fetches) — the sequential transaction loop in `poa.py` and full state root recompute architecture stay as-is; only the I/O around them is optimized.

> **Scope constraint**: No parallel processing, no architectural changes to the tx loop. Block import rate / tx validation latency targets are v0.6.1. This release targets: query latency <5ms (95th percentile), cache hit rate >80%, mempool query latency <5ms, network compression >50%.

> **Prerequisites**: [v0.5.18](../v0.5.18/change.log) (green blockchain-node test suite — the regression baseline).

---

## Documentation Structure

This release documentation has been split into topic-focused files:

- **[Overview](./overview.md)** - Release overview, status baseline, and task split overview
- **[Agent A Tasks](./agent-a.md)** - Shared core implementation (cache fixes, HTTP pool, compression, benchmarking)
- **[Agent B Tasks](./agent-b.md)** - Apps & infrastructure implementation (indexes, connection pooling, N+1 elimination, batch operations)

---

## Quick Navigation

### Overview
- [Status Baseline](#status-baseline--verified-code-targets-from-subagent-investigation)
- [Task Split Overview](#task-split-overview)

### Agent A (Shared Core)
- [Scope](./agent-a.md#scope)
- [Tasks](./agent-a.md#tasks)
- [Fix BlockchainCache typing](./agent-a.md#a1-fix-blockchaincache-typing--add-block-by-hash)
- [In-process BlockHeaderCache](./agent-a.md#a2-in-process-blockheadercache)
- [Shared async HTTP connection pool](./agent-a.md#a3-shared-async-http-connection-pool)
- [Compression utility](./agent-a.md#a4-compression-utility)
- [Benchmarking helpers](./agent-a.md#a5-benchmarking-helpers)
- [Unit tests](./agent-a.md#a6-unit-tests)
- [Verify clean](./agent-a.md#a7-verify-clean)

### Agent B (Apps & Infrastructure)
- [Scope](./agent-b.md#scope)
- [Tasks](./agent-b.md#tasks)
- [Add missing indexes](./agent-b.md#b1-add-missing-indexes--alembic-migration)
- [Wire up connection pooling](./agent-b.md#b2-wire-up-connection-pooling)
- [Eliminate N+1 queries](./agent-b.md#b3-eliminate-n1-queries)
- [Batch mempool operations](./agent-b.md#b4-batch-mempool-operations)
- [Incremental state root](./agent-b.md#b5-incremental-state-root)
- [Wire up shared HTTP client pool](./agent-b.md#b6-wire-up-shared-http-client-pool)
- [Wire up compression + block header caching](./agent-b.md#b7-wire-up-compression--block-header-caching)
- [Performance benchmarks](./agent-b.md#b8-performance-benchmarks--verify-targets)

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

## Related Topics

- [Agent A Tasks](./agent-a.md) - Shared core implementation details
- [Agent B Tasks](./agent-b.md) - Apps & infrastructure implementation details

---

**Documentation Version**: 1.0
**Last Updated**: 2026-06-30
**Release**: v0.6.0 — Database & Network Optimization
