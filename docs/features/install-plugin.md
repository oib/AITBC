# Install Plugin

Install a market plugin

- **Status**: ✅
- **Release**: —

## Implementation Details

- `apps/coordinator-api/src/coordinator_api/contexts/market/services/plugin_manager.py` — Plugin Manager for market extensibility.
- `apps/market/src/market_service/domain/market.py` — Software service registry for market (migrated from plugin service)
- `Market` exposes `POST /v1/market/plugins` (operation `register_plugin_v1_market_plugins_post`) — Register Plugin
- `Market` exposes `GET /v1/market/offer/{plugin_id}` (operation `get_software_offer_v1_market_offer__plugin_id__get`) — Get Software Offer
- `Market` exposes `DELETE /v1/market/offer/{plugin_id}` (operation `unregister_offer_v1_market_offer__plugin_id__delete`) — Unregister Offer

## Examples

- `GET /market/plugins` (`list_market_plugins` in `apps/coordinator-api/src/coordinator_api/contexts/market/routers/market.py`)
- `GET /` (`list_gpus` in `apps/edge/src/aitbc_edge/routers/gpu.py`)
- `GET /{gpu_id}` (`get_gpu_listing` in `apps/edge/src/aitbc_edge/routers/gpu.py`)
- `DELETE /{gpu_id}` (`remove_gpu_listing` in `apps/edge/src/aitbc_edge/routers/gpu.py`)
- `POST /scan` (`scan_gpus` in `apps/edge/src/aitbc_edge/routers/gpu.py`)
- `POST /v1/market/plugins` (`register_plugin_v1_market_plugins_post`) on `Market`
- `GET /v1/market/offer/{plugin_id}` (`get_software_offer_v1_market_offer__plugin_id__get`) on `Market`
- `DELETE /v1/market/offer/{plugin_id}` (`unregister_offer_v1_market_offer__plugin_id__delete`) on `Market`

## Operational Notes

- **Status / Release:** `✅` / `—`
