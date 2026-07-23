# Rate Offer

Rate a marketplace offer/service

- **Status**: ✅
- **Release**: —
## Implementation Details
- `apps/coordinator-api/src/coordinator_api/contexts/marketplace/domain/global_marketplace.py` — Global Marketplace Domain Models Domain models for global marketplace operations, multi-region suppo...
- `apps/coordinator-api/alembic/versions/add_global_marketplace.py` — Add global marketplace tables Revision ID: add_global_marketplace Revises: add_cross_chain_reputatio...
- `apps/coordinator-api/src/coordinator_api/contexts/marketplace/routers/marketplace.py` — List available marketplace plugins
- `Marketplace` exposes `POST /v1/marketplace/offer/{service_id}/rate` (operation `rate_service_v1_marketplace_offer__service_id__rate_post`) — Rate Service
- `Marketplace` exposes `GET /v1/marketplace/offer/{service_id}/ratings` (operation `get_service_ratings_v1_marketplace_offer__service_id__ratings_get`) — Get Service Ratings
- `Marketplace` exposes `POST /v1/marketplace/offers` (operation `create_offer_v1_marketplace_offers_post`) — Create Offer
## Examples

- `GET /offers/cross-chain` (`get_integrated_marketplace_offers` in `apps/coordinator-api/src/coordinator_api/contexts/marketplace/routers/global_marketplace_integration.py`)
- `GET /marketplace/offers` (`list_marketplace_offers` in `apps/coordinator-api/src/coordinator_api/contexts/marketplace/routers/marketplace.py`)
- `POST /offers/create-cross-chain` (`create_cross_chain_marketplace_offer` in `apps/coordinator-api/src/coordinator_api/contexts/marketplace/routers/global_marketplace_integration.py`)
- `POST /marketplace/sync-offers` (`sync_offers` in `apps/coordinator-api/src/coordinator_api/contexts/marketplace/routers/marketplace_offers.py`)
- `GET /marketplace/miner-offers` (`list_miner_offers` in `apps/coordinator-api/src/coordinator_api/contexts/marketplace/routers/marketplace_offers.py`)
- `POST /v1/marketplace/offer/{service_id}/rate` (`rate_service_v1_marketplace_offer__service_id__rate_post`) on `Marketplace`
- `GET /v1/marketplace/offer/{service_id}/ratings` (`get_service_ratings_v1_marketplace_offer__service_id__ratings_get`) on `Marketplace`
- `POST /v1/marketplace/offers` (`create_offer_v1_marketplace_offers_post`) on `Marketplace`
## Operational Notes
- **Status / Release:** `✅` / `—`
- Provides unified entry point with authentication, rate limiting, and request forwarding.
