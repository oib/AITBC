# GPU Metrics

Get GPU metrics

- **Status**: ✅
- **Release**: —

## Implementation Details

- `apps/gpu/src/gpu_service/services/edge_gpu_service.py` — Edge GPU service for managing GPU operations
- `apps/edge/src/aitbc_edge/clients/gpu_service.py` — GPU service client for Edge API Service
- `apps/edge/src/aitbc_edge/services/gpu_service.py` — GPU service for Edge API Service
- `Coordinator API` exposes `GET /v1/edge-gpu/metrics/{gpu_id}` (operation `get_gpu_metrics_v1_edge_gpu_metrics__gpu_id__get`) — Get Gpu Metrics
- `Coordinator API` exposes `GET /v1/edge-gpu/metrics` (operation `get_all_metrics_v1_edge_gpu_metrics_get`) — Get All Metrics
- `Openapi` exposes `GET /v1/edge-gpu/metrics/{gpu_id}` (operation `get_gpu_metrics_v1_edge_gpu_metrics__gpu_id__get`) — Get Gpu Metrics

## Examples

- `GET /{gpu_id}/metrics` (`get_gpu_metrics` in `apps/edge/src/aitbc_edge/routers/gpu.py`)
- `GET /metrics/{gpu_id}` (`get_gpu_metrics` in `apps/coordinator-api/src/coordinator_api/contexts/edge_gpu/routers/edge_gpu.py`)
- `GET /{gpu_id}` (`get_gpu_listing` in `apps/edge/src/aitbc_edge/routers/gpu.py`)
- `GET /{metric_id}` (`get_metrics` in `apps/edge/src/aitbc_edge/routers/metrics.py`)
- `GET /metrics/{miner_id}` (`get_miner_sla_metrics` in `apps/pool-hub/src/poolhub/app/routers/sla.py`)
- `GET /v1/edge-gpu/metrics/{gpu_id}` (`get_gpu_metrics_v1_edge_gpu_metrics__gpu_id__get`) on `Coordinator API`
- `GET /v1/edge-gpu/metrics` (`get_all_metrics_v1_edge_gpu_metrics_get`) on `Coordinator API`
- `GET /v1/edge-gpu/metrics/{gpu_id}` (`get_gpu_metrics_v1_edge_gpu_metrics__gpu_id__get`) on `Openapi`

## Operational Notes

- **Status / Release:** `✅` / `—`
- Requires GPU for model inference and training.
