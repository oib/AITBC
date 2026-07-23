# Install Plugin

Install a marketplace plugin

- **Status**: ✅
- **Release**: —
## Implementation Details
- `apps/coordinator-api/src/coordinator_api/contexts/marketplace/services/plugin_manager.py` — Plugin Manager for marketplace extensibility.
- `apps/marketplace/src/marketplace_service/domain/marketplace.py` — Software service registry for marketplace (migrated from plugin service)
- `Marketplace` exposes `POST /v1/marketplace/plugins` (operation `register_plugin_v1_marketplace_plugins_post`) — Register Plugin
- `Marketplace` exposes `GET /v1/marketplace/offer/{plugin_id}` (operation `get_software_offer_v1_marketplace_offer__plugin_id__get`) — Get Software Offer
- `Marketplace` exposes `DELETE /v1/marketplace/offer/{plugin_id}` (operation `unregister_offer_v1_marketplace_offer__plugin_id__delete`) — Unregister Offer
## Examples

- `GET /marketplace/plugins` (`list_marketplace_plugins` in `apps/coordinator-api/src/coordinator_api/contexts/marketplace/routers/marketplace.py`)
- `GET /` (`list_gpus` in `apps/edge/src/aitbc_edge/routers/gpu.py`)
- `GET /{gpu_id}` (`get_gpu_listing` in `apps/edge/src/aitbc_edge/routers/gpu.py`)
- `DELETE /{gpu_id}` (`remove_gpu_listing` in `apps/edge/src/aitbc_edge/routers/gpu.py`)
- `POST /scan` (`scan_gpus` in `apps/edge/src/aitbc_edge/routers/gpu.py`)
- `POST /v1/marketplace/plugins` (`register_plugin_v1_marketplace_plugins_post`) on `Marketplace`
- `GET /v1/marketplace/offer/{plugin_id}` (`get_software_offer_v1_marketplace_offer__plugin_id__get`) on `Marketplace`
- `DELETE /v1/marketplace/offer/{plugin_id}` (`unregister_offer_v1_marketplace_offer__plugin_id__delete`) on `Marketplace`
## Operational Notes
- **Status / Release:** `✅` / `—`
