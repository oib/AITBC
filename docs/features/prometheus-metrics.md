# Prometheus Metrics

Prometheus metrics endpoints

- **Status**: ✅
- **Release**: —
## Implementation Details
- `apps/blockchain-node/src/aitbc_chain/observability/consensus_metrics.py` — Register Prometheus metrics (idempotent).
- `apps/blockchain-event-bridge/src/blockchain_event_bridge/metrics.py` — Prometheus metrics for blockchain event bridge.
- `aitbc/middleware/prometheus_metrics.py` — Middleware to collect Prometheus metrics for all HTTP requests.
- `apps/blockchain-node/src/aitbc_chain/metrics.py`
- `Blockchain Node` exposes `GET /metrics` (operation `metrics_metrics_get`) — Prometheus metrics
- `Coordinator API` exposes `GET /v1/monitoring/dashboard/metrics` (operation `system_metrics_v1_monitoring_dashboard_metrics_get`) — System Metrics
- `Coordinator API` exposes `GET /v1/agents/{agent_wallet}/metrics` (operation `get_agent_metrics_v1_agents__agent_wallet__metrics_get`) — Get Agent Metrics
## Examples

- `GET /metrics` (`get_prometheus_metrics` in `apps/agent-coordinator/src/agent_app/routers/monitoring.py`)
- `GET /` (`list_gpus` in `apps/edge/src/aitbc_edge/routers/gpu.py`)
- `GET /{gpu_id}` (`get_gpu_listing` in `apps/edge/src/aitbc_edge/routers/gpu.py`)
- `DELETE /{gpu_id}` (`remove_gpu_listing` in `apps/edge/src/aitbc_edge/routers/gpu.py`)
- `POST /scan` (`scan_gpus` in `apps/edge/src/aitbc_edge/routers/gpu.py`)
- `GET /metrics` (`metrics_metrics_get`) on `Blockchain Node`
- `GET /v1/monitoring/dashboard/metrics` (`system_metrics_v1_monitoring_dashboard_metrics_get`) on `Coordinator API`
- `GET /v1/agents/{agent_wallet}/metrics` (`get_agent_metrics_v1_agents__agent_wallet__metrics_get`) on `Coordinator API`
## Operational Notes
- **Status / Release:** `✅` / `—`
