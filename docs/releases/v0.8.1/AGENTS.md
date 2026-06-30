# v0.8.1 — Agent Task Assignment

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

### Architecture: Cross-Chain Offer Sync (v0.8.1)

```
┌──────────────────────────────────────────────────────────────────────┐
│ Shared Core (aitbc/trading/ — EXTEND v0.8.0 SDK)                    │
│                                                                      │
│  Offer sync types (A1 — NEW offer_types.py):                         │
│    OfferSyncStatus enum — fresh, stale, syncing, error               │
│    SyncedOffer — cached offer with sync metadata                     │
│    OfferSyncConfig — per-chain sync intervals + staleness thresholds │
│    OfferDiscoveryRequest — discovery query with filters              │
│    OfferDiscoveryResult — ranked, deduplicated results               │
│                                                                      │
│  Offer sync client (A2 — NEW offer_client.py):                       │
│    OfferSyncClient — async HTTP client for offer sync endpoints      │
│    discover_offers, sync_offers, get_sync_status, get_offer_cache    │
│                                                                      │
│  Offer cache (A3 — NEW offer_cache.py):                              │
│    OfferCache — wraps RedisCache for offer-specific caching          │
│    get_offer, set_offer, delete_offer, list_offers_by_chain          │
│    is_stale, refresh_stale_offers, get_sync_metadata                 │
│    Fallback to in-memory dict when Redis unavailable                 │
└──────────────────────────────────────────────────────────────────────┘
         ↑ consumed by                    ↑ consumed by
┌─────────────────────────┐    ┌──────────────────────────────────────┐
│ CLI (cli/aitbc_cli/)    │    │ Trading Service                      │
│                         │    │ (apps/trading/)                      │
│  trade discover         │    │                                      │
│  trade sync             │    │  Offer sync config (B1):             │
│  trade sync-status      │    │    Settings extensions (sync_enabled,│
│                         │    │    sync_interval, staleness_thresholds)│
│  Uses OfferSyncClient   │    │                                      │
│  (A2) + offer types     │    │  Offer sync service (B2):            │
│                         │    │    OfferSyncService — polling loop   │
│                         │    │    Per-chain sync intervals          │
│                         │    │    Incremental sync (since last_sync)│
│                         │    │    Conflict resolution (source-wins) │
│                         │    │    Staleness detection + refresh     │
│                         │    │                                      │
│                         │    │  Discovery endpoint (B3):            │
│                         │    │    POST /v1/trading/offers/discover  │
│                         │    │    Queries OfferCache (A3)           │
│                         │    │    Triggers on-demand sync if stale  │
│                         │    │                                      │
│                         │    │  Sync endpoints (B4):                │
│                         │    │    POST /v1/trading/offers/sync      │
│                         │    │    GET /v1/trading/offers/sync-status│
│                         │    │                                      │
│                         │    │  CLI commands (B5):                  │
│                         │    │    trade discover, sync, sync-status │
│                         │    │                                      │
│                         │    │  Tests (B6):                         │
│                         │    │    Sync, discovery, staleness,       │
│                         │    │    conflict resolution               │
└─────────────────────────┘    └──────────────────────────────────────┘

  Blockchain Node (apps/blockchain-node/) — NOT modified in v0.8.1:
    Existing RPC endpoints used by offer sync:
    - GET /rpc/gpus (with chain_id filter) — query GPU offers
    - GET /rpc/gpu/info/{gpu_id} — get single offer
    - GET /rpc/transactions?transaction_type=GPU_MARKETPLACE — query offer txs
    - GET /marketplace/listings — query marketplace listings
```

---

## Task Split Overview

| Agent | Domain | Tasks | Files |
|-------|--------|-------|-------|
| **Agent A** | Shared core (`aitbc/`) | 4 items | `aitbc/trading/offer_types.py` (new), `aitbc/trading/offer_client.py` (new), `aitbc/trading/offer_cache.py` (new), `tests/unit/` |
| **Agent B** | Apps & infrastructure | 6 items | `apps/trading/src/trading_service/`, `cli/aitbc_cli/commands/trade.py` (extend), `apps/trading/tests/` |

