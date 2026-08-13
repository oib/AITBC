# Dynamic Pricing

Apply dynamic pricing strategies to offers

- **Status**: ✅
- **Release**: —

## Implementation Details

- `apps/coordinator-api/src/coordinator_api/contexts/trading/domain/pricing_strategies.py` — Pricing Strategies Domain Module Defines various pricing strategies and their configurations for dyn...
- `apps/coordinator-api/src/coordinator_api/contexts/trading/schemas/pricing.py` — Pricing API Schemas Pydantic models for dynamic pricing API requests and responses
- `apps/coordinator-api/alembic/versions/add_dynamic_pricing_tables.py` — Add dynamic pricing tables Revision ID: add_dynamic_pricing_tables Revises: initial_migration Create...
- `apps/coordinator-api/src/coordinator_api/contexts/trading/domain/pricing_models.py` — Pricing Models for Dynamic Pricing Database Schema SQLModel definitions for pricing history, strateg...
- `Marketplace` exposes `POST /v1/marketplace/dynamic-pricing` (operation `calculate_dynamic_pricing_v1_marketplace_dynamic_pricing_post`) — Calculate Dynamic Pricing
- `Openapi` exposes `POST /v1/global-marketplace-integration/offers/{offer_id}/optimize-pricing` (operation `optimize_offer_pricing_v1_global_marketplace_integration_offers__offer_id__optimize_pricing_post`) — Optimize Offer Pricing
- `Coordinator API` exposes `GET /v1/marketplace/offers` (operation `list_marketplace_offers_v1_marketplace_offers_get`) — List marketplace offers

## Examples

- `POST /offers/{offer_id}/optimize-pricing` (`optimize_offer_pricing` in `apps/coordinator-api/src/coordinator_api/contexts/marketplace/routers/global_marketplace_integration.py`)
- `POST /v1/trading/offers/discover` (`discover_offers` in `apps/trading/src/trading_service/routers/offers.py`)
- `POST /v1/trading/offers/sync` (`sync_offers` in `apps/trading/src/trading_service/routers/offers.py`)
- `GET /v1/trading/offers/sync-status` (`get_offer_sync_status` in `apps/trading/src/trading_service/routers/offers.py`)
- `GET /v1/trading/offers/cache` (`get_cached_offers` in `apps/trading/src/trading_service/routers/offers.py`)
- `POST /v1/marketplace/dynamic-pricing` (`calculate_dynamic_pricing_v1_marketplace_dynamic_pricing_post`) on `Marketplace`
- `POST /v1/global-marketplace-integration/offers/{offer_id}/optimize-pricing` (`optimize_offer_pricing_v1_global_marketplace_integration_offers__offer_id__optimize_pricing_post`) on `Openapi`
- `GET /v1/marketplace/offers` (`list_marketplace_offers_v1_marketplace_offers_get`) on `Coordinator API`

## Operational Notes

- **Status / Release:** `✅` / `—`
