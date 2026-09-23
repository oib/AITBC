# Rate Offer

Rate a market offer/service

- **Status**: ✅
- **Release**: —

## Implementation Details

- `apps/coordinator-api/src/coordinator_api/contexts/market/domain/global_market.py` — Global Market Domain Models Domain models for global market operations, multi-region suppo...
- `apps/coordinator-api/alembic/versions/add_global_market.py` — Add global market tables Revision ID: add_global_market Revises: add_cross_chain_reputatio...
- `apps/coordinator-api/src/coordinator_api/contexts/market/routers/market.py` — List available market plugins
- `Market` exposes `POST /v1/market/offer/{service_id}/rate` (operation `rate_service_v1_market_offer__service_id__rate_post`) — Rate Service
- `Market` exposes `GET /v1/market/offer/{service_id}/ratings` (operation `get_service_ratings_v1_market_offer__service_id__ratings_get`) — Get Service Ratings
- `Market` exposes `POST /v1/market/offers` (operation `create_offer_v1_market_offers_post`) — Create Offer

## Examples

- `GET /offers/cross-chain` (`get_integrated_market_offers` in `apps/coordinator-api/src/coordinator_api/contexts/market/routers/global_market_integration.py`) *(router defined but not mounted in `main.py` — 404s today)*
- `GET /market/offers` (`list_market_offers` in `apps/coordinator-api/src/coordinator_api/contexts/market/routers/market.py`)
- `POST /offers/create-cross-chain` (`create_cross_chain_market_offer` in `apps/coordinator-api/src/coordinator_api/contexts/market/routers/global_market_integration.py`) *(router defined but not mounted in `main.py` — 404s today)*
- `POST /market/sync-offers` (`sync_offers` in `apps/coordinator-api/src/coordinator_api/contexts/market/routers/market_offers.py`)
- `GET /market/miner-offers` (`list_miner_offers` in `apps/coordinator-api/src/coordinator_api/contexts/market/routers/market_offers.py`)
- `POST /v1/market/offer/{service_id}/rate` (`rate_service_v1_market_offer__service_id__rate_post`) on `Market`
- `GET /v1/market/offer/{service_id}/ratings` (`get_service_ratings_v1_market_offer__service_id__ratings_get`) on `Market`
- `POST /v1/market/offers` (`create_offer_v1_market_offers_post`) on `Market`

## Operational Notes

- **Status / Release:** `✅` / `—`
- Provides unified entry point with authentication, rate limiting, and request forwarding.
