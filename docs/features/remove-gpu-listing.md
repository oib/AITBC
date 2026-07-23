# Remove GPU Listing

Remove GPU listing

- **Status**: ✅
- **Release**: —
## Implementation Details
- `apps/edge/src/aitbc_edge/services/gpu_service.py` — GPU service for Edge API Service
- `apps/edge/src/aitbc_edge/routers/gpu.py` — GPU operations router for Edge API Service
- `apps/edge/src/aitbc_edge/schemas/gpu.py` — GPU-related schemas for Edge API Service
- `apps/coordinator-api/src/coordinator_api/contexts/marketplace/routers/marketplace_gpu.py` — Get pricing engine instance
- `Blockchain Node` exposes `GET /rpc/gpus` (operation `list_gpus_rpc_gpus_get`) — List all registered GPUs
- `Blockchain Node` exposes `GET /rpc/gpu/allocations/{gpu_id}` (operation `get_gpu_allocations_rpc_gpu_allocations__gpu_id__get`) — Query GPU allocations
- `Blockchain Node` exposes `POST /rpc/gpu/register` (operation `register_gpu_rpc_gpu_register_post`) — Register GPU on-chain
## Examples

- `DELETE /{gpu_id}` (`remove_gpu_listing` in `apps/edge/src/aitbc_edge/routers/gpu.py`)
- `GET /{gpu_id}` (`get_gpu_listing` in `apps/edge/src/aitbc_edge/routers/gpu.py`)
- `GET /` (`list_gpus` in `apps/edge/src/aitbc_edge/routers/gpu.py`)
- `POST /scan` (`scan_gpus` in `apps/edge/src/aitbc_edge/routers/gpu.py`)
- `GET /{gpu_id}/metrics` (`get_gpu_metrics` in `apps/edge/src/aitbc_edge/routers/gpu.py`)
- `GET /rpc/gpus` (`list_gpus_rpc_gpus_get`) on `Blockchain Node`
- `GET /rpc/gpu/allocations/{gpu_id}` (`get_gpu_allocations_rpc_gpu_allocations__gpu_id__get`) on `Blockchain Node`
- `POST /rpc/gpu/register` (`register_gpu_rpc_gpu_register_post`) on `Blockchain Node`
## Operational Notes
- **Status / Release:** `✅` / `—`
- Provides listing, matching, pricing, and settlement for marketplace participants.
