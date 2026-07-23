# Performance Logging

Request performance timing middleware

- **Status**: ✅
- **Release**: —
## Implementation Details
- `aitbc/middleware/performance.py` — Performance logging middleware for tracking request timing
- `apps/agent-coordinator/src/agent_app/middleware.py`
- `aitbc/aitbc_logging.py` — AITBC Logging Module Centralized logging utilities for the AITBC project
- `aitbc/auth/middleware.py` — Custom authentication error.
- `Blockchain Node` exposes `POST /rpc/islands/bridge` (operation `request_bridge_route_rpc_islands_bridge_post`) — Request a bridge to another island
- `Blockchain Node` exposes `POST /rpc/faucet` (operation `faucet_request_route_rpc_faucet_post`) — Request test tokens from faucet
- `Coordinator API` exposes `POST /v1/islands/bridge` (operation `request_bridge_v1_islands_bridge_post`) — Request Bridge
## Examples

- `POST /join` (`join_island` in `apps/edge/src/aitbc_edge/routers/islands.py`)
- `POST /leave` (`leave_island` in `apps/edge/src/aitbc_edge/routers/islands.py`)
- `GET /` (`list_islands` in `apps/edge/src/aitbc_edge/routers/islands.py`)
- `GET /{island_id}` (`get_island` in `apps/edge/src/aitbc_edge/routers/islands.py`)
- `POST /bridge` (`request_bridge` in `apps/edge/src/aitbc_edge/routers/islands.py`)
- `POST /rpc/islands/bridge` (`request_bridge_route_rpc_islands_bridge_post`) on `Blockchain Node`
- `POST /rpc/faucet` (`faucet_request_route_rpc_faucet_post`) on `Blockchain Node`
- `POST /v1/islands/bridge` (`request_bridge_v1_islands_bridge_post`) on `Coordinator API`
## Operational Notes
- **Status / Release:** `✅` / `—`
- Provides unified entry point with authentication, rate limiting, and request forwarding.
