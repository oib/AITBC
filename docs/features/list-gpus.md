# List GPUs

List all GPUs with filters

- **Status**: ✅
- **Release**: —

## Implementation Details

- API endpoint `GET /` implemented in `apps/edge/src/aitbc_edge/routers/gpu.py`
- API endpoint `GET /marketplace/gpu/list` implemented in `apps/coordinator-api/src/coordinator_api/contexts/marketplace/routers/marketplace_gpu.py`
- API endpoint `POST /join` implemented in `apps/edge/src/aitbc_edge/routers/islands.py`
- API endpoint `POST /leave` implemented in `apps/edge/src/aitbc_edge/routers/islands.py`
- API endpoint `GET /` implemented in `apps/edge/src/aitbc_edge/routers/islands.py`
- `Blockchain Node` exposes `GET /rpc/gpus` (operation `list_gpus_rpc_gpus_get`) — List all registered GPUs
- `Coordinator API` exposes `GET /v1/marketplace/gpu/list` (operation `list_gpus_v1_marketplace_gpu_list_get`) — List Gpus
- `Openapi` exposes `GET /v1/marketplace/gpu/list` (operation `list_gpus_v1_marketplace_gpu_list_get`) — List Gpus

## Examples

- `GET /` (`list_gpus` in `apps/edge/src/aitbc_edge/routers/gpu.py`)
- `GET /marketplace/gpu/list` (`list_gpus` in `apps/coordinator-api/src/coordinator_api/contexts/marketplace/routers/marketplace_gpu.py`)
- `POST /join` (`join_island` in `apps/edge/src/aitbc_edge/routers/islands.py`)
- `POST /leave` (`leave_island` in `apps/edge/src/aitbc_edge/routers/islands.py`)
- `GET /` (`list_islands` in `apps/edge/src/aitbc_edge/routers/islands.py`)
- `GET /rpc/gpus` (`list_gpus_rpc_gpus_get`) on `Blockchain Node`
- `GET /v1/marketplace/gpu/list` (`list_gpus_v1_marketplace_gpu_list_get`) on `Coordinator API`
- `GET /v1/marketplace/gpu/list` (`list_gpus_v1_marketplace_gpu_list_get`) on `Openapi`

## Operational Notes

- **Status / Release:** `✅` / `—`
