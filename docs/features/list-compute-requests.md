# List Compute Requests

List compute requests with filters

- **Status**: ✅
- **Release**: —

## Implementation Details

- `apps/agent-coordinator/src/agent_app/routers/coin_requests.py` — Request to execute an approved coin request forwarded from a follower node.
- API endpoint `GET /requests` implemented in `apps/edge/src/aitbc_edge/routers/serve.py`
- API endpoint `POST /requests` implemented in `apps/edge/src/aitbc_edge/routers/serve.py`
- API endpoint `GET /requests/{request_id}` implemented in `apps/edge/src/aitbc_edge/routers/serve.py`
- API endpoint `POST /requests/{request_id}/cancel` implemented in `apps/edge/src/aitbc_edge/routers/serve.py`
- `Coordinator API` exposes `GET /v1/trading/requests` (operation `list_trade_requests_v1_trading_requests_get`) — List Trade Requests
- `Blockchain Node` exposes `GET /rpc/contracts` (operation `list_contracts_route_rpc_contracts_get`) — List deployed contracts
- `Blockchain Node` exposes `GET /rpc/islands` (operation `list_islands_route_rpc_islands_get`) — List all islands

## Examples

- `GET /requests` (`list_compute_requests` in `apps/edge/src/aitbc_edge/routers/serve.py`)
- `POST /requests` (`submit_compute_request` in `apps/edge/src/aitbc_edge/routers/serve.py`)
- `GET /requests/{request_id}` (`get_compute_request` in `apps/edge/src/aitbc_edge/routers/serve.py`)
- `POST /requests/{request_id}/cancel` (`cancel_compute_request` in `apps/edge/src/aitbc_edge/routers/serve.py`)
- `GET /requests/{request_id}/result` (`get_compute_result` in `apps/edge/src/aitbc_edge/routers/serve.py`)
- `GET /v1/trading/requests` (`list_trade_requests_v1_trading_requests_get`) on `Coordinator API`
- `GET /rpc/contracts` (`list_contracts_route_rpc_contracts_get`) on `Blockchain Node`
- `GET /rpc/islands` (`list_islands_route_rpc_islands_get`) on `Blockchain Node`

## Operational Notes

- **Status / Release:** `✅` / `—`
