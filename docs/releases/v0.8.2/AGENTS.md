# v0.8.2 — Agent Task Assignment

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
- [Status Baseline](./overview.md#status-baseline--verified-code-targets-2026-06-29)
- [Task Split Overview](./overview.md#task-split-overview)

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

## Design Decisions (Resolved 2026-06-29)

All 5 design decisions are grounded in codebase investigation (4 parallel subagent reports). Each decision cites the existing pattern it follows.

### Decision 1: Offer Event Schema

**Decision**: Use `event_type` (not `event`) as the field name, include `source` field, embed `SyncedOffer` object (not raw dict).

```python
@dataclass
class OfferEvent:
    event_type: str          # OfferEventType value: "created" | "updated" | "deleted"
    offer_id: str
    chain_id: str
    offer: SyncedOffer | None = None  # None for deleted events
    timestamp: str = ""      # ISO 8601 (datetime.now(UTC).isoformat())
    source: str | None = None  # "blockchain-node" | "trading-service" | None
```

**Rationale (grounded in evidence)**:
- Field name `event_type` matches the **agent-coordinator event pattern** (`apps/agent-coordinator/src/app/routing/agent_discovery.py:370-375`): `{"event_type": str, "timestamp": ISO, "payload": dict}`. Using `event` would diverge from the only existing Redis pub/sub event pattern in the codebase.
- `source` field matches the generic `aitbc.events.Event` dataclass (`aitbc/events/events.py:30-42`): `event_type, data, timestamp, priority, source`. This enables event routing and debugging.
- Embedding `SyncedOffer` object (with `to_dict()`/`from_dict()`) rather than a raw dict payload matches how `SyncedOffer` is already serialized in `offer_cache.py:65-74` and `offer_types.py:64-116`. It provides type safety and consistent serialization.
- `timestamp` as ISO string (not datetime object) matches all existing patterns: agent-coordinator, gossip block messages (`consensus/poa.py:502`: `block.timestamp.isoformat()`), and `SyncedOffer.last_synced`.

**Gossip message format** (when publishing to `offers.{chain_id}` topic):
```json
{
  "event_type": "created",
  "offer_id": "gpu_abc123",
  "chain_id": "ait-hub",
  "offer": { /* SyncedOffer.to_dict() output */ },
  "timestamp": "2026-06-29T12:00:00+00:00",
  "source": "blockchain-node"
}
```

**Event type semantics**:
| Event | Trigger | `offer` field |
|-------|---------|---------------|
| `created` | New GPU_MARKETPLACE tx confirmed | Full `SyncedOffer` |
| `updated` | Offer status change (e.g., available→reserved) | Full `SyncedOffer` with new status |
| `deleted` | Offer delisted/expired | `None` (only `offer_id` + `chain_id` needed) |

---

### Decision 2: Gossip Topic Partitioning

**Decision**: Use `offers.{chain_id}` (per-chain partitioning), NOT a single global `offers` topic.

**Rationale (grounded in evidence)**:
- **ALL existing gossip topics use per-chain partitioning** — this is the only pattern in the codebase:
  - `blocks.{chain_id}` (`consensus/poa.py:488`, `main.py:223`)
  - `transactions.{chain_id}` (`main.py:182`)
  - `chain.{chain_id}.sync` (`network/multi_chain_manager.py:310`)
- Redis channel name = gossip topic string (1:1 mapping, `gossip/broker.py:174,184,209`). Per-chain topics → separate Redis channels → isolated delivery, per-chain metrics (`gossip_publications_topic_{topic}`), cleaner debugging.
- Subscribers only receive events for chains they care about. A single global `offers` topic would force every subscriber to filter by `chain_id` in the message handler — wasteful at scale.
- `chain_id` is ALSO included in the message payload (defense-in-depth, matching how block messages redundantly include `chain_id` at `consensus/poa.py:499`).

**Priority routing**: The existing `_priority_for_topic()` in `gossip/broker.py:318-328` defaults non-block/transaction topics to `PRIORITY_STATUS` (4). Offers are lower priority than blocks/transactions — **no change needed to `_priority_for_topic()`**. Offers default to priority 4, which is correct.

**Subscription pattern** (trading service):
```python
# Subscribe to offer events for each registered chain
for chain_id in registered_chains:
    sub = await gossip_broker.subscribe(f"offers.{chain_id}")
    # Process events from sub.queue
```

---

### Decision 3: Subscription Auth

**Decision**: Reuse the exact lease-based pattern from `/rpc/subscribe/ws`. No JWT, no X-Wallet-Address. Auth via `node_id` + Redis lease.

**Rationale (grounded in evidence)**:
- The existing WebSocket subscription endpoint (`apps/blockchain-node/src/aitbc_chain/rpc/websocket.py:42-136`) uses **lease-based auth with `node_id`** — no JWT, no wallet address. This is the only WebSocket auth pattern in the codebase.
- The lease is obtained via prior HTTP POST to `/rpc/subscribe` (`rpc/subscription.py:14-56`), stored in Redis via `lease_tracker.py:80-116`, and validated on WebSocket connect (`websocket.py:54-83`).
- Config values are proven: `lease_duration=3600` (1hr), `lease_renewal_threshold=300` (5min), `heartbeat_interval=60` (1min) — `config.py:184-188`.

**New endpoints (mirroring existing pattern)**:
| Endpoint | Mirrors | Purpose |
|----------|---------|---------|
| `POST /v1/trading/offers/subscribe` | `POST /rpc/subscribe` | Register, get lease |
| `POST /v1/trading/offers/heartbeat` | `POST /rpc/heartbeat` | Extend lease |
| `WS /v1/trading/offers/subscribe/ws` | `WS /rpc/subscribe/ws` | Stream offer events |

**WebSocket first message** (client → server, extends existing pattern with optional filters):
```json
{
  "node_id": "trading-node-1",
  "chain_id": "ait-hub",
  "transport": "websocket",
  "filters": {
    "service_type": "gpu_marketplace",
    "min_price": 0.5,
    "max_price": 10.0,
    "region": "us-east",
    "gpu_model": "A100"
  }
}
```

**Lease storage**: The trading service is a separate process from blockchain-node. It needs its own lease tracker pointing at the same Redis, with a **different key prefix** to avoid collisions:
- Block subscription leases: `lease:subscriber:{node_id}` (existing, `lease_tracker.py`)
- Offer subscription leases: `lease:offer_subscriber:{node_id}` (new)

**Heartbeat**: Same dual-heartbeat pattern as existing:
1. Application-level JSON ping every 20s: `{"type": "ping", "timestamp": ...}` (server → client)
2. HTTP heartbeat for lease renewal every 60s, renews when <300s remaining (client → server)
3. WebSocket protocol-level ping handled by `websockets` library (`ping_interval=20, ping_timeout=30`)

**Reconnection**: Same backoff as `subscription_client.py:262-276`:
- WebSocket disconnect → retry after 5s
- Other errors → fallback to polling (v0.8.1 OfferSyncClient), retry after 30s

---

### Decision 4: Staleness During Subscription Drop

**Decision**: Multi-layer staleness policy. When a subscription drops, mark offers stale (don't delete them), then fall back to polling.

**Rationale (grounded in evidence)**:
- OfferCache already has per-offer staleness via `last_synced` + `staleness_threshold_seconds` (default 300s, `offer_cache.py:112-123`, `offer_types.py:38-60`). This is the foundation.
- BlockchainCache uses **TTL + event invalidation** (belt-and-suspenders, `blockchain_cache.py:24-29`). OfferCache should follow the same layered approach.
- SubscriptionClient already has push→pull fallback (`subscription_client.py:262-276`, `368-382`). Offer subscription should do the same: subscription → polling fallback.
- **Gap identified**: No per-chain "silent chain" detection exists. This is new work.

**Staleness layers**:
| Layer | Mechanism | Existing? | Trigger |
|-------|-----------|-----------|---------|
| 1. Per-offer TTL | `cache_ttl_seconds=300` — entries auto-expire | ✅ Existing | Time-based |
| 2. Per-offer staleness | `is_stale()` checks `last_synced` vs threshold | ✅ Existing | Time-based |
| 3. Per-chain silent detection | `mark_chain_silent()` — mark all chain offers stale | ❌ NEW | Subscription drop + N failed reconnects |
| 4. Polling fallback | Switch to v0.8.1 OfferSyncClient polling | ✅ Existing (pattern) | Subscription failure |

**New OfferCache methods**:
```python
def mark_chain_silent(self, chain_id: str) -> int:
    """Mark all offers for a chain as stale when subscription drops.

    Sets sync_status=STALE, sync_confidence=0.5 for all offers.
    Records 'silent_since' in chain sync metadata.
    Does NOT delete offers — consumers need to know data is uncertain.
    Returns: number of offers marked stale.
    """

def is_chain_silent(self, chain_id: str) -> bool:
    """Check if a chain is marked as silent (subscription dropped)."""

def clear_chain_silent(self, chain_id: str) -> None:
    """Clear silent status when subscription reconnects."""
```

**Trigger conditions for `mark_chain_silent()`**:
1. WebSocket disconnects
2. Reconnection fails after `subscription_max_reconnect_attempts` (default: 3)
3. No events received for `subscription_silent_threshold_multiplier × staleness_threshold` (default: 2 × 300s = 600s = 10min)

**Recovery**: When subscription reconnects, call `clear_chain_silent(chain_id)`. The next batch of events will refresh offers via `handle_event()`.

**Config additions**:
```python
subscription_max_reconnect_attempts: int = 3
subscription_silent_threshold_multiplier: int = 2  # silent after 2x staleness threshold
```

**Key principle**: Never delete cached offers on subscription drop. Mark them stale so consumers can decide whether to use uncertain data. Polling sync will refresh them.

---

### Decision 5: Search Index Opt-In Config

**Decision**: Search index is OFF by default (opt-in). Meilisearch preferred over Elasticsearch. In-memory search as fallback.

**Rationale (grounded in evidence)**:
- No search index infrastructure exists anywhere in the codebase. This is entirely new.
- Meilisearch is preferred over Elasticsearch because:
  - Lighter weight (single binary, ~50MB vs Elasticsearch's JVM + ~500MB)
  - Simpler API (REST, no query DSL)
  - Good Python client (`meilisearch-python-sdk`)
  - Built-in faceted search and full-text search
  - Sub-millisecond search on small datasets
- The in-memory fallback (filter/sort on cached offers in OfferCache) ensures the feature works without external dependencies.

**Config defaults**:
```python
# apps/trading/src/trading_service/config.py
offer_search_index_enabled: bool = False  # OFF by default — opt-in
offer_search_index_backend: str = "meilisearch"  # only supported backend in v0.8.2
offer_search_index_url: str = "http://localhost:7700"  # Meilisearch default
offer_search_index_api_key: str = ""  # empty = no auth (dev mode)
```

**Behavior**:
| Config | Behavior |
|--------|----------|
| `offer_search_index_enabled=False` | Use in-memory search (filter/sort OfferCache entries) |
| `offer_search_index_enabled=True` + index reachable | Use Meilisearch for search queries |
| `offer_search_index_enabled=True` + index unreachable | Fall back to in-memory search, log warning |

**Indexing strategy**: Index on offer events (same `OfferEvent` stream that drives cache invalidation):
- `created` → add document to index
- `updated` → update document in index
- `deleted` → remove document from index

**Search scope**:
- Full-text: `service_type`, `provider`, `attributes.gpu_model`, `attributes.region`
- Faceted filters: `chain_id`, `service_type`, `region`, `gpu_model`, `price_range`
- Sort: `price`, `created_at`

**Why not Elasticsearch**: Elasticsearch requires JVM, significant memory, and complex configuration. For a blockchain-adjacent project that values lightweight deployment (single-binary nodes, SQLite/Redis defaults), Meilisearch aligns better. Elasticsearch can be added later if needed.

---

### Architecture: Advanced Offer Sync (v0.8.2)

```
┌──────────────────────────────────────────────────────────────────────┐
│ Shared Core (aitbc/trading/ — EXTEND v0.8.1 SDK)                    │
│                                                                      │
│  Subscription types (A1 — NEW subscription_types.py):                │
│    OfferEvent — created/updated/deleted event with offer data        │
│    OfferSubscription — subscription config (filters, debounce)       │
│    SubscriptionStatus — subscribed/reconnecting/polling_fallback     │
│    OfferNotification — debounced batch notification                  │
│                                                                      │
│  Subscription client (A2 — NEW subscription_client.py):              │
│    OfferSubscriptionClient — WebSocket client for offer streaming    │
│    subscribe(chain_id, filters), unsubscribe, reconnect, fallback    │
│                                                                      │
│  Offer event types (A3 — EXTEND offer_types.py):                     │
│    OfferEventType enum — CREATED, UPDATED, DELETED                   │
│    Add to existing offer_types.py (no new file)                      │
└──────────────────────────────────────────────────────────────────────┘
         ↑ consumed by                    ↑ consumed by
┌─────────────────────────┐    ┌──────────────────────────────────────┐
│ CLI (cli/aitbc_cli/)    │    │ Trading Service                      │
│                         │    │ (apps/trading/)                      │
│  trade watch            │    │                                      │
│  trade subscription-    │    │  Subscription config (B1):           │
│    status               │    │    Settings extensions (subscription  │
│                         │    │    enabled, debounce, fallback)       │
│  Uses OfferSubscription │    │                                      │
│  Client (A2)            │    │  WebSocket endpoint (B2):             │
│                         │    │    /v1/trading/offers/subscribe       │
│                         │    │    Stream offer events from gossip    │
│                         │    │    Lease-based auth (like /rpc/       │
│                         │    │    subscribe/ws)                      │
│                         │    │                                      │
│                         │    │  Gossip integration (B3):             │
│                         │    │    Subscribe to offers.{chain_id}     │
│                         │    │    Publish offer changes to gossip    │
│                         │    │    Update OfferCache on events        │
│                         │    │                                      │
│                         │    │  Notification service (B4):           │
│                         │    │    Saved query matching               │
│                         │    │    Debounced batch notifications      │
│                         │    │    WebSocket push to subscribers      │
│                         │    │                                      │
│                         │    │  Subscription status endpoint (B5):   │
│                         │    │    GET /v1/trading/offers/            │
│                         │    │    subscription-status                │
│                         │    │                                      │
│                         │    │  CLI commands (B6):                   │
│                         │    │    trade watch, subscription-status   │
│                         │    │                                      │
│                         │    │  Optional: Search index (B7):         │
│                         │    │    Meilisearch/Elasticsearch client   │
│                         │    │    Index on offer events              │
│                         │    │    Fallback to in-memory search       │
│                         │    │                                      │
│                         │    │  Tests (B8):                         │
└─────────────────────────┘    └──────────────────────────────────────┘

  Blockchain Node (apps/blockchain-node/) — Agent B (optional):
    B9: Publish offer changes to gossip topic offers.{chain_id}
        (on GPU_MARKETPLACE tx confirmation, publish offer event)
```

---

## Task Split Overview

| Agent | Domain | Tasks | Files |
|-------|--------|-------|-------|
| **Agent A** | Shared core (`aitbc/`) | 4 items | `aitbc/trading/subscription_types.py` (new), `aitbc/trading/subscription_client.py` (new), `aitbc/trading/offer_types.py` (extend), `tests/unit/` |
| **Agent B** | Apps & infrastructure | 8 items | `apps/trading/src/trading_service/`, `cli/aitbc_cli/commands/trade.py` (extend), `apps/blockchain-node/` (optional gossip publishing), `apps/trading/tests/` |

**Conflict boundary**: Agent A owns `aitbc/trading/subscription_*.py` (new files) and `offer_types.py` (extend). Agent B owns `apps/trading/`, `cli/`, `apps/blockchain-node/`. Agent B consumes Agent A's `OfferSubscriptionClient`, subscription types, and offer event types.

**Sequencing**: Agent A goes first (shared SDK). Agent B starts after Agent A completes A1-A3 (B2-B4 depend on A1 types + A2 client). B1 (config) can proceed in parallel with Agent A.

---

**Documentation Version**: 1.0
**Last Updated**: 2026-06-30
**Release**: v0.8.2 — Advanced Offer Sync

---

## Agent A — Shared Core

**Scope**: Create subscription types, an OfferSubscriptionClient for WebSocket-based offer streaming, and extend offer types with event types. These are dependency-free shared types consumed by the trading service and CLI.

**Working directory**: `/opt/aitbc/aitbc/trading/`

**Prerequisite**: v0.8.1 Agent A ✅ (`b3f3ef57d`). v0.8.1 Agent B should be complete (for trading service endpoints).

**Verification command**:
```bash
cd /opt/aitbc && ./venv/bin/python -m mypy --show-error-codes aitbc/trading/ && ./venv/bin/python -m ruff check aitbc/trading/ tests/unit/test_offer_subscription_sdk.py && ./venv/bin/python -m pytest tests/unit/test_offer_subscription_sdk.py -q -o addopts=""
```

### Tasks

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| A1 | Create `aitbc/trading/subscription_types.py` — OfferEventType, OfferEvent, OfferSubscription, SubscriptionStatus, OfferNotification | 🔴 P0 | `aitbc/trading/subscription_types.py` (new), `aitbc/trading/__init__.py` (extend) | ✅ |
| A2 | Create `aitbc/trading/subscription_client.py` — OfferSubscriptionClient WebSocket client | 🔴 P0 | `aitbc/trading/subscription_client.py` (new), `aitbc/trading/__init__.py` (extend) | ✅ |
| A3 | Extend `aitbc/trading/offer_types.py` — add OfferEventType enum | Medium | `aitbc/trading/offer_types.py` (extend) | ✅ |
| A4 | Unit tests for A1-A3 | High | `tests/unit/test_offer_subscription_sdk.py` (new) | ✅ |

### Agent A — Detailed Instructions

#### A1: Subscription Types

Create `aitbc/trading/subscription_types.py` — schema is finalized in [Design Decision 1](#decision-1-offer-event-schema):

```python
class OfferEventType(StrEnum):
    """Type of offer change event."""
    CREATED = "created"
    UPDATED = "updated"
    DELETED = "deleted"


@dataclass
class OfferEvent:
    """An offer change event from a chain.

    Schema aligned with agent-coordinator event pattern
    (agent_discovery.py:370-375) and aitbc.events.Event (events.py:30-42).
    See Design Decision 1 for rationale.
    """
    event_type: str  # OfferEventType value
    offer_id: str
    chain_id: str
    offer: SyncedOffer | None = None  # None for deleted events
    timestamp: str = ""  # ISO 8601 timestamp
    source: str | None = None  # "blockchain-node" | "trading-service" | None

    def to_dict(self) -> dict[str, Any]:
        """Serialize for gossip transport / WebSocket."""
        ...

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OfferEvent:
        """Deserialize from gossip transport."""
        ...


@dataclass
class OfferSubscription:
    """Configuration for an offer subscription (saved query)."""
    chain_id: str | None = None  # None = all chains
    service_type: str | None = None
    min_price: float | None = None
    max_price: float | None = None
    region: str | None = None
    gpu_model: str | None = None
    debounce_ms: int = 1000  # batch notifications within this window

    def matches(self, event: OfferEvent) -> bool:
        """Check if an event matches this subscription filter."""
        ...


class SubscriptionStatus(StrEnum):
    """Status of a WebSocket subscription."""
    SUBSCRIBED = "subscribed"
    RECONNECTING = "reconnecting"
    POLLING_FALLBACK = "polling_fallback"
    DISCONNECTED = "disconnected"


@dataclass
class OfferNotification:
    """A debounced batch notification of offer changes."""
    events: list[OfferEvent] = field(default_factory=list)
    chain_id: str = ""
    batch_size: int = 0
    timestamp: str = ""  # ISO timestamp
```

#### A2: OfferSubscriptionClient

Create `aitbc/trading/subscription_client.py` — WebSocket client for offer streaming:

```python
class OfferSubscriptionClient:
    """WebSocket client for real-time offer change streaming.

    Follows the same reconnection and lease pattern as
    SubscriptionClient (apps/blockchain-node/src/aitbc_chain/
    subscription_client.py).
    """
    # subscribe(chain_id, filters) -> AsyncIterator[OfferEvent]
    # unsubscribe(chain_id)
    # get_subscription_status() -> dict[chain_id, SubscriptionStatus]
    # close()
    # Auto-reconnect with 5s delay on disconnect
    # Fallback to polling (OfferSyncClient) when subscription fails
```

#### A3: Extend Offer Types

Add `OfferEventType` enum to `aitbc/trading/offer_types.py` (or re-export from `subscription_types.py`).

#### A4: Unit Tests

`tests/unit/test_offer_subscription_sdk.py` — tests for all subscription types, client (mocked WebSocket), and event handling.

---

## Agent B — Apps & Infrastructure

**Scope**: Add subscription config, WebSocket endpoint, gossip integration, notification service, subscription status endpoint, CLI commands, optional search index, and tests.

**Working directory**: `/opt/aitbc/apps/trading/`, `/opt/aitbc/cli/`, `/opt/aitbc/apps/blockchain-node/`

**Prerequisite**: Agent A A1-A3 complete. v0.8.1 Agent B complete.

**Verification command**:
```bash
cd /opt/aitbc && ./venv/bin/python -m ruff check apps/trading/src/ cli/aitbc_cli/commands/trade.py
cd /opt/aitbc && PYTHONPATH=apps/trading/src:aitbc ./venv/bin/python -m pytest apps/trading/tests/test_v082_offer_subscription.py -q -o addopts="" --timeout=30
```

### Tasks

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| B1 | Add subscription config to trading service Settings | 🔴 P0 | `apps/trading/src/trading_service/config.py` (extend) | ✅ |
| B2 | Create WebSocket offer subscription endpoint — `/v1/trading/offers/subscribe` | 🔴 P0 | `apps/trading/src/trading_service/main.py` (extend) | ✅ |
| B3 | Integrate gossip broker — subscribe to `offers.{chain_id}`, update OfferCache on events | 🔴 P0 | `apps/trading/src/trading_service/services/offer_subscription_service.py` (new) | ✅ |
| B4 | Create notification service — saved query matching, debounced batches | Medium | `apps/trading/src/trading_service/services/offer_notification_service.py` (new) | ✅ |
| B5 | Add subscription status endpoint — `GET /v1/trading/offers/subscription-status` | Medium | `apps/trading/src/trading_service/main.py` (extend) | ✅ |
| B6 | Add CLI trade watch, subscription-status commands | Medium | `cli/aitbc_cli/commands/trade.py` (extend) | ✅ |
| B7 | Optional: Search index integration (Meilisearch preferred) | Low | `apps/trading/src/trading_service/services/offer_search_service.py` (new) | ✅ |
| B8 | Integration tests | High | `apps/trading/tests/test_v082_offer_subscription.py` (new) | ✅ |
| B9 | Optional: Publish offer changes to gossip in blockchain-node | Low | `apps/blockchain-node/src/aitbc_chain/rpc/marketplace.py` (extend) | ✅ |

### Agent B — Detailed Instructions

#### B1: Subscription Config

Extend `apps/trading/src/trading_service/config.py`:
```python
# Subscription settings
offer_subscription_enabled: bool = True
offer_subscription_debounce_ms: int = 1000
offer_subscription_fallback_to_polling: bool = True
offer_subscription_reconnect_delay_seconds: int = 5
offer_subscription_heartbeat_seconds: int = 20
# Optional: search index
offer_search_index_enabled: bool = False
offer_search_index_backend: str = "meilisearch"  # or "elasticsearch"
offer_search_index_url: str = "http://localhost:7700"
```

#### B2: WebSocket Offer Subscription Endpoint

Add to `main.py`:
- `WS /v1/trading/offers/subscribe` — WebSocket endpoint for offer streaming
- Follow `/rpc/subscribe/ws` pattern (lease-based auth, heartbeat, subscriber tracking)
- Stream offer events from gossip topic `offers.{chain_id}`
- Support filter params: `chain_id`, `service_type`, `min_price`, `max_price`, `region`

#### B3: Gossip Integration

Create `apps/trading/src/trading_service/services/offer_subscription_service.py`:
- Subscribe to gossip topics `offers.{chain_id}` for each registered chain
- On offer event: update OfferCache (invalidate stale entry, set fresh entry)
- Publish events to WebSocket subscribers
- Track subscription health per chain

#### B4: Notification Service

Create `apps/trading/src/trading_service/services/offer_notification_service.py`:
- Maintain saved query subscriptions from WebSocket clients
- Match incoming offer events against saved queries
- Debounce batch notifications (collect for `debounce_ms` then send)
- Push notifications to WebSocket subscribers

#### B5: Subscription Status Endpoint

Add to `main.py`:
- `GET /v1/trading/offers/subscription-status` — per-chain subscription health
- Returns: chain_id, status (subscribed/reconnecting/polling_fallback), last_event, event_count

#### B6: CLI Commands

Extend `cli/aitbc_cli/commands/trade.py`:
- `aitbc trade watch --service-type <type> --max-price <price> --region <region>` — stream offer changes
- `aitbc trade subscription-status` — show subscription health per chain

Use `OfferSubscriptionClient` from A2.

#### B7: Optional Search Index

Create `apps/trading/src/trading_service/services/offer_search_service.py`:
- Meilisearch client (preferred) or Elasticsearch client
- Index offers on sync/event
- Query endpoint for advanced search
- Fallback to in-memory search (v0.8.1) when index unavailable

#### B8: Integration Tests

`apps/trading/tests/test_v082_offer_subscription.py` — tests for:
- WebSocket subscription (mocked gossip broker)
- Offer event → cache update → notification flow
- Reconnection and fallback to polling
- Debounced batch notifications
- Subscription status tracking
- CLI commands (smoke tests)

#### B9: Optional Blockchain-Node Gossip Publishing

Extend `apps/blockchain-node/src/aitbc_chain/rpc/marketplace.py`:
- On GPU_MARKETPLACE tx confirmation, publish offer event to gossip topic `offers.{chain_id}`
- Event types: created (new listing), updated (status change), deleted (listing removed)

---

## Coordination

### Shared Files

No shared files are touched by both agents. Agent A owns `aitbc/trading/subscription_*.py` (new) and `offer_types.py` (extend). Agent B owns `apps/trading/`, `cli/`, `apps/blockchain-node/`.

### Sequencing

1. **Phase 1** (parallel): Agent A starts A1-A3 (subscription SDK), Agent B starts B1 (config)
2. **Phase 2** (Agent A first): Agent A completes A4 (tests), Agent B starts B2-B4 (WebSocket, gossip, notifications — depends on A1 + A2)
3. **Phase 3** (Agent B): B5-B6 (status endpoint, CLI), B7-B9 (optional: search index, blockchain-node gossip), B8 (tests)

### Dependencies

```
v0.8.1 (polling-based offer sync) ✅ Agent A, ⬜ Agent B
    │
    ├── A1 (subscription types) ──┐
    ├── A2 (subscription client) ─┤
    ├── A3 (extend offer types) ──┤
    │                              ├── A4 (tests)
    │                              │
    ├── B1 (config) ──────────────┐│
    │                              │├── B2 (WebSocket endpoint — needs A1 + A2)
    │                              │├── B3 (gossip integration — needs A1)
    │                              │├── B4 (notification service — needs A1)
    │                              │├── B5 (subscription status — needs A1)
    │                              │├── B6 (CLI — needs A2)
    │                              │├── B7 (search index — optional)
    │                              │├── B8 (tests)
    │                              │└── B9 (blockchain-node gossip — optional)
```

### Deferred to Future Releases

- **Advanced search features**: Relevance scoring, personalization, ML-based ranking
- **Cross-island gossip mesh**: Direct island-to-island offer propagation (beyond Redis pub/sub)
- **Offer event sourcing**: Full event log for audit and replay
- **Subscription persistence**: Survive trading service restarts with persistent subscriptions
