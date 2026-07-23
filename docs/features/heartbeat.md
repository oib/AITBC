# Heartbeat

Extend subscription lease via heartbeat

- **Status**: ✅
- **Release**: —
## Implementation Details
- `aitbc/trading/subscription_client.py` — The base HTTP URL for the trading service.
- `apps/blockchain-node/src/aitbc_chain/rpc/subscription.py` — Subscription RPC endpoints for lease-based block push system.
- `apps/trading/src/trading_service/services/lease_tracker.py` — Manages offer-subscriber leases in Redis with in-memory fallback.
- `apps/blockchain-node/src/aitbc_chain/lease_tracker.py` — Redis-based lease tracker for block subscription system.
- `apps/blockchain-node/src/aitbc_chain/rpc/routers/subscription.py` — Subscription router.
- `Blockchain Node` exposes `POST /rpc/heartbeat` (operation `heartbeat_route_rpc_heartbeat_post`) — Extend subscription lease via heartbeat
- `Blockchain Node` exposes `POST /rpc/subscribe` (operation `register_subscription_route_rpc_subscribe_post`) — Register for block subscription with lease
- `Blockchain Node` exposes `GET /rpc/lease/{node_id}` (operation `lease_status_route_rpc_lease__node_id__get`) — Get lease status for a subscriber
## Examples

- `POST /v1/transactions` (`submit_transaction` in `apps/trading/src/trading_service/routers/transactions.py`)
- `GET /v1/transactions` (`get_transactions` in `apps/trading/src/trading_service/routers/transactions.py`)
- `GET /v1/blocks` (`get_blocks` in `apps/trading/src/trading_service/routers/transactions.py`)
- `GET /v1/explorer/blocks` (`get_blocks_v1` in `apps/trading/src/trading_service/routers/transactions.py`)
- `GET /api/v1/blocks` (`get_blocks_api` in `apps/trading/src/trading_service/routers/transactions.py`)
- `POST /rpc/heartbeat` (`heartbeat_route_rpc_heartbeat_post`) on `Blockchain Node`
- `POST /rpc/subscribe` (`register_subscription_route_rpc_subscribe_post`) on `Blockchain Node`
- `GET /rpc/lease/{node_id}` (`lease_status_route_rpc_lease__node_id__get`) on `Blockchain Node`
## Operational Notes
- Feature status is `✅` (release `—`). Add operational notes as details become available.
