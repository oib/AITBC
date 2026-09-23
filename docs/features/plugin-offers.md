# Plugin Offers

Get offers from specific plugins

- **Status**: ✅
- **Release**: —

## Implementation Details

- `apps/coordinator-api/src/coordinator_api/contexts/market/services/plugin_manager.py` — Plugin Manager for market extensibility.
- `apps/trading/src/trading_service/routers/offers.py` — Offer sync and discovery endpoints for the Trading Service.
- `Coordinator API` exposes `GET /v1/market/offers` (operation `list_market_offers_v1_market_offers_get`) — List market offers
- `Coordinator API` exposes `GET /v1/market/plugins` (operation `list_market_plugins_v1_market_plugins_get`) — List market plugins
- `Coordinator API` exposes `GET /v1/market/miner-offers` (operation `list_miner_offers_v1_market_miner_offers_get`) — List all miner offers

## Examples

- `GET /v1/trading/offers/sync-status` (`get_offer_sync_status` in `apps/trading/src/trading_service/routers/offers.py`)
- `GET /v1/trading/offers/cache` (`get_cached_offers` in `apps/trading/src/trading_service/routers/offers.py`)
- `GET /v1/trading/offers/subscription-status` (`get_subscription_status` in `apps/trading/src/trading_service/routers/subscriptions.py`)
- `GET /market/plugins` (`list_market_plugins` in `apps/coordinator-api/src/coordinator_api/contexts/market/routers/market.py`)
- `GET /offers/cross-chain` (`get_integrated_market_offers` in `apps/coordinator-api/src/coordinator_api/contexts/market/routers/global_market_integration.py`) *(router defined but not mounted in `main.py` — 404s today)*
- `GET /v1/market/offers` (`list_market_offers_v1_market_offers_get`) on `Coordinator API`
- `GET /v1/market/plugins` (`list_market_plugins_v1_market_plugins_get`) on `Coordinator API`
- `GET /v1/market/miner-offers` (`list_miner_offers_v1_market_miner_offers_get`) on `Coordinator API`

## Operational Notes

- **Status / Release:** `✅` / `—`
