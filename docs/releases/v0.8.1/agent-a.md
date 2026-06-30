# v0.8.1 Cross-Chain Offer Synchronization — Agent A Tasks

**Last Updated**: 2026-06-30
**Version**: 1.0

**Agent**: Agent A (Shared Core)

**Scope**: Extend the v0.8.0 trading SDK with offer sync types, offer sync client, and offer cache.

**Working directory**: `/opt/aitbc/aitbc/trading/`

**Prerequisite**: v0.8.0 Agent A ✅.

**Verification command**:
```bash
cd /opt/aitbc && ./venv/bin/python -m mypy --show-error-codes aitbc/trading/ && ./venv/bin/python -m ruff check aitbc/trading/ tests/unit/test_offer_sync.py && ./venv/bin/python -m pytest tests/unit/test_offer_sync.py -q -o addopts=""
```

---

## Tasks

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| A1 | Offer sync types — OfferSyncStatus, SyncedOffer, OfferSyncConfig, OfferDiscoveryRequest, OfferDiscoveryResult | 🔴 P0 | `aitbc/trading/offer_types.py` (new) | ✅ |
| A2 | Offer sync client — OfferSyncClient with discover_offers, sync_offers, get_sync_status, get_offer_cache | 🔴 P0 | `aitbc/trading/offer_client.py` (new) | ✅ |
| A3 | Offer cache — OfferCache wrapping RedisCache for offer-specific caching | 🔴 P0 | `aitbc/trading/offer_cache.py` (new) | ✅ |
| A4 | Unit tests for A1-A3 | High | `tests/unit/test_offer_sync.py` (new) | ✅ |

---

## A1: Offer Sync Types

Create `aitbc/trading/offer_types.py`:
- `OfferSyncStatus` enum — fresh, stale, syncing, error
- `SyncedOffer` dataclass — cached offer with sync metadata
- `OfferSyncConfig` dataclass — per-chain sync intervals + staleness thresholds
- `OfferDiscoveryRequest` dataclass — discovery query with filters
- `OfferDiscoveryResult` dataclass — ranked, deduplicated results

---

## A2: Offer Sync Client

Create `aitbc/trading/offer_client.py`:
- `OfferSyncClient` — async HTTP client for offer sync endpoints
- `discover_offers(filters)` — discover offers across chains
- `sync_offers(chain_id)` — trigger sync for a specific chain
- `get_sync_status(chain_id)` — get sync status for a chain
- `get_offer_cache(offer_id)` — get cached offer

---

## A3: Offer Cache

Create `aitbc/trading/offer_cache.py`:
- `OfferCache` — wraps RedisCache for offer-specific caching
- `get_offer(offer_id)` — get cached offer
- `set_offer(offer_id, offer, ttl)` — cache offer with TTL
- `delete_offer(offer_id)` — delete cached offer
- `list_offers_by_chain(chain_id)` — list all offers for a chain
- `is_stale(offer_id)` — check if offer is stale
- `refresh_stale_offers(chain_id)` — refresh stale offers
- `get_sync_metadata(offer_id)` — get sync metadata
- Fallback to in-memory dict when Redis unavailable

---

## A4: Unit Tests

`tests/unit/test_offer_sync.py` — tests for:
- Offer sync types serialization
- Offer sync client HTTP methods (mocked httpx)
- Offer cache get/set/delete
- Staleness detection
- Sync metadata tracking

---

## Related Topics

- [Overview](./overview.md) - Release overview and status baseline
- [Agent B Tasks](./agent-b.md) - Apps & infrastructure implementation details

---

**Documentation Version**: 1.0
**Last Updated**: 2026-06-30
**Release**: v0.8.1 — Cross-Chain Offer Synchronization
**Agent**: Agent A (Shared Core)
