# List Plugins

List market plugins

- **Status**: ✅
- **Release**: —

## Implementation Details

- `apps/market/src/market_service/services/market_service.py` — Market service for managing market operations
- `apps/coordinator-api/src/coordinator_api/contexts/market/domain/gpu_market.py` — Persistent SQLModel tables for the GPU market.
- `apps/coordinator-api/src/coordinator_api/contexts/market/routers/market.py` — List available market plugins
- `apps/blockchain-event-bridge/src/blockchain_event_bridge/action_handlers/market.py` — Market action handler for triggering market state updates.
- `apps/coordinator-api/src/coordinator_api/contexts/market/domain/global_market.py` — Global Market Domain Models Domain models for global market operations, multi-region suppo...
- `Coordinator API` exposes `GET /v1/market/plugins` (operation `list_market_plugins_v1_market_plugins_get`) — List market plugins
- `Blockchain Node` exposes `GET /rpc/market/listings` (operation `market_listings_rpc_market_listings_get`) — List market items
- `Coordinator API` exposes `GET /v1/market/offers` (operation `list_market_offers_v1_market_offers_get`) — List market offers

## Examples

- `GET /market/plugins` (`list_market_plugins` in `apps/coordinator-api/src/coordinator_api/contexts/market/routers/market.py`)
- `GET /market/offers` (`list_market_offers` in `apps/coordinator-api/src/coordinator_api/contexts/market/routers/market.py`)
- `GET /market/miner-offers` (`list_miner_offers` in `apps/coordinator-api/src/coordinator_api/contexts/market/routers/market_offers.py`)
- `GET /market/gpu/list` (`list_gpus` in `apps/coordinator-api/src/coordinator_api/contexts/market/routers/market_gpu.py`)
- `GET /market/orders` (`list_orders` in `apps/coordinator-api/src/coordinator_api/contexts/market/routers/market_gpu.py`)
- `GET /v1/market/plugins` (`list_market_plugins_v1_market_plugins_get`) on `Coordinator API`
- `GET /rpc/market/listings` (`market_listings_rpc_market_listings_get`) on `Blockchain Node`
- `GET /v1/market/offers` (`list_market_offers_v1_market_offers_get`) on `Coordinator API`

## Operational Notes

- **Status / Release:** `✅` / `—`
