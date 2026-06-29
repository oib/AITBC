# v0.8.2 — Agent Task Assignment

**Release Theme**: Advanced Offer Sync — Subscription-Based Sync, Real-Time Notifications, Gossip Propagation, Optional Search Index

**Goal**: Upgrade cross-chain offer synchronization from polling-based (v0.8.1) to subscription-based with real-time notifications. Offers are pushed to subscribers via WebSocket and gossip pub/sub, eliminating polling latency. Optional external search index for advanced queries.

> **Not on the critical path**: v0.9.0 (Atomic Cross-Chain Settlement) does NOT depend on v0.8.2. v0.9.0 only needs v0.8.1's polling-based sync. v0.8.2 is an enhancement release that can ship after v0.9.0 or in parallel.

> **Prerequisites**: [v0.8.1](../v0.8.1/change.log) (Agent A ✅ `b3f3ef57d`, Agent B ⬜ pending), [v0.8.0](../v0.8.0/change.log), [v0.7.0](../v0.7.0/change.log) ✅, [v0.7.1](../v0.7.1/change.log) ✅, [v0.7.2](../v0.7.2/change.log) ✅.

> **Risk**: Low-Medium. This is an enhancement layer on v0.8.1. No consensus-critical path is touched. The main risk is WebSocket connection management (reconnection, backpressure) and gossip event ordering. Polling-based sync (v0.8.1) remains as fallback.

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
| A1 | Create `aitbc/trading/subscription_types.py` — OfferEventType, OfferEvent, OfferSubscription, SubscriptionStatus, OfferNotification | 🔴 P0 | `aitbc/trading/subscription_types.py` (new), `aitbc/trading/__init__.py` (extend) | ⬜ |
| A2 | Create `aitbc/trading/subscription_client.py` — OfferSubscriptionClient WebSocket client | 🔴 P0 | `aitbc/trading/subscription_client.py` (new), `aitbc/trading/__init__.py` (extend) | ⬜ |
| A3 | Extend `aitbc/trading/offer_types.py` — add OfferEventType enum | Medium | `aitbc/trading/offer_types.py` (extend) | ⬜ |
| A4 | Unit tests for A1-A3 | High | `tests/unit/test_offer_subscription_sdk.py` (new) | ⬜ |

### Agent A — Detailed Instructions

#### A1: Subscription Types

Create `aitbc/trading/subscription_types.py`:

```python
class OfferEventType(StrEnum):
    """Type of offer change event."""
    CREATED = "created"
    UPDATED = "updated"
    DELETED = "deleted"


@dataclass
class OfferEvent:
    """An offer change event from a chain."""
    event_type: str  # OfferEventType value
    offer_id: str
    chain_id: str
    offer: SyncedOffer | None = None  # None for deleted events
    timestamp: str = ""  # ISO timestamp


@dataclass
class OfferSubscription:
    """Configuration for an offer subscription."""
    chain_id: str | None = None  # None = all chains
    service_type: str | None = None
    min_price: float | None = None
    max_price: float | None = None
    region: str | None = None
    gpu_model: str | None = None
    debounce_ms: int = 1000  # batch notifications within this window


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
| B1 | Add subscription config to trading service Settings | 🔴 P0 | `apps/trading/src/trading_service/config.py` (extend) | ⬜ |
| B2 | Create WebSocket offer subscription endpoint — `/v1/trading/offers/subscribe` | 🔴 P0 | `apps/trading/src/trading_service/main.py` (extend) | ⬜ |
| B3 | Integrate gossip broker — subscribe to `offers.{chain_id}`, update OfferCache on events | 🔴 P0 | `apps/trading/src/trading_service/services/offer_subscription_service.py` (new) | ⬜ |
| B4 | Create notification service — saved query matching, debounced batches | Medium | `apps/trading/src/trading_service/services/offer_notification_service.py` (new) | ⬜ |
| B5 | Add subscription status endpoint — `GET /v1/trading/offers/subscription-status` | Medium | `apps/trading/src/trading_service/main.py` (extend) | ⬜ |
| B6 | Add CLI trade watch, subscription-status commands | Medium | `cli/aitbc_cli/commands/trade.py` (extend) | ⬜ |
| B7 | Optional: Search index integration (Meilisearch preferred) | Low | `apps/trading/src/trading_service/services/offer_search_service.py` (new) | ⬜ |
| B8 | Integration tests | High | `apps/trading/tests/test_v082_offer_subscription.py` (new) | ⬜ |
| B9 | Optional: Publish offer changes to gossip in blockchain-node | Low | `apps/blockchain-node/src/aitbc_chain/rpc/marketplace.py` (extend) | ⬜ |

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
