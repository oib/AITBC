# Plugin Offers

Get offers from specific plugins

- **Status**: ✅
- **Release**: —

## Implementation Details

- `apps/coordinator-api/src/coordinator_api/contexts/marketplace/services/plugin_manager.py` — Plugin Manager for marketplace extensibility.
- `apps/trading/src/trading_service/routers/offers.py` — Offer sync and discovery endpoints for the Trading Service.
- `Coordinator API` exposes `GET /v1/marketplace/offers` (operation `list_marketplace_offers_v1_marketplace_offers_get`) — List marketplace offers
- `Coordinator API` exposes `GET /v1/marketplace/plugins` (operation `list_marketplace_plugins_v1_marketplace_plugins_get`) — List marketplace plugins
- `Coordinator API` exposes `GET /v1/marketplace/miner-offers` (operation `list_miner_offers_v1_marketplace_miner_offers_get`) — List all miner offers

## Examples

- `GET /v1/trading/offers/sync-status` (`get_offer_sync_status` in `apps/trading/src/trading_service/routers/offers.py`)
- `GET /v1/trading/offers/cache` (`get_cached_offers` in `apps/trading/src/trading_service/routers/offers.py`)
- `GET /v1/trading/offers/subscription-status` (`get_subscription_status` in `apps/trading/src/trading_service/routers/subscriptions.py`)
- `GET /marketplace/plugins` (`list_marketplace_plugins` in `apps/coordinator-api/src/coordinator_api/contexts/marketplace/routers/marketplace.py`)
- `GET /offers/cross-chain` (`get_integrated_marketplace_offers` in `apps/coordinator-api/src/coordinator_api/contexts/marketplace/routers/global_marketplace_integration.py`)
- `GET /v1/marketplace/offers` (`list_marketplace_offers_v1_marketplace_offers_get`) on `Coordinator API`
- `GET /v1/marketplace/plugins` (`list_marketplace_plugins_v1_marketplace_plugins_get`) on `Coordinator API`
- `GET /v1/marketplace/miner-offers` (`list_miner_offers_v1_marketplace_miner_offers_get`) on `Coordinator API`

## Operational Notes

- **Status / Release:** `✅` / `—`
