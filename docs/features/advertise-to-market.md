# Advertise to Market

Advertise edge GPU capabilities to market

- **Status**: ✅
- **Release**: v0.6.6

## Implementation Details

- `apps/market/src/market_service/domain/market.py` — Software service registry for market (migrated from plugin service)
- `apps/edge/src/aitbc_edge/services/gpu_service.py` — GPU service for Edge API Service
- `apps/edge/src/aitbc_edge/routers/gpu.py` — GPU operations router for Edge API Service
- `apps/gpu/src/gpu_service/services/edge_gpu_service.py` — Edge GPU service for managing GPU operations
- `apps/gpu/src/gpu_service/domain/gpu_market.py` — Persistent SQLModel tables for the GPU market.
- `Market` exposes `POST /v1/market/edge-advertise` (operation `edge_advertise_v1_market_edge_advertise_post`) — Edge Advertise
- `Market` exposes `GET /v1/market/edge-advertise` (operation `list_edge_nodes_v1_market_edge_advertise_get`) — List Edge Nodes
- `Blockchain Node` exposes `POST /rpc/edge/register` (operation `register_edge_node_rpc_edge_register_post`) — Register edge node on-chain

## Examples

- `POST /advertise` (`advertise_to_market` in `apps/edge/src/aitbc_edge/routers/gpu.py`)
- `POST /market/gpu/register` (`register_gpu` in `apps/coordinator-api/src/coordinator_api/contexts/market/routers/market_gpu.py`)
- `GET /market/gpu/list` (`list_gpus` in `apps/coordinator-api/src/coordinator_api/contexts/market/routers/market_gpu.py`)
- `GET /market/gpu/{gpu_id}` (`get_gpu_details` in `apps/coordinator-api/src/coordinator_api/contexts/market/routers/market_gpu.py`)
- `POST /market/gpu/purchase` (`buy_gpu` in `apps/coordinator-api/src/coordinator_api/contexts/market/routers/market_gpu.py`)
- `POST /v1/market/edge-advertise` (`edge_advertise_v1_market_edge_advertise_post`) on `Market`
- `GET /v1/market/edge-advertise` (`list_edge_nodes_v1_market_edge_advertise_get`) on `Market`
- `POST /rpc/edge/register` (`register_edge_node_rpc_edge_register_post`) on `Blockchain Node`

## Operational Notes

- **Status / Release:** `✅` / `v0.6.6`
