# Marketplace Analytics

Get marketplace analytics and performance metrics

- **Status**: ✅
- **Release**: —
## Implementation Details
- `apps/coordinator-api/src/coordinator_api/contexts/marketplace/domain/global_marketplace.py` — Global Marketplace Domain Models Domain models for global marketplace operations, multi-region suppo...
- `apps/coordinator-api/src/coordinator_api/contexts/analytics/domain/analytics.py` — Marketplace Analytics Domain Models Implements SQLModel definitions for analytics, insights, and rep...
- `apps/coordinator-api/src/coordinator_api/contexts/analytics/services/analytics_service.py` — Service for marketplace analytics operations.
- `Coordinator API` exposes `GET /v1/agent-performance/analytics/{agent_id}` (operation `get_performance_analytics_v1_agent_performance_analytics__agent_id__get`) — Get Performance Analytics
- `Marketplace` exposes `GET /v1/marketplace/analytics` (operation `get_analytics_v1_marketplace_analytics_get`) — Get Analytics
- `Marketplace` exposes `GET /v1/marketplace/performance` (operation `get_marketplace_performance_v1_marketplace_performance_get`) — Get Marketplace Performance
## Examples

- `GET /analytics/marketplace-integration` (`get_marketplace_integration_analytics` in `apps/coordinator-api/src/coordinator_api/contexts/marketplace/routers/global_marketplace_integration.py`)
- `GET /analytics` (`get_marketplace_analytics` in `apps/coordinator-api/src/coordinator_api/contexts/marketplace/routers/global_marketplace.py`)
- `GET /analytics/{agent_id}` (`get_performance_analytics` in `apps/coordinator-api/src/coordinator_api/contexts/agent_coordination/routers/agent_performance.py`)
- `GET /{gpu_id}/metrics` (`get_gpu_metrics` in `apps/edge/src/aitbc_edge/routers/gpu.py`)
- `GET /{metric_id}` (`get_metrics` in `apps/edge/src/aitbc_edge/routers/metrics.py`)
- `GET /v1/agent-performance/analytics/{agent_id}` (`get_performance_analytics_v1_agent_performance_analytics__agent_id__get`) on `Coordinator API`
- `GET /v1/marketplace/analytics` (`get_analytics_v1_marketplace_analytics_get`) on `Marketplace`
- `GET /v1/marketplace/performance` (`get_marketplace_performance_v1_marketplace_performance_get`) on `Marketplace`
## Operational Notes
- **Status / Release:** `✅` / `—`
