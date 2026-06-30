# v0.8.2 Advanced Offer Sync — Agent A Tasks

**Last Updated**: 2026-06-30
**Version**: 1.0

**Agent**: Agent A (Shared Core)

**Scope**: Extend the v0.8.1 trading SDK with offer event types, offer subscription client, and optional search index integration.

**Working directory**: `/opt/aitbc/aitbc/trading/`

**Prerequisite**: v0.8.1 Agent A ✅.

**Verification command**:
```bash
cd /opt/aitbc && ./venv/bin/python -m mypy --show-error-codes aitbc/trading/ && ./venv/bin/python -m ruff check aitbc/trading/ tests/unit/test_offer_subscription.py && ./venv/bin/python -m pytest tests/unit/test_offer_subscription.py -q -o addopts=""
```

---

## Tasks

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| A1 | Offer event types — OfferEvent, OfferEventType, OfferSubscription, OfferSubscriptionFilter | 🔴 P0 | `aitbc/trading/offer_types.py` (extend) | ✅ |
| A2 | Offer subscription client — OfferSubscriptionClient with WebSocket subscription methods | 🔴 P0 | `aitbc/trading/offer_subscription_client.py` (new) | ✅ |
| A3 | Search index integration — MeilisearchClient for advanced queries (optional) | Low | `aitbc/trading/search_index.py` (new, optional) | ✅ |
| A4 | Unit tests for A1-A2 | High | `tests/unit/test_offer_subscription.py` (new) | ✅ |

---

## A1: Offer Event Types

Extend `aitbc/trading/offer_types.py`:
- `OfferEventType` enum — created, updated, deleted
- `OfferEvent` dataclass — event_type, offer_id, chain_id, offer (SyncedOffer), timestamp, source
- `OfferSubscription` dataclass — subscription_id, node_id, chain_id, filters, status
- `OfferSubscriptionFilter` dataclass — service_type, min_price, max_price, region, gpu_model

---

## A2: Offer Subscription Client

Create `aitbc/trading/offer_subscription_client.py`:
- `OfferSubscriptionClient` — WebSocket client for offer subscription endpoints
- `subscribe(filters)` — subscribe to offer events with filters
- `unsubscribe()` — unsubscribe from offer events
- `heartbeat()` — send heartbeat to extend lease
- `get_subscription_status()` — get subscription status
- Follows pattern from `apps/blockchain-node/src/aitbc_chain/subscription_client.py`

---

## A3: Search Index Integration (Optional)

Create `aitbc/trading/search_index.py`:
- `MeilisearchClient` — client for Meilisearch search index
- `index_offer(offer)` — index an offer
- `search_offers(query, filters)` — search offers with filters
- `delete_offer(offer_id)` — delete offer from index
- Optional: can be deferred to future release

---

## A4: Unit Tests

`tests/unit/test_offer_subscription.py` — tests for:
- Offer event types serialization
- Offer subscription client WebSocket methods (mocked websockets)
- Subscription status tracking
- Filter application

---

## Related Topics

- [Overview](./overview.md) - Release overview and status baseline
- [Agent B Tasks](./agent-b.md) - Apps & infrastructure implementation details

---

**Documentation Version**: 1.0
**Last Updated**: 2026-06-30
**Release**: v0.8.2 — Advanced Offer Sync
**Agent**: Agent A (Shared Core)
