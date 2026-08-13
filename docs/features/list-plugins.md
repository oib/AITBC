# List Plugins

List marketplace plugins

- **Status**: ✅
- **Release**: —

## Implementation Details

- `apps/marketplace/src/marketplace_service/services/marketplace_service.py` — Marketplace service for managing marketplace operations
- `apps/coordinator-api/src/coordinator_api/contexts/marketplace/domain/gpu_marketplace.py` — Persistent SQLModel tables for the GPU marketplace.
- `apps/coordinator-api/src/coordinator_api/contexts/marketplace/routers/marketplace.py` — List available marketplace plugins
- `apps/blockchain-event-bridge/src/blockchain_event_bridge/action_handlers/marketplace.py` — Marketplace action handler for triggering marketplace state updates.
- `apps/coordinator-api/src/coordinator_api/contexts/marketplace/domain/global_marketplace.py` — Global Marketplace Domain Models Domain models for global marketplace operations, multi-region suppo...
- `Coordinator API` exposes `GET /v1/marketplace/plugins` (operation `list_marketplace_plugins_v1_marketplace_plugins_get`) — List marketplace plugins
- `Blockchain Node` exposes `GET /rpc/marketplace/listings` (operation `marketplace_listings_rpc_marketplace_listings_get`) — List marketplace items
- `Coordinator API` exposes `GET /v1/marketplace/offers` (operation `list_marketplace_offers_v1_marketplace_offers_get`) — List marketplace offers

## Examples

- `GET /marketplace/plugins` (`list_marketplace_plugins` in `apps/coordinator-api/src/coordinator_api/contexts/marketplace/routers/marketplace.py`)
- `GET /marketplace/offers` (`list_marketplace_offers` in `apps/coordinator-api/src/coordinator_api/contexts/marketplace/routers/marketplace.py`)
- `GET /marketplace/miner-offers` (`list_miner_offers` in `apps/coordinator-api/src/coordinator_api/contexts/marketplace/routers/marketplace_offers.py`)
- `GET /marketplace/gpu/list` (`list_gpus` in `apps/coordinator-api/src/coordinator_api/contexts/marketplace/routers/marketplace_gpu.py`)
- `GET /marketplace/orders` (`list_orders` in `apps/coordinator-api/src/coordinator_api/contexts/marketplace/routers/marketplace_gpu.py`)
- `GET /v1/marketplace/plugins` (`list_marketplace_plugins_v1_marketplace_plugins_get`) on `Coordinator API`
- `GET /rpc/marketplace/listings` (`marketplace_listings_rpc_marketplace_listings_get`) on `Blockchain Node`
- `GET /v1/marketplace/offers` (`list_marketplace_offers_v1_marketplace_offers_get`) on `Coordinator API`

## Operational Notes

- **Status / Release:** `✅` / `—`
