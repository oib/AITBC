# Health Checks

Health check endpoints for all services

- **Status**: ✅
- **Release**: —
## Implementation Details
- `aitbc/health_checks.py` — Health check utilities for AITBC services Provides health check endpoints for all services
- `apps/agent-coordinator/src/agent_app/routers/health.py` — Health check endpoint
- `apps/coordinator-api/src/coordinator_api/contexts/multimodal/routers/multimodal_health.py` — Multi-Modal Agent Service Health Check Router Provides health monitoring for multi-modal processing ...
- `Blockchain Node` exposes `GET /rpc/bridge/health` (operation `bridge_health_route_rpc_bridge_health_get`) — Bridge health check
- `Blockchain Node` exposes `GET /health` (operation `health_health_get`) — Health check
- `Coordinator API` exposes `GET /v1/zk/health` (operation `health_check_v1_zk_health_get`) — ZK service health check
## Examples

- `GET /health` (`health_check` in `apps/coordinator-api/src/coordinator_api/contexts/zk_applications/routers/zk_proofs.py`)
- `GET /health` (`health_check` in `apps/coordinator-api/src/coordinator_api/contexts/ipfs/routers/ipfs.py`)
- `GET /oracle/health` (`health_check` in `apps/coordinator-api/src/coordinator_api/contexts/blockchain/routers/oracle.py`)
- `GET /health` (`analytics_health_check` in `apps/coordinator-api/src/coordinator_api/contexts/analytics/routers/analytics.py`)
- `GET /health` (`health_check` in `apps/agent-coordinator/src/agent_app/routers/health.py`)
- `GET /rpc/bridge/health` (`bridge_health_route_rpc_bridge_health_get`) on `Blockchain Node`
- `GET /health` (`health_health_get`) on `Blockchain Node`
- `GET /v1/zk/health` (`health_check_v1_zk_health_get`) on `Coordinator API`
## Operational Notes
- **Status / Release:** `✅` / `—`