**Conflict boundary**: Agent A owns `aitbc/trading/offer_*.py` (new files). Agent B owns `apps/trading/`, `cli/`. Agent B consumes Agent A's `OfferSyncClient`, offer types, and `OfferCache`. No shared files are touched by both agents.

**Sequencing**: Agent A goes first (shared SDK). Agent B starts after Agent A completes A1-A3 (B2-B4 depend on A1 types + A3 cache). B1 (config) can proceed in parallel with Agent A.

---

## Agent A — Shared Core

**Scope**: Create offer sync types, an OfferSyncClient for the trading service offer sync endpoints, and an OfferCache that wraps RedisCache for offer-specific caching with staleness tracking.

**Working directory**: `/opt/aitbc/aitbc/trading/`

**Prerequisite**: v0.8.0 Agent A ✅ (`939bb066f`). v0.8.0 Agent B should be complete (for InterChainTrade + IslandRegistryEntry models).

**Verification command**:
```bash
cd /opt/aitbc && ./venv/bin/python -m mypy --show-error-codes aitbc/trading/ && ./venv/bin/python -m ruff check aitbc/trading/ tests/unit/test_offer_sync_sdk.py && ./venv/bin/python -m pytest tests/unit/test_offer_sync_sdk.py -q -o addopts=""
```

### Tasks

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| A1 | Create `aitbc/trading/offer_types.py` — OfferSyncStatus, SyncedOffer, OfferSyncConfig, OfferDiscoveryRequest, OfferDiscoveryResult | 🔴 P0 | `aitbc/trading/offer_types.py` (new), `aitbc/trading/__init__.py` (extend) | ✅ |
| A2 | Create `aitbc/trading/offer_client.py` — OfferSyncClient async HTTP client | 🔴 P0 | `aitbc/trading/offer_client.py` (new), `aitbc/trading/__init__.py` (extend) | ✅ |
| A3 | Create `aitbc/trading/offer_cache.py` — OfferCache wrapping RedisCache | 🔴 P0 | `aitbc/trading/offer_cache.py` (new), `aitbc/trading/__init__.py` (extend) | ✅ |
| A4 | Unit tests for A1-A3 | High | `tests/unit/test_offer_sync_sdk.py` (new) | ✅ |

### Agent A — Detailed Instructions

#### A1: Offer Sync Types

Create `aitbc/trading/offer_types.py`:

```python
class OfferSyncStatus(StrEnum):
    """Status of an offer in the sync cache."""
    FRESH = "fresh"       # recently synced, within staleness threshold
    STALE = "stale"       # exceeded staleness threshold, needs refresh
    SYNCING = "syncing"   # currently being synced
    ERROR = "error"       # sync failed


@dataclass
class OfferSyncConfig:
    """Configuration for offer synchronization per chain."""
    sync_enabled: bool = True
    sync_interval_seconds: int = 60  # polling interval
    staleness_threshold_seconds: int = 300  # 5 min for fast chains
    max_bandwidth_kbps: int = 100
    cache_ttl_seconds: int = 300
    # Per-chain overrides: {chain_id: threshold_seconds}
    per_chain_staleness: dict[str, int] = field(default_factory=dict)


@dataclass
class SyncedOffer:
    """A cached offer with sync metadata."""
    offer_id: str
    chain_id: str
    provider: str
    service_type: str  # "gpu_marketplace", "compute", etc.
    price: float
    quantity: int
    status: str  # OfferFSM status (available, reserved, in_use, delisted, expired)
    attributes: dict[str, Any] = field(default_factory=dict)
    last_synced: str = ""  # ISO timestamp
    sync_status: str = "fresh"  # OfferSyncStatus value
    sync_confidence: float = 1.0  # 1.0 = fresh, 0.5 = stale, 0.0 = error


@dataclass
class OfferDiscoveryRequest:
    """Request to discover offers across chains."""
    source_chain: str | None = None
    dest_chain: str | None = None
    service_type: str | None = None
    min_price: float | None = None
    max_price: float | None = None
    region: str | None = None
    gpu_model: str | None = None
    limit: int = 100
    offset: int = 0


@dataclass
class OfferDiscoveryResult:
    """Result of offer discovery across chains."""
    offers: list[SyncedOffer] = field(default_factory=list)
    total_count: int = 0
    chains_searched: list[str] = field(default_factory=list)
    stale_count: int = 0
    sync_triggered: bool = False
```

