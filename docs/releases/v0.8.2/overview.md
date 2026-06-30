# v0.8.2 Advanced Offer Sync — Overview

**Last Updated**: 2026-06-30
**Version**: 1.0

**Release Theme**: Advanced Offer Sync — Subscription-Based Sync, Real-Time Notifications, Gossip Propagation, Optional Search Index

**Goal**: Upgrade cross-chain offer synchronization from polling-based (v0.8.1) to subscription-based with real-time notifications. Offers are pushed to subscribers via WebSocket and gossip pub/sub, eliminating polling latency. Optional external search index for advanced queries.

> **Not on the critical path**: v0.9.0 (Atomic Cross-Chain Settlement) does NOT depend on v0.8.2. v0.9.0 only needs v0.8.1's polling-based sync. v0.8.2 is an enhancement release that can ship after v0.9.0 or in parallel.

> **Prerequisites**: [v0.8.1](../v0.8.1/change.log) (Agent A ✅ `b3f3ef57d`, Agent B ⬜ pending), [v0.8.0](../v0.8.0/change.log), [v0.7.0](../v0.7.0/change.log) ✅, [v0.7.1](../v0.7.1/change.log) ✅, [v0.7.2](../v0.7.2/change.log) ✅.

> **Risk**: Low-Medium. This is an enhancement layer on v0.8.1. No consensus-critical path is touched. The main risk is WebSocket connection management (reconnection, backpressure) and gossip event ordering. Polling-based sync (v0.8.1) remains as fallback.

---

## Documentation Structure

This release documentation has been split into topic-focused files:

- **[Overview](./overview.md)** - Release overview, status baseline, and task split overview
- **[Agent A Tasks](./agent-a.md)** - Shared core implementation (offer event types, subscription client, search index)
- **[Agent B Tasks](./agent-b.md)** - Apps & infrastructure implementation (WebSocket endpoints, gossip integration, CLI, tests)

---

## Quick Navigation

