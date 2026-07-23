# Match Request

Match a compute request to best GPU offer (price-time priority)

- **Status**: ✅
- **Release**: v0.6.6
## Implementation Details
- `apps/trading/src/trading_service/services/offer_sync_service.py` — Service for synchronizing offers across AITBC chains.
- `aitbc/trading/offer_types.py` — from __future__ import annotations from dataclasses import dataclass, field from enum import StrEnum...
- `apps/coordinator-api/src/coordinator_api/contexts/marketplace/routers/marketplace_gpu.py` — Get pricing engine instance
- `Marketplace` exposes `POST /v1/marketplace/match` (operation `match_request_v1_marketplace_match_post`) — Match Request
- `Blockchain Node` exposes `POST /rpc/islands/bridge` (operation `request_bridge_route_rpc_islands_bridge_post`) — Request a bridge to another island
- `Blockchain Node` exposes `POST /rpc/faucet` (operation `faucet_request_route_rpc_faucet_post`) — Request test tokens from faucet
## Examples

- `POST /requests` (`submit_compute_request` in `apps/edge/src/aitbc_edge/routers/serve.py`)
- `GET /requests` (`list_compute_requests` in `apps/edge/src/aitbc_edge/routers/serve.py`)
- `GET /requests/{request_id}` (`get_compute_request` in `apps/edge/src/aitbc_edge/routers/serve.py`)
- `POST /requests/{request_id}/cancel` (`cancel_compute_request` in `apps/edge/src/aitbc_edge/routers/serve.py`)
- `GET /requests/{request_id}/result` (`get_compute_result` in `apps/edge/src/aitbc_edge/routers/serve.py`)
- `POST /v1/marketplace/match` (`match_request_v1_marketplace_match_post`) on `Marketplace`
- `POST /rpc/islands/bridge` (`request_bridge_route_rpc_islands_bridge_post`) on `Blockchain Node`
- `POST /rpc/faucet` (`faucet_request_route_rpc_faucet_post`) on `Blockchain Node`
## Operational Notes
- **Status / Release:** `✅` / `v0.6.6`
- Handles agent discovery, load balancing, and real-time messaging between agents.
- Provides unified entry point with authentication, rate limiting, and request forwarding.
