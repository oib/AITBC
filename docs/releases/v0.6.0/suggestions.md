## Preparation Phase
- Verify that all prerequisite releases are merged and tagged.
- Set up a test environment matching the target release's dependencies.
- Run existing test suite to ensure baseline passes before coding.
- Review the CHANGELOG and any linked design documents for ambiguities.
- Coordinate with relevant agents (A/B) to clarify file ownership and avoid conflicts.

# v0.6.0 Suggestions

## Status
**RESCOPED + INVESTIGATED** — Performance targets that depend on parallel processing (block import >500/sec, tx validation <10ms, mempool >5,000/sec) have been moved to v0.6.1. v0.6.0 is now scoped to DB/network/caching only. Full codebase investigation completed — all gaps resolved with concrete file paths, line numbers, and index definitions.

## Resolved Issues
- ~~Remove or defer performance targets that depend on v0.6.1 (parallel validation)~~ → Done. Block/tx processing targets moved to v0.6.1.
- ~~Changelog is vague: no concrete code targets, no file paths~~ → Scope clarification added with file/line references (poa.py lines 239-327, merkle_patricia_trie.py lines 402-419).
- ~~Still missing: how new indexes are defined (Alembic vs create_all)~~ → **Resolved**: Alembic migrations with `if_not_exists=True` (pattern exists in coordinator-api's `add_query_performance_indexes.py`). Blockchain-node has Alembic set up (`apps/blockchain-node/migrations/`).
- ~~Still missing: Redis/Memcached bootstrap and configuration strategy~~ → **Resolved**: `aitbc/caching/redis_cache.py` already exists with in-memory fallback. Config: `REDIS_URL`, `CACHE_BACKEND=redis|memory`. See change.log migration guide step 2.
- ~~Still missing: test strategy for caching behavior~~ → **Resolved**: Cache key schema `{chain_id}:{type}:{key}` with per-layer TTL (see change.log CACHE_KEY_SCHEMA section).
- ~~No baseline performance measurements exist~~ → **Resolved**: Baseline benchmark plan added (see change.log "Baseline Benchmarks" section).

## Gaps
All 4 original gaps resolved. No remaining gaps.

## Recommendations (all addressed in change.log)
1. ~~Add precise code touchpoints~~ → **Done**: DB_INDEX_DEFINITIONS, CACHE_KEY_SCHEMA, and "Verified Code Targets" sections in change.log.
2. ~~Define cache invalidation per chain~~ → **Done**: Cache keys include `chain_id`; TTL per layer defined.
3. ~~Benchmark current performance first~~ → **Done**: Baseline benchmark plan with target directory `benchmarks/v0.6.0-baseline/`.
4. ~~Specify cache backend (in-process, Redis, or both)~~ → **Done**: Both — in-process LRU for hot data (block headers), Redis for shared state (account balances). `RedisCache` already falls back to in-memory.
5. ~~Use Alembic migrations for new indexes~~ → **Done**: Migration approach documented. Pattern: `op.create_index(..., if_not_exists=True)`.

## Investigation Results (verified at v0.5.18)

### Missing Indexes (P0)
| Table | Column(s) | Query Location | Index Type |
|-------|-----------|----------------|------------|
| `block` | `parent_hash` | `sync.py:542` | Single |
| `transaction` | `sender` | balance lookups | Single |
| `transaction` | `recipient` | incoming transfer lookups | Single |
| `transaction` | `(chain_id, block_height)` | `rpc/blocks.py:139` | Composite |
| `cross_chain_transfer` | `status` | `cross_chain/bridge.py:229` | Single |
| `stake` | `status` | `rpc/staking.py:365,415` | Single |
| `governance_proposal` | `status` | `rpc/staking.py:305,365,415` | Single |
| `mempool` | `(chain_id, fee)` | `mempool.py:256,276` | Composite |

### N+1 Query Hotspots
- `rpc/blocks.py:127-142` — per-block transaction fetch loop
- `consensus/poa.py:239-327` — 3 DB calls per tx in block proposal
- `sync.py:433-451` — per-account `session.get()` in account sync

### Connection Pooling
- `database.py:82,92,106` — `create_engine()` with zero pool config
- `aitbc/database/pooling.py` — `create_pooled_engine()` exists but unused

### Caching
- `aitbc/caching/redis_cache.py` — RedisCache with in-memory fallback (exists, used in `rpc/accounts.py`)
- `aitbc/caching/blockchain_cache.py` — BlockchainCache exists but **type mismatch** (`chain_id: int` vs `str`)
- Block header caching: **absent** — no in-process cache for hot block headers

### Mempool Issues
- `mempool.py:244` — per-tx `session.commit()` in `add()`
- `mempool.py:329` — per-tx `session.commit()` in `remove()`
- `mempool.py:303-311` — per-tx DELETE loop in `drain()` (should batch)

### Network
- `gossip/broker.py:154` — JSON only, no compression
- 6 files create `httpx.AsyncClient` per-request (no shared connection pool)
