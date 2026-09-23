# Dynamic Pricing

Apply dynamic pricing strategies to offers

- **Status**: ✅
- **Release**: —

## Implementation Details

- `apps/coordinator-api/src/coordinator_api/contexts/trading/domain/pricing_strategies.py` — Pricing Strategies Domain Module Defines various pricing strategies and their configurations for dyn...
- `apps/coordinator-api/src/coordinator_api/contexts/trading/schemas/pricing.py` — Pricing API Schemas Pydantic models for dynamic pricing API requests and responses
- `apps/coordinator-api/alembic/versions/add_dynamic_pricing_tables.py` — Add dynamic pricing tables Revision ID: add_dynamic_pricing_tables Revises: initial_migration Create...
- `apps/coordinator-api/src/coordinator_api/contexts/trading/domain/pricing_models.py` — Pricing Models for Dynamic Pricing Database Schema SQLModel definitions for pricing history, strateg...
- `Market` exposes `POST /v1/market/dynamic-pricing` (operation `calculate_dynamic_pricing_v1_market_dynamic_pricing_post`) — Calculate Dynamic Pricing
- `Openapi` exposes `POST /v1/global-market-integration/offers/{offer_id}/optimize-pricing` (operation `optimize_offer_pricing_v1_global_market_integration_offers__offer_id__optimize_pricing_post`) — Optimize Offer Pricing *(router not mounted — 404s today)*
- `Coordinator API` exposes `GET /v1/market/offers` (operation `list_market_offers_v1_market_offers_get`) — List market offers

## Examples

- `POST /offers/{offer_id}/optimize-pricing` (`optimize_offer_pricing` in `apps/coordinator-api/src/coordinator_api/contexts/market/routers/global_market_integration.py`) *(router defined but not mounted in `main.py` — 404s today)*
- `POST /v1/trading/offers/discover` (`discover_offers` in `apps/trading/src/trading_service/routers/offers.py`)
- `POST /v1/trading/offers/sync` (`sync_offers` in `apps/trading/src/trading_service/routers/offers.py`)
- `GET /v1/trading/offers/sync-status` (`get_offer_sync_status` in `apps/trading/src/trading_service/routers/offers.py`)
- `GET /v1/trading/offers/cache` (`get_cached_offers` in `apps/trading/src/trading_service/routers/offers.py`)
- `POST /v1/market/dynamic-pricing` (`calculate_dynamic_pricing_v1_market_dynamic_pricing_post`) on `Market`
- `POST /v1/global-market-integration/offers/{offer_id}/optimize-pricing` (`optimize_offer_pricing_v1_global_market_integration_offers__offer_id__optimize_pricing_post`) on `Openapi`
- `GET /v1/market/offers` (`list_market_offers_v1_market_offers_get`) on `Coordinator API`

## Operational Notes

- **Status / Release:** `✅` / `—`
