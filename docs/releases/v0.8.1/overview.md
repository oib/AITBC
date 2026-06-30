# v0.8.1 Cross-Chain Offer Synchronization — Overview

**Last Updated**: 2026-06-30
**Version**: 1.0

**Release Theme**: Cross-Chain Offer Synchronization — Distributed Offer Discovery, Polling-Based Sync, Staleness Detection, Conflict Resolution

**Goal**: Build a cross-chain offer synchronization layer on top of the v0.8.0 trading service. Enable agents to discover offers on other AITBC chains, keep offer state synchronized across the network via polling, detect stale offers, and resolve conflicts. Defer subscription-based sync (WebSocket) and external search index (Elasticsearch) to future releases.

> **Rescope from original change.log**: The original v0.8.1 change.log bundled polling-based sync + subscription-based sync + real-time WebSocket + external search index into one release. Per the user's analysis (confirmed) and codebase investigation:
> - ✅ v0.8.1: Polling-based sync, local offer cache (Redis), staleness detection, conflict resolution, CLI discover/sync/sync-status commands
> - ➡️ Future (v0.8.2+): Subscription-based sync (WebSocket), real-time offer notifications, external search index (Elasticsearch/Meilisearch)
> - The user's recommendation to start with polling-only sync is adopted — subscription adds WebSocket complexity (auth, reconnection, backpressure) that can be deferred.

> **Stale prerequisite correction**: The user's analysis claimed "v0.8.0 is a Concept Plan (no trading service exists yet)" — this is **FALSE**. `apps/trading/` exists (1011 lines) and v0.8.0 Agent A is complete (`939bb066f` — `aitbc/trading/` SDK with types, client, bridge utilities). v0.8.0 Agent B is pending but the trading service app exists with FastAPI, domain models, and service layer. v0.8.1 can proceed after v0.8.0 Agent B completes.

> **Prerequisites**: [v0.8.0](../v0.8.0/change.log) (Agent A ✅ `939bb066f`, Agent B ⬜ pending), [v0.7.0](../v0.7.0/change.log) ✅, [v0.7.1](../v0.7.1/change.log) ✅, [v0.7.2](../v0.7.2/change.log) ✅, [v0.6.6](../v0.6.6/change.log) ✅ (Marketplace + OfferFSM + BlockchainRPCClient).

> **Risk**: Medium. Offer sync is an off-chain service layer — no consensus-critical path is touched. The main risk is cache consistency (stale offers → failed trades) and bandwidth management (polling all chains). Redis is already used in the codebase for caching and pub/sub.

---

## Documentation Structure

This release documentation has been split into topic-focused files:

- **[Overview](./overview.md)** - Release overview, status baseline, and task split overview
- **[Agent A Tasks](./agent-a.md)** - Shared core implementation (offer sync types, client, cache)
- **[Agent B Tasks](./agent-b.md)** - Apps & infrastructure implementation (sync service, endpoints, CLI, tests)

---

## Quick Navigation