#### A2: Offer Sync Client

Create `aitbc/trading/offer_client.py` — async HTTP client for the trading service offer sync endpoints:

```python
class OfferSyncClient:
    """HTTP client for offer sync endpoints."""
    # Wraps: POST /v1/trading/offers/discover, POST /v1/trading/offers/sync,
    # GET /v1/trading/offers/sync-status, GET /v1/trading/offers/cache
```

Methods: `discover_offers`, `sync_offers`, `get_sync_status`, `get_cached_offers`.

#### A3: Offer Cache

Create `aitbc/trading/offer_cache.py` — wraps `RedisCache` from `aitbc.caching`:

```python
class OfferCache:
    """Cache for cross-chain offers with staleness tracking."""
    # Uses RedisCache under the hood (with in-memory fallback)
    # get_offer(offer_id) -> SyncedOffer | None
    # set_offer(offer_id, offer, ttl) -> None
    # delete_offer(offer_id) -> None
    # list_offers_by_chain(chain_id) -> list[SyncedOffer]
    # list_offers_by_type(service_type) -> list[SyncedOffer]
    # is_stale(offer_id) -> bool
    # get_stale_offers(chain_id) -> list[str]
    # get_sync_metadata(chain_id) -> dict (last_sync, offer_count, stale_count)
    # clear_chain(chain_id) -> None
```

#### A4: Unit Tests

`tests/unit/test_offer_sync_sdk.py` — tests for all types, client (mocked httpx), and cache (mocked RedisCache).

---

## Agent B — Apps & Infrastructure

**Scope**: Add offer sync config, OfferSyncService (polling loop), discovery endpoint, sync endpoints, CLI commands, integration tests.

**Working directory**: `/opt/aitbc/apps/trading/`, `/opt/aitbc/cli/`

**Prerequisite**: Agent A A1-A3 complete. v0.8.0 Agent B complete (InterChainTrade + IslandRegistryEntry + CLI trade.py).

**Verification command**:
```bash
cd /opt/aitbc && ./venv/bin/python -m ruff check apps/trading/src/ cli/aitbc_cli/commands/trade.py
cd /opt/aitbc && PYTHONPATH=apps/trading/src:aitbc ./venv/bin/python -m pytest apps/trading/tests/test_v081_offer_sync.py -q -o addopts="" --timeout=30
```

### Tasks

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| B1 | Add offer sync config to trading service Settings | 🔴 P0 | `apps/trading/src/trading_service/config.py` (extend) | ✅ |
| B2 | Create OfferSyncService — polling loop per chain, incremental sync, conflict resolution, staleness detection | 🔴 P0 | `apps/trading/src/trading_service/services/offer_sync_service.py` (new) | ✅ |
| B3 | Add offer discovery endpoint — POST /v1/trading/offers/discover | 🔴 P0 | `apps/trading/src/trading_service/main.py` (extend) | ✅ |
| B4 | Add offer sync endpoints — POST /v1/trading/offers/sync, GET /v1/trading/offers/sync-status | 🔴 P0 | `apps/trading/src/trading_service/main.py` (extend) | ✅ |
| B5 | Add CLI trade discover, sync, sync-status commands | 🔴 P0 | `cli/aitbc_cli/commands/trade.py` (extend) | ✅ |
| B6 | Integration tests | High | `apps/trading/tests/test_v081_offer_sync.py` (new) | ✅ |

### Agent B — Detailed Instructions

#### B1: Offer Sync Config

Extend `apps/trading/src/trading_service/config.py` (from v0.8.0 B1):
```python
# Offer sync settings
offer_sync_enabled: bool = True
offer_sync_interval_seconds: int = 60
offer_staleness_threshold_seconds: int = 300  # 5 min default
offer_cache_ttl_seconds: int = 300
offer_sync_max_bandwidth_kbps: int = 100
# Per-chain staleness overrides (JSON env var)
offer_per_chain_staleness: dict[str, int] = {}
```

