# Market Analytics

Get market analytics and performance metrics

- **Status**: ✅
- **Release**: —

## Implementation Details

- `apps/coordinator-api/src/coordinator_api/contexts/market/domain/global_market.py` — Global Market Domain Models Domain models for global market operations, multi-region suppo...
- `apps/coordinator-api/src/coordinator_api/contexts/analytics/domain/analytics.py` — Market Analytics Domain Models Implements SQLModel definitions for analytics, insights, and rep...
- `apps/coordinator-api/src/coordinator_api/contexts/analytics/services/analytics_service.py` — Service for market analytics operations.
- `Coordinator API` exposes `GET /v1/agent-performance/analytics/{agent_id}` (operation `get_performance_analytics_v1_agent_performance_analytics__agent_id__get`) — Get Performance Analytics
- `Market` exposes `GET /v1/market/analytics` (operation `get_analytics_v1_market_analytics_get`) — Get Analytics
- `Market` exposes `GET /v1/market/performance` (operation `get_market_performance_v1_market_performance_get`) — Get Market Performance

## Examples

- `GET /analytics/market-integration` (`get_market_integration_analytics` in `apps/coordinator-api/src/coordinator_api/contexts/market/routers/global_market_integration.py`) *(router defined but not mounted in `main.py` — 404s today)*
- `GET /analytics` (`get_market_analytics` in `apps/coordinator-api/src/coordinator_api/contexts/market/routers/global_market.py`)
- `GET /analytics/{agent_id}` (`get_performance_analytics` in `apps/coordinator-api/src/coordinator_api/contexts/agent_coordination/routers/agent_performance.py`)
- `GET /{gpu_id}/metrics` (`get_gpu_metrics` in `apps/edge/src/aitbc_edge/routers/gpu.py`)
- `GET /{metric_id}` (`get_metrics` in `apps/edge/src/aitbc_edge/routers/metrics.py`)
- `GET /v1/agent-performance/analytics/{agent_id}` (`get_performance_analytics_v1_agent_performance_analytics__agent_id__get`) on `Coordinator API`
- `GET /v1/market/analytics` (`get_analytics_v1_market_analytics_get`) on `Market`
- `GET /v1/market/performance` (`get_market_performance_v1_market_performance_get`) on `Market`

## Operational Notes

- **Status / Release:** `✅` / `—`
