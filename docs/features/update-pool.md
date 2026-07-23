# Update Pool

Update pool settings

- **Status**: ✅
- **Release**: v0.6.7
## Implementation Details
- `apps/pool-hub/src/poolhub/settings.py` — Backward-compatible property: returns the database URL.
- `aitbc/network/http_pool.py` — import asyncio from typing import Any import httpx from aitbc.aitbc_logging import get_logger logger...
- `apps/wallet/src/wallet_app/settings.py` — Runtime configuration for the wallet daemon service.
- API endpoint `POST /requests` implemented in `apps/edge/src/aitbc_edge/routers/serve.py`
- API endpoint `GET /requests` implemented in `apps/edge/src/aitbc_edge/routers/serve.py`
- `Coordinator API` exposes `GET /v1/admin/debug-settings` (operation `debug_settings_v1_admin_debug_settings_get`) — Debug settings
- `Coordinator API` exposes `POST /v1/miners/register` (operation `register_v1_miners_register_post`) — Register or update miner
- `Coordinator API` exposes `PUT /v1/miners/{miner_id}/capabilities` (operation `update_miner_capabilities_v1_miners__miner_id__capabilities_put`) — Update miner capabilities
## Examples

- `POST /requests` (`submit_compute_request` in `apps/edge/src/aitbc_edge/routers/serve.py`)
- `GET /requests` (`list_compute_requests` in `apps/edge/src/aitbc_edge/routers/serve.py`)
- `GET /requests/{request_id}` (`get_compute_request` in `apps/edge/src/aitbc_edge/routers/serve.py`)
- `POST /requests/{request_id}/cancel` (`cancel_compute_request` in `apps/edge/src/aitbc_edge/routers/serve.py`)
- `GET /requests/{request_id}/result` (`get_compute_result` in `apps/edge/src/aitbc_edge/routers/serve.py`)
- `GET /v1/admin/debug-settings` (`debug_settings_v1_admin_debug_settings_get`) on `Coordinator API`
- `POST /v1/miners/register` (`register_v1_miners_register_post`) on `Coordinator API`
- `PUT /v1/miners/{miner_id}/capabilities` (`update_miner_capabilities_v1_miners__miner_id__capabilities_put`) on `Coordinator API`
## Operational Notes
- **Status / Release:** `✅` / `v0.6.7`
- Manages pool configuration, worker tracking, and payout scheduling.
- The pool-hub manages miner registration, job assignment, scoring, and reward distribution.
