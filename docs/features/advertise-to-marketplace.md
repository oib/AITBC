# Advertise to Marketplace

Advertise edge GPU capabilities to marketplace

- **Status**: ✅
- **Release**: v0.6.6
## Implementation Details
- `apps/marketplace/src/marketplace_service/domain/marketplace.py` — Software service registry for marketplace (migrated from plugin service)
- `apps/edge/src/aitbc_edge/services/gpu_service.py` — GPU service for Edge API Service
- `apps/edge/src/aitbc_edge/routers/gpu.py` — GPU operations router for Edge API Service
- `apps/gpu/src/gpu_service/services/edge_gpu_service.py` — Edge GPU service for managing GPU operations
- `apps/gpu/src/gpu_service/domain/gpu_marketplace.py` — Persistent SQLModel tables for the GPU marketplace.
- `Marketplace` exposes `POST /v1/marketplace/edge-advertise` (operation `edge_advertise_v1_marketplace_edge_advertise_post`) — Edge Advertise
- `Marketplace` exposes `GET /v1/marketplace/edge-advertise` (operation `list_edge_nodes_v1_marketplace_edge_advertise_get`) — List Edge Nodes
- `Blockchain Node` exposes `POST /rpc/edge/register` (operation `register_edge_node_rpc_edge_register_post`) — Register edge node on-chain
## Examples

- `POST /advertise` (`advertise_to_marketplace` in `apps/edge/src/aitbc_edge/routers/gpu.py`)
- `POST /marketplace/gpu/register` (`register_gpu` in `apps/coordinator-api/src/coordinator_api/contexts/marketplace/routers/marketplace_gpu.py`)
- `GET /marketplace/gpu/list` (`list_gpus` in `apps/coordinator-api/src/coordinator_api/contexts/marketplace/routers/marketplace_gpu.py`)
- `GET /marketplace/gpu/{gpu_id}` (`get_gpu_details` in `apps/coordinator-api/src/coordinator_api/contexts/marketplace/routers/marketplace_gpu.py`)
- `POST /marketplace/gpu/purchase` (`buy_gpu` in `apps/coordinator-api/src/coordinator_api/contexts/marketplace/routers/marketplace_gpu.py`)
- `POST /v1/marketplace/edge-advertise` (`edge_advertise_v1_marketplace_edge_advertise_post`) on `Marketplace`
- `GET /v1/marketplace/edge-advertise` (`list_edge_nodes_v1_marketplace_edge_advertise_get`) on `Marketplace`
- `POST /rpc/edge/register` (`register_edge_node_rpc_edge_register_post`) on `Blockchain Node`
## Operational Notes
- **Status / Release:** `✅` / `v0.6.6`
