# Register Subscription

Register for block subscription with lease

- **Status**: ✅
- **Release**: —
## Implementation Details
- `apps/blockchain-node/src/aitbc_chain/rpc/routers/subscription.py` — Subscription router.
- `aitbc/trading/subscription_client.py` — The base HTTP URL for the trading service.
- `apps/blockchain-node/src/aitbc_chain/rpc/subscription.py` — Subscription RPC endpoints for lease-based block push system.
- `apps/blockchain-node/src/aitbc_chain/subscription_client.py` — Subscription client for follower nodes to receive block pushes from hub.
- `apps/trading/src/trading_service/services/lease_tracker.py` — Manages offer-subscriber leases in Redis with in-memory fallback.
- `Blockchain Node` exposes `POST /rpc/subscribe` (operation `register_subscription_route_rpc_subscribe_post`) — Register for block subscription with lease
- `Blockchain Node` exposes `POST /rpc/heartbeat` (operation `heartbeat_route_rpc_heartbeat_post`) — Extend subscription lease via heartbeat
- `Blockchain Node` exposes `GET /rpc/lease/{node_id}` (operation `lease_status_route_rpc_lease__node_id__get`) — Get lease status for a subscriber
## Examples

- `POST /subscribe` (`register_subscription_route` in `apps/blockchain-node/src/aitbc_chain/rpc/routers/subscription.py`)
- `POST /requests` (`submit_compute_request` in `apps/edge/src/aitbc_edge/routers/serve.py`)
- `GET /requests` (`list_compute_requests` in `apps/edge/src/aitbc_edge/routers/serve.py`)
- `GET /requests/{request_id}` (`get_compute_request` in `apps/edge/src/aitbc_edge/routers/serve.py`)
- `POST /requests/{request_id}/cancel` (`cancel_compute_request` in `apps/edge/src/aitbc_edge/routers/serve.py`)
- `POST /rpc/subscribe` (`register_subscription_route_rpc_subscribe_post`) on `Blockchain Node`
- `POST /rpc/heartbeat` (`heartbeat_route_rpc_heartbeat_post`) on `Blockchain Node`
- `GET /rpc/lease/{node_id}` (`lease_status_route_rpc_lease__node_id__get`) on `Blockchain Node`
## Operational Notes
- **Status / Release:** `✅` / `—`
