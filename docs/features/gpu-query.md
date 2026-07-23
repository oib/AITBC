# GPU Query

Query GPU registrations and allocations

- **Status**: ✅
- **Release**: —
## Implementation Details
- `apps/blockchain-node/src/aitbc_chain/rpc/gpu_resources.py` — GPU resource RPC endpoints for AITBC blockchain.
- `apps/gpu/src/gpu_service/services/edge_gpu_service.py` — Edge GPU service for managing GPU operations
- `apps/coordinator-api/src/coordinator_api/contexts/marketplace/routers/marketplace_gpu.py` — Get pricing engine instance
- `Blockchain Node` exposes `GET /rpc/gpu/allocations/{gpu_id}` (operation `get_gpu_allocations_rpc_gpu_allocations__gpu_id__get`) — Query GPU allocations
- `Blockchain Node` exposes `GET /rpc/gpu/info/{gpu_id}` (operation `get_gpu_rpc_gpu_info__gpu_id__get`) — Query GPU registration
- `Blockchain Node` exposes `GET /rpc/edge/info/{node_id}` (operation `get_edge_node_rpc_edge_info__node_id__get`) — Query edge node registration
## Examples

- `GET /` (`list_gpus` in `apps/edge/src/aitbc_edge/routers/gpu.py`)
- `GET /{gpu_id}` (`get_gpu_listing` in `apps/edge/src/aitbc_edge/routers/gpu.py`)
- `DELETE /{gpu_id}` (`remove_gpu_listing` in `apps/edge/src/aitbc_edge/routers/gpu.py`)
- `POST /scan` (`scan_gpus` in `apps/edge/src/aitbc_edge/routers/gpu.py`)
- `GET /{gpu_id}/metrics` (`get_gpu_metrics` in `apps/edge/src/aitbc_edge/routers/gpu.py`)
- `GET /rpc/gpu/allocations/{gpu_id}` (`get_gpu_allocations_rpc_gpu_allocations__gpu_id__get`) on `Blockchain Node`
- `GET /rpc/gpu/info/{gpu_id}` (`get_gpu_rpc_gpu_info__gpu_id__get`) on `Blockchain Node`
- `GET /rpc/edge/info/{node_id}` (`get_edge_node_rpc_edge_info__node_id__get`) on `Blockchain Node`
## Operational Notes
- **Status / Release:** `✅` / `—`
- Requires GPU for model inference and training.
