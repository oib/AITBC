# Edge Health

Get edge node health status

- **Status**: ✅
- **Release**: v0.6.6
## Implementation Details
- `apps/blockchain-node/src/aitbc_chain/network/health.py` — Peer Health Monitoring Service Monitors peer liveness and performance metrics
- `apps/gpu/src/gpu_service/services/edge_gpu_service.py` — Edge GPU service for managing GPU operations
- `Marketplace` exposes `GET /v1/marketplace/edge/{node_id}/health` (operation `get_edge_health_v1_marketplace_edge__node_id__health_get`) — Get Edge Health
- `Blockchain Node` exposes `GET /rpc/lease/{node_id}` (operation `lease_status_route_rpc_lease__node_id__get`) — Get lease status for a subscriber
- `Blockchain Node` exposes `GET /rpc/status` (operation `get_status_route_rpc_status_get`) — Get node status (alias for /info)
## Examples

- `GET /v1/exchange/payment-status/{payment_id}` (`get_exchange_payment_status` in `apps/trading/src/trading_service/routers/exchange_compat.py`)
- `GET /v1/trading/chains/{chain_id}/health` (`get_chain_health` in `apps/trading/src/trading_service/routers/inter_chain.py`)
- `GET /v1/trading/inter-chain/{trade_id}/status` (`get_inter_chain_trade_status` in `apps/trading/src/trading_service/routers/inter_chain.py`)
- `GET /v1/trading/offers/sync-status` (`get_offer_sync_status` in `apps/trading/src/trading_service/routers/offers.py`)
- `GET /v1/trading/offers/subscription-status` (`get_subscription_status` in `apps/trading/src/trading_service/routers/subscriptions.py`)
- `GET /v1/marketplace/edge/{node_id}/health` (`get_edge_health_v1_marketplace_edge__node_id__health_get`) on `Marketplace`
- `GET /rpc/lease/{node_id}` (`lease_status_route_rpc_lease__node_id__get`) on `Blockchain Node`
- `GET /rpc/status` (`get_status_route_rpc_status_get`) on `Blockchain Node`
## Operational Notes
- **Status / Release:** `✅` / `v0.6.6`
- Handles task distribution, result collection, and edge-local caching.
