# Get Ratings

Get ratings for an offer

- **Status**: ✅
- **Release**: —

## Implementation Details

- `aitbc/trading/offer_types.py` — from **future** import annotations from dataclasses import dataclass, field from enum import StrEnum...
- `aitbc/marketplace/offer_fsm.py` — from **future** import annotations import logging from enum import StrEnum logger = logging.getLogge...
- `aitbc/trading/offer_cache.py` — Get a single offer from the cache.
- `apps/trading/src/trading_service/services/offer_search_service.py` — Initialize the external search backend client.
- `Marketplace` exposes `GET /v1/marketplace/offer/{service_id}/ratings` (operation `get_service_ratings_v1_marketplace_offer__service_id__ratings_get`) — Get Service Ratings
- `Marketplace` exposes `GET /v1/marketplace/offers/{offer_id}` (operation `get_offer_v1_marketplace_offers__offer_id__get`) — Get Offer
- `Marketplace` exposes `GET /v1/marketplace/offers/{offer_id}/history` (operation `get_offer_history_v1_marketplace_offers__offer_id__history_get`) — Get Offer History

## Examples

- `GET /v1/trading/offers/sync-status` (`get_offer_sync_status` in `apps/trading/src/trading_service/routers/offers.py`)
- `GET /v1/trading/offers/cache` (`get_cached_offers` in `apps/trading/src/trading_service/routers/offers.py`)
- `GET /v1/trading/offers/subscription-status` (`get_subscription_status` in `apps/trading/src/trading_service/routers/subscriptions.py`)
- `GET /offers/cross-chain` (`get_integrated_marketplace_offers` in `apps/coordinator-api/src/coordinator_api/contexts/marketplace/routers/global_marketplace_integration.py`)
- `GET /offers/{offer_id}/cross-chain-details` (`get_cross_chain_offer_details` in `apps/coordinator-api/src/coordinator_api/contexts/marketplace/routers/global_marketplace_integration.py`)
- `GET /v1/marketplace/offer/{service_id}/ratings` (`get_service_ratings_v1_marketplace_offer__service_id__ratings_get`) on `Marketplace`
- `GET /v1/marketplace/offers/{offer_id}` (`get_offer_v1_marketplace_offers__offer_id__get`) on `Marketplace`
- `GET /v1/marketplace/offers/{offer_id}/history` (`get_offer_history_v1_marketplace_offers__offer_id__history_get`) on `Marketplace`

## Operational Notes

- **Status / Release:** `✅` / `—`