### Overview
- [Status Baseline](#status-baseline--verified-code-targets-2026-06-29)
- [Task Split Overview](#task-split-overview)

### Agent A (Shared Core)
- [Scope](./agent-a.md#scope)
- [Tasks](./agent-a.md#tasks)
- [Offer event types](./agent-a.md#a1-offer-event-types)
- [Offer subscription client](./agent-a.md#a2-offer-subscription-client)
- [Search index integration](./agent-a.md#a3-search-index-integration-optional)
- [Unit tests](./agent-a.md#a4-unit-tests)

### Agent B (Apps & Infrastructure)
- [Scope](./agent-b.md#scope)
- [Tasks](./agent-b.md#tasks)
- [Offer event publishing](./agent-b.md#b1-offer-event-publishing)
- [Offer WebSocket endpoint](./agent-b.md#b2-offer-websocket-endpoint)
- [Gossip integration](./agent-b.md#b3-gossip-integration)
- [Subscription endpoints](./agent-b.md#b4-subscription-endpoints)
- [CLI commands](./agent-b.md#b5-cli-commands)
- [Tests](./agent-b.md#b6-tests)

---

## Status Baseline — Verified Code Targets (2026-06-29)

| Component | Location | Current State | v0.8.2 Target |
|-----------|----------|---------------|---------------|
| **WebSocket infrastructure** | `apps/blockchain-node/src/aitbc_chain/rpc/websocket.py` (136 lines) | ✅ EXISTS — `/rpc/blocks`, `/rpc/transactions`, `/rpc/subscribe/ws` (lease-based) | Pattern to follow for offer subscription endpoint |
| **Gossip broker** | `apps/blockchain-node/src/aitbc_chain/gossip/broker.py` (511 lines) | ✅ EXISTS — InMemory + Redis pub/sub, dedup, priority queue | Add `offers.{chain_id}` topic for offer change events |
| **Gossip relay** | `apps/blockchain-node/src/aitbc_chain/gossip/relay.py` (138 lines) | ✅ EXISTS — HTTP POST + WebSocket for gossip messages | NOT modified (relay is standalone, not in blockchain-node app) |
| **SubscriptionClient** | `apps/blockchain-node/src/aitbc_chain/subscription_client.py` (405 lines) | ✅ EXISTS — 3 transports (websocket, http, redis), reconnection, lease mgmt | Pattern to follow for offer subscription client |
| **RedisCache** | `aitbc/caching/redis_cache.py` (72 lines) | ✅ EXISTS — get/set/delete with TTL, in-memory fallback | Already used by OfferCache (v0.8.1) |
| **BlockchainCache invalidation** | `aitbc/caching/blockchain_cache.py` (224 lines) | ✅ EXISTS — `subscribe_to_invalidation()`, `_notify_subscribers()` | Pattern to follow for OfferCache invalidation |
| **OfferCache** | `aitbc/trading/offer_cache.py` (221 lines, v0.8.1) | ✅ EXISTS — get/set/delete, staleness tracking, sync metadata | Extend with real-time invalidation on gossip events |
| **OfferSyncClient** | `aitbc/trading/offer_client.py` (150 lines, v0.8.1) | ✅ EXISTS — async HTTP client for offer sync endpoints | Extend with WebSocket subscription methods |
| **Offer types** | `aitbc/trading/offer_types.py` (208 lines, v0.8.1) | ✅ EXISTS — OfferSyncStatus, SyncedOffer, OfferSyncConfig, etc. | Extend with subscription types (OfferEvent, OfferSubscription) |
| **Offer event system** | — | ❌ NONE — no offer_change notifications anywhere | Create offer event publishing + subscription |
| **Offer WebSocket endpoint** | — | ❌ NONE — no `/v1/trading/offers/subscribe` | Create WebSocket endpoint for offer streaming |
| **Offer gossip topic** | — | ❌ NONE — no `offers.{chain_id}` topic | Add offer change events to gossip broker |
| **External search index** | — | ❌ NONE — no Elasticsearch/Meilisearch | Optional: integrate Meilisearch (preferred) or Elasticsearch |
| **Real-time notification system** | — | ❌ NONE — no saved query subscriptions | Create watch/notify system with debounced batches |

### Already Fixed / Exists (verified — no work needed)

1. ✅ **WebSocket infrastructure exists** — lease-based auth, heartbeat, subscriber tracking (`websocket.py`)
2. ✅ **Gossip broker exists** — Redis pub/sub, dedup, priority queue (`broker.py`)
3. ✅ **SubscriptionClient pattern exists** — 3 transports, reconnection, lease management (`subscription_client.py`)
4. ✅ **RedisCache exists** — TTL, in-memory fallback (`redis_cache.py`)
5. ✅ **BlockchainCache invalidation pattern exists** — subscribe_to_invalidation, _notify_subscribers (`blockchain_cache.py`)
6. ✅ **OfferCache exists** (v0.8.1) — staleness tracking, chain-scoped queries
7. ✅ **OfferSyncClient exists** (v0.8.1) — async HTTP client
8. ✅ **Offer types exist** (v0.8.1) — OfferSyncStatus, SyncedOffer, OfferSyncConfig, etc.
9. ✅ **v0.8.1 polling-based sync exists** — remains as fallback when subscription fails

---

## Task Split Overview

| Agent | Domain | Tasks | Files |
|-------|--------|-------|-------|
| **Agent A** | Shared core (`aitbc/`) | 4 items | `aitbc/trading/offer_types.py` (extend), `aitbc/trading/offer_subscription_client.py` (new), `aitbc/trading/search_index.py` (new, optional), `tests/unit/` |
| **Agent B** | Apps & infrastructure | 6 items | `apps/trading/src/trading_service/`, `apps/blockchain-node/src/aitbc_chain/`, `cli/aitbc_cli/commands/trade.py` (extend), `apps/trading/tests/` |

**Conflict boundary**: Agent A owns `aitbc/trading/` (extend v0.8.1 SDK). Agent B owns `apps/trading/`, `apps/blockchain-node/`, and `cli/`. Agent B consumes Agent A's offer event types, subscription client, and search index.

**Sequencing**: Agent A goes first (shared SDK). Agent B starts after Agent A completes A1-A2. B1 (event publishing) can proceed in parallel with Agent A.

---

## Related Topics

- [Agent A Tasks](./agent-a.md) - Shared core implementation details
- [Agent B Tasks](./agent-b.md) - Apps & infrastructure implementation details

---

**Documentation Version**: 1.0
**Last Updated**: 2026-06-30
**Release**: v0.8.2 — Advanced Offer Sync
