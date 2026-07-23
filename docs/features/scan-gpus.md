# Scan GPUs

Scan GPUs for a miner

- **Status**: ✅
- **Release**: —
## Implementation Details
- `apps/miner/production_miner.py` — Real GPU Miner Client for AITBC - runs on host with actual GPU
- `apps/pool-hub/src/poolhub/repositories/miner_repository.py` — Coordinates miner registry persistence across PostgreSQL and Redis.
- `apps/coordinator-api/src/coordinator_api/contexts/infrastructure/routers/miner.py` — List jobs assigned to a specific miner
- `Blockchain Node` exposes `GET /rpc/gpus` (operation `list_gpus_rpc_gpus_get`) — List all registered GPUs
- `Coordinator API` exposes `POST /v1/admin/debug/create-test-miner` (operation `create_test_miner_v1_admin_debug_create_test_miner_post`) — Create a test miner for debugging
- `Coordinator API` exposes `GET /v1/marketplace/gpu/list` (operation `list_gpus_v1_marketplace_gpu_list_get`) — List Gpus
## Examples

- `POST /scan` (`scan_gpus` in `apps/edge/src/aitbc_edge/routers/gpu.py`)
- `GET /` (`list_gpus` in `apps/edge/src/aitbc_edge/routers/gpu.py`)
- `GET /{gpu_id}` (`get_gpu_listing` in `apps/edge/src/aitbc_edge/routers/gpu.py`)
- `DELETE /{gpu_id}` (`remove_gpu_listing` in `apps/edge/src/aitbc_edge/routers/gpu.py`)
- `GET /{gpu_id}/metrics` (`get_gpu_metrics` in `apps/edge/src/aitbc_edge/routers/gpu.py`)
- `GET /rpc/gpus` (`list_gpus_rpc_gpus_get`) on `Blockchain Node`
- `POST /v1/admin/debug/create-test-miner` (`create_test_miner_v1_admin_debug_create_test_miner_post`) on `Coordinator API`
- `GET /v1/marketplace/gpu/list` (`list_gpus_v1_marketplace_gpu_list_get`) on `Coordinator API`
## Operational Notes
- **Status / Release:** `✅` / `—`
