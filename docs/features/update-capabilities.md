# Update Capabilities

Update miner capabilities

- **Status**: ✅
- **Release**: —

## Implementation Details

- `apps/pool-hub/src/poolhub/repositories/miner_repository.py` — Coordinates miner registry persistence across PostgreSQL and Redis.
- `apps/coordinator-api/src/coordinator_api/contexts/infrastructure/routers/miner.py` — List jobs assigned to a specific miner
- `apps/miner/production_miner.py` — Real GPU Miner Client for AITBC - runs on host with actual GPU
- `apps/coordinator-api/scripts/advanced_agent_capabilities.py` — Advanced AI Agent Capabilities Implementation - Phase 5 Multi-Modal Agent Architecture and Adaptive ...
- `Coordinator API` exposes `PUT /v1/miners/{miner_id}/capabilities` (operation `update_miner_capabilities_v1_miners__miner_id__capabilities_put`) — Update miner capabilities
- `Coordinator API` exposes `POST /v1/miners/register` (operation `register_v1_miners_register_post`) — Register or update miner
- `Coordinator API` exposes `POST /v1/admin/debug/create-test-miner` (operation `create_test_miner_v1_admin_debug_create_test_miner_post`) — Create a test miner for debugging

## Examples

- `PUT /miners/{miner_id}/capabilities` (`update_miner_capabilities` in `apps/coordinator-api/src/coordinator_api/contexts/infrastructure/routers/miner.py`)
- `GET /` (`list_gpus` in `apps/edge/src/aitbc_edge/routers/gpu.py`)
- `GET /{gpu_id}` (`get_gpu_listing` in `apps/edge/src/aitbc_edge/routers/gpu.py`)
- `DELETE /{gpu_id}` (`remove_gpu_listing` in `apps/edge/src/aitbc_edge/routers/gpu.py`)
- `POST /scan` (`scan_gpus` in `apps/edge/src/aitbc_edge/routers/gpu.py`)
- `PUT /v1/miners/{miner_id}/capabilities` (`update_miner_capabilities_v1_miners__miner_id__capabilities_put`) on `Coordinator API`
- `POST /v1/miners/register` (`register_v1_miners_register_post`) on `Coordinator API`
- `POST /v1/admin/debug/create-test-miner` (`create_test_miner_v1_admin_debug_create_test_miner_post`) on `Coordinator API`

## Operational Notes

- **Status / Release:** `✅` / `—`
