# Get Compute Request

Get a specific compute request

- **Status**: ✅
- **Release**: —
## Implementation Details
- `aitbc/middleware/request_id.py` — Request ID correlation middleware for structured logging
- `aitbc/models/coin_request.py` — Database schema for coin requests. Moved from hermes_service.storage.schema in v0.5.9 §1 to provide ...
- API endpoint `GET /requests/{request_id}` implemented in `apps/edge/src/aitbc_edge/routers/serve.py`
- API endpoint `GET /requests/{request_id}/result` implemented in `apps/edge/src/aitbc_edge/routers/serve.py`
- `Coordinator API` exposes `GET /v1/cross-chain/bridge/request/{bridge_request_id}` (operation `get_bridge_request_status_v1_cross_chain_bridge_request__bridge_request_id__get`) — Get Bridge Request Status
- `Coordinator API` exposes `GET /v1/trading/requests/{request_id}` (operation `get_trade_request_v1_trading_requests__request_id__get`) — Get Trade Request
- `Coordinator API` exposes `GET /v1/trading/requests/{request_id}/matches` (operation `get_trade_matches_v1_trading_requests__request_id__matches_get`) — Get Trade Matches
## Examples

- `GET /requests/{request_id}` (`get_compute_request` in `apps/edge/src/aitbc_edge/routers/serve.py`)
- `GET /requests/{request_id}/result` (`get_compute_result` in `apps/edge/src/aitbc_edge/routers/serve.py`)
- `POST /requests` (`submit_compute_request` in `apps/edge/src/aitbc_edge/routers/serve.py`)
- `GET /requests` (`list_compute_requests` in `apps/edge/src/aitbc_edge/routers/serve.py`)
- `POST /requests/{request_id}/cancel` (`cancel_compute_request` in `apps/edge/src/aitbc_edge/routers/serve.py`)
- `GET /v1/cross-chain/bridge/request/{bridge_request_id}` (`get_bridge_request_status_v1_cross_chain_bridge_request__bridge_request_id__get`) on `Coordinator API`
- `GET /v1/trading/requests/{request_id}` (`get_trade_request_v1_trading_requests__request_id__get`) on `Coordinator API`
- `GET /v1/trading/requests/{request_id}/matches` (`get_trade_matches_v1_trading_requests__request_id__matches_get`) on `Coordinator API`
## Operational Notes
- **Status / Release:** `✅` / `—`
- Provides unified entry point with authentication, rate limiting, and request forwarding.
