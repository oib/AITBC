# Coordinator Heartbeat

Periodic health reporting to agent-coordinator

- **Status**: ✅
- **Release**: v0.6.6

## Implementation Details

- `apps/agent-coordinator/src/agent_app/routing/agent_discovery.py` — Agent Discovery and Registration System for AITBC Agent Coordination
- `apps/coordinator-api/src/coordinator_api/contexts/agent_coordination/routers/agent_messaging.py` — Request to register agent
- `Coordinator API` exposes `GET /v1/agent-identity/registry/health` (operation `get_registry_health_v1_agent_identity_registry_health_get`) — Get Registry Health
- `Openapi` exposes `GET /v1/agent-identity/registry/health` (operation `get_registry_health_v1_agent_identity_registry_health_get`) — Get Registry Health
- `Blockchain Node` exposes `GET /rpc/contracts/messaging/agents/{agent_id}/reputation` (operation `get_agent_reputation_route_rpc_contracts_messaging_agents__agent_id__reputation_get`) — Get agent reputation

## Examples

- `POST /agents/{agent_id}/heartbeat` (`heartbeat` in `apps/coordinator-api/src/coordinator_api/contexts/agent_coordination/routers/agent_messaging.py`)
- `GET /health` (`agent_health` in `apps/coordinator-api/src/coordinator_api/contexts/agent_coordination/routers/agent_messaging.py`)
- `POST /agents/{agent_id}/heartbeat` (`agent_heartbeat` in `apps/agent-coordinator/src/agent_app/routers/agents.py`)
- `GET /health` (`health` in `apps/trading/src/trading_service/routers/system.py`)
- `GET /ready` (`ready` in `apps/trading/src/trading_service/routers/system.py`)
- `GET /v1/agent-identity/registry/health` (`get_registry_health_v1_agent_identity_registry_health_get`) on `Coordinator API`
- `GET /v1/agent-identity/registry/health` (`get_registry_health_v1_agent_identity_registry_health_get`) on `Openapi`
- `GET /rpc/contracts/messaging/agents/{agent_id}/reputation` (`get_agent_reputation_route_rpc_contracts_messaging_agents__agent_id__reputation_get`) on `Blockchain Node`

## Operational Notes

- **Status / Release:** `✅` / `v0.6.6`
- Handles agent discovery, load balancing, and real-time messaging between agents.
- **Prerequisites**: Requires [v0.6.5](../v0.6/v0.6.5_change.log) (Agent Coordination — task assignment uses agent coordination), [v0.6.3](../v0.6/v0.6.3_change.log) (Multi...