### Overview
- [Status Baseline](#status-baseline--verified-code-targets-2026-06-29)
- [Task Split Overview](#task-split-overview)

### Agent A (Shared Core)
- [Scope](./agent-a.md#scope)
- [Tasks](./agent-a.md#tasks)
- [Offer sync types](./agent-a.md#a1-offer-sync-types)
- [Offer sync client](./agent-a.md#a2-offer-sync-client)
- [Offer cache](./agent-a.md#a3-offer-cache)
- [Unit tests](./agent-a.md#a4-unit-tests)

### Agent B (Apps & Infrastructure)
- [Scope](./agent-b.md#scope)
- [Tasks](./agent-b.md#tasks)
- [Offer sync config](./agent-b.md#b1-offer-sync-config)
- [Offer sync service](./agent-b.md#b2-offer-sync-service)
- [Discovery endpoint](./agent-b.md#b3-discovery-endpoint)
- [Sync endpoints](./agent-b.md#b4-sync-endpoints)
- [CLI commands](./agent-b.md#b5-cli-commands)
- [Tests](./agent-b.md#b6-tests)

---

## Status Baseline — Verified Code Targets (2026-06-29)

| Component | Location | Current State | v0.8.1 Target |
|-----------|----------|---------------|---------------|
| **IslandManager** | `apps/blockchain-node/src/aitbc_chain/network/island_manager.py` (284 lines) | ✅ EXISTS — 20 methods, all membership/bridge. Zero offer sync. | NOT modified — offer sync is a separate service layer |
| **MarketplaceOffer model** | `packages/aitbc-shared/aitbc_shared/models/marketplace.py` (58 lines) | ✅ EXISTS — provider, capacity, price, sla, status, gpu_model, region, **chain_id** (v0.6.6) | Used as the offer schema for sync (already chain-aware) |
| **OfferFSM** | `aitbc/marketplace/offer_fsm.py` (100 lines) | ✅ EXISTS — 5 states (AVAILABLE, RESERVED, IN_USE, DELISTED, EXPIRED), validated transitions | Used for offer status validation during sync |
| **BlockchainRPCClient** | `aitbc/marketplace/blockchain_rpc.py` (141 lines) | ✅ EXISTS — query_offers, get_offer, submit_transaction, register_gpu, allocate_gpu (chain-aware) | Used by offer sync service to query offers from each chain |
| **GPU resource RPC** | `apps/blockchain-node/src/aitbc_chain/rpc/gpu_resources.py` (288 lines) | ✅ EXISTS — GET /rpc/gpus (with chain_id filter), GET /rpc/gpu/info/{gpu_id}, POST /rpc/gpu/register | Offer sync polls these endpoints per chain |
| **Marketplace RPC** | `apps/blockchain-node/src/aitbc_chain/rpc/marketplace.py` (179 lines) | ✅ EXISTS — GET /marketplace/listings (queries GPU_MARKETPLACE txs), POST /marketplace/create | Offer sync can also poll marketplace listings |
| **Transaction query RPC** | `apps/blockchain-node/src/aitbc_chain/rpc/transactions.py:172-249` | ✅ EXISTS — GET /rpc/transactions with transaction_type, chain_id, status filters | Offer sync queries GPU_MARKETPLACE transactions per chain |
| **RedisCache** | `aitbc/caching/redis_cache.py` (72 lines) | ✅ EXISTS — get/set/delete with TTL, fallback to in-memory dict | Reused for offer cache with TTL + staleness |
| **BlockchainCache** | `aitbc/caching/blockchain_cache.py` | ✅ EXISTS — wraps RedisCache for blocks, transactions, balances | Pattern to follow for OfferCache |
| **Gossip broker** | `apps/blockchain-node/src/aitbc_chain/gossip/broker.py` | ✅ EXISTS — InMemoryGossipBackend + BroadcastGossipBackend (Redis pub/sub) | Can be used for offer change notifications (future) |
| **WebSocket endpoints** | `apps/blockchain-node/src/aitbc_chain/rpc/websocket.py` | ✅ EXISTS — /rpc/blocks, /rpc/transactions, /rpc/subscribe/ws | NOT used in v0.8.1 (polling only); subscription deferred |
| **Trading SDK (v0.8.0)** | `aitbc/trading/` (4 modules) | ✅ EXISTS — types, client, bridge utilities | Extended with offer sync types + client methods |
| **Trading service (v0.8.0)** | `apps/trading/src/trading_service/` (1011 lines) | ✅ EXISTS — FastAPI, domain models, service layer | Extended with offer sync service + endpoints |
| **InterChainTrade model** | `apps/trading/src/trading_service/domain/inter_chain.py` (v0.8.0 Agent B) | ⬜ PENDING — Agent B B2 will create this | Has `offer_id` field for linking trades to offers |
| **IslandRegistryEntry model** | `apps/trading/src/trading_service/domain/inter_chain.py` (v0.8.0 Agent B) | ⬜ PENDING — Agent B B2 will create this | Has `offers_count` + `last_sync` fields for sync tracking |
| **CLI trade commands** | `cli/aitbc_cli/commands/trade.py` (v0.8.0 Agent B) | ⬜ PENDING — Agent B B7 will create this | Extended with discover, sync, sync-status subcommands |
| **Offer sync service** | — | ❌ NONE — no offer sync code anywhere | Create OfferSyncService (polling loop per chain) |
| **Offer cache** | — | ❌ NONE — no offer-specific cache | Create OfferCache (wraps RedisCache with offer-specific TTLs) |
| **Staleness config** | — | ❌ NONE — no staleness config in codebase | Add per-chain staleness thresholds to trading config |
| **Distributed search index** | — | ❌ NONE — no Elasticsearch/Meilisearch | DEFERRED — v0.8.1 uses local cache + in-memory search |

### Already Fixed / Exists (verified — no work needed)

1. ✅ **MarketplaceOffer model exists** — chain-aware (chain_id field, v0.6.6), with provider, capacity, price, gpu_model, region, status
2. ✅ **OfferFSM exists** — 5 states with validated transitions (AVAILABLE → RESERVED → IN_USE → AVAILABLE/DELISTED)
3. ✅ **BlockchainRPCClient exists** — chain-aware, query_offers(chain_id, status, gpu_model, region, limit)
4. ✅ **GPU resource RPC exists** — GET /rpc/gpus with chain_id filter, GET /rpc/gpu/info/{gpu_id}
5. ✅ **Transaction query RPC exists** — GET /rpc/transactions with transaction_type + chain_id filters
6. ✅ **RedisCache exists** — get/set/delete with TTL, fallback to in-memory dict
7. ✅ **Gossip broker exists** — InMemory + Redis pub/sub backends (for future subscription-based sync)
8. ✅ **WebSocket endpoints exist** — /rpc/blocks, /rpc/transactions (for future subscription-based sync)
9. ✅ **v0.8.0 trading SDK exists** — types (InterChainTradeData, ChainInfo, TradeMatchResult), TradingClient, TradingBridgeClient
10. ✅ **v0.7.0-v0.7.2 bridge complete** — 15 bridge RPC endpoints available

---

## Task Split Overview

| Agent | Domain | Tasks | Files |
|-------|--------|-------|-------|
| **Agent A** | Shared core (`aitbc/`) | 4 items | `aitbc/trading/offer_types.py` (new), `aitbc/trading/offer_client.py` (new), `aitbc/trading/offer_cache.py` (new), `tests/unit/` |
| **Agent B** | Apps & infrastructure | 6 items | `apps/trading/src/trading_service/`, `cli/aitbc_cli/commands/trade.py` (extend), `apps/trading/tests/` |

**Conflict boundary**: Agent A owns `aitbc/trading/` (extend v0.8.0 SDK). Agent B owns `apps/trading/` and `cli/`. Agent B consumes Agent A's offer sync types, client, and cache.

**Sequencing**: Agent A goes first (shared SDK). Agent B starts after Agent A completes A1-A3. B1 (config) can proceed in parallel with Agent A.

---

## Related Topics

- [Agent A Tasks](./agent-a.md) - Shared core implementation details
- [Agent B Tasks](./agent-b.md) - Apps & infrastructure implementation details

---

**Documentation Version**: 1.0
**Last Updated**: 2026-06-30
**Release**: v0.8.1 — Cross-Chain Offer Synchronization