#### B2: OfferSyncService

Create `apps/trading/src/trading_service/services/offer_sync_service.py`:
- `OfferSyncService` — background polling loop per registered chain
- Uses `BlockchainRPCClient` from `aitbc.marketplace` to query offers per chain
- Uses `OfferCache` from `aitbc.trading.offer_cache` (A3) for caching
- Incremental sync: track `last_sync` timestamp per chain, only fetch changed offers
- Conflict resolution: source-chain-wins (offer from source chain is authoritative)
- Staleness detection: check `last_synced` against per-chain threshold
- Sync status tracking: per-chain last_sync, offer_count, stale_count, error_count

#### B3: Offer Discovery Endpoint

Add to `main.py`:
- `POST /v1/trading/offers/discover` — query OfferCache with filters (service_type, price range, region, gpu_model)
- If cached offers are stale, trigger on-demand sync before returning
- Return `OfferDiscoveryResult` (from A1) with ranked, deduplicated offers

#### B4: Offer Sync Endpoints

Add to `main.py`:
- `POST /v1/trading/offers/sync` — trigger sync for specific chain or all chains
- `GET /v1/trading/offers/sync-status` — get sync status per chain (last_sync, offer_count, stale_count)

#### B5: CLI Commands

Extend `cli/aitbc_cli/commands/trade.py` (from v0.8.0 B7):
- `aitbc trade discover --source-chain <chain> --dest-chain <chain> --service-type <type>` — discover offers
- `aitbc trade sync --all-chains / --chain-id <chain> / --service-type <type>` — trigger sync
- `aitbc trade sync-status` — show sync status

Use `OfferSyncClient` from A2 for all RPC calls.

#### B6: Integration Tests

`apps/trading/tests/test_v081_offer_sync.py` — tests for:
- OfferSyncService polling loop (mocked BlockchainRPCClient)
- Offer discovery with filters
- Staleness detection and refresh
- Conflict resolution (same offer on multiple chains)
- Sync status tracking
- CLI commands (smoke tests)

---

## Coordination

### Shared Files

No shared files are touched by both agents. Agent A owns `aitbc/trading/offer_*.py` (new files). Agent B owns `apps/trading/`, `cli/`. Agent B consumes Agent A's `OfferSyncClient`, offer types, and `OfferCache`.

### Sequencing

1. **Phase 1** (parallel): Agent A starts A1-A3 (offer sync SDK), Agent B starts B1 (config)
2. **Phase 2** (Agent A first): Agent A completes A4 (tests), Agent B starts B2-B4 (sync service, endpoints — depends on A1 types + A3 cache)
3. **Phase 3** (Agent B): B5 (CLI — needs A2 client), B6 (tests)

### Dependencies

```
v0.8.0 (trading service + SDK) ✅ Agent A, ⬜ Agent B
    │
    ├── A1 (offer types) ──┐
    ├── A2 (offer client) ─┤
    ├── A3 (offer cache) ──┤
    │                        ├── A4 (tests)
    │                        │
    ├── B1 (config) ────────┐│
    │                        │├── B2 (sync service — needs A1 + A3)
    │                        │├── B3 (discovery endpoint — needs A1 + A3)
    │                        │├── B4 (sync endpoints — needs A1)
    │                        │├── B5 (CLI — needs A2)
    │                        │└── B6 (tests)
```

### Deferred to Future Releases

- **Subscription-based sync (v0.8.2+)**: WebSocket-based real-time offer notifications, push notifications, subscription heartbeat/reconnection
- **External search index (future)**: Elasticsearch/Meilisearch cluster across islands for advanced search
- **Bandwidth management**: Compressed sync payloads, bandwidth limiting per chain (basic version in v0.8.1, advanced in future)
- **Offer availability verification**: Real-time check before trade creation (basic version in v0.8.1, advanced in v0.9.0)
- **Gossip-based offer propagation**: Using existing BroadcastGossipBackend for offer change events (future)
