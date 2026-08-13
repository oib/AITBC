# Get GPU Listing

Get GPU listing details by ID

- **Status**: ✅
- **Release**: —

## Implementation Details

- `apps/edge/src/aitbc_edge/services/gpu_service.py` — GPU service for Edge API Service
- `apps/coordinator-api/src/coordinator_api/contexts/marketplace/routers/marketplace_gpu.py` — Get pricing engine instance
- `apps/edge/src/aitbc_edge/routers/gpu.py` — GPU operations router for Edge API Service
- `apps/gpu/src/gpu_service/services/edge_gpu_service.py` — Edge GPU service for managing GPU operations
- `Coordinator API` exposes `GET /v1/marketplace/gpu/{gpu_id}` (operation `get_gpu_details_v1_marketplace_gpu__gpu_id__get`) — Get Gpu Details
- `Openapi` exposes `GET /v1/marketplace/gpu/{gpu_id}` (operation `get_gpu_details_v1_marketplace_gpu__gpu_id__get`) — Get Gpu Details
- `Blockchain Node` exposes `GET /rpc/disputes/{dispute_id}` (operation `get_dispute_route_rpc_disputes__dispute_id__get`) — Get dispute details

## Examples

- `GET /{gpu_id}` (`get_gpu_listing` in `apps/edge/src/aitbc_edge/routers/gpu.py`)
- `GET /marketplace/gpu/{gpu_id}` (`get_gpu_details` in `apps/coordinator-api/src/coordinator_api/contexts/marketplace/routers/marketplace_gpu.py`)
- `DELETE /{gpu_id}` (`remove_gpu_listing` in `apps/edge/src/aitbc_edge/routers/gpu.py`)
- `GET /{gpu_id}/metrics` (`get_gpu_metrics` in `apps/edge/src/aitbc_edge/routers/gpu.py`)
- `GET /offers/{offer_id}/cross-chain-details` (`get_cross_chain_offer_details` in `apps/coordinator-api/src/coordinator_api/contexts/marketplace/routers/global_marketplace_integration.py`)
- `GET /v1/marketplace/gpu/{gpu_id}` (`get_gpu_details_v1_marketplace_gpu__gpu_id__get`) on `Coordinator API`
- `GET /v1/marketplace/gpu/{gpu_id}` (`get_gpu_details_v1_marketplace_gpu__gpu_id__get`) on `Openapi`
- `GET /rpc/disputes/{dispute_id}` (`get_dispute_route_rpc_disputes__dispute_id__get`) on `Blockchain Node`

## Operational Notes

- **Status / Release:** `✅` / `—`
- Provides listing, matching, pricing, and settlement for marketplace participants.
