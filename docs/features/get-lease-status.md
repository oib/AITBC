# Get Lease Status

Get lease status for a subscriber

- **Status**: ✅
- **Release**: —

## Implementation Details

- `apps/blockchain-node/src/aitbc_chain/lease_tracker.py` — Redis-based lease tracker for block subscription system.
- `apps/trading/src/trading_service/services/lease_tracker.py` — Manages offer-subscriber leases in Redis with in-memory fallback.
- API endpoint `GET /v1/exchange/payment-status/{payment_id}` implemented in `apps/trading/src/trading_service/routers/exchange_compat.py`
- API endpoint `GET /v1/trading/inter-chain/{trade_id}/status` implemented in `apps/trading/src/trading_service/routers/inter_chain.py`
- `Blockchain Node` exposes `GET /rpc/lease/{node_id}` (operation `lease_status_route_rpc_lease__node_id__get`) — Get lease status for a subscriber
- `Blockchain Node` exposes `GET /rpc/status` (operation `get_status_route_rpc_status_get`) — Get node status (alias for /info)
- `Blockchain Node` exposes `GET /rpc/consensus/status` (operation `consensus_status_route_rpc_consensus_status_get`) — Get consensus status

## Examples

- `GET /v1/exchange/payment-status/{payment_id}` (`get_exchange_payment_status` in `apps/trading/src/trading_service/routers/exchange_compat.py`)
- `GET /v1/trading/inter-chain/{trade_id}/status` (`get_inter_chain_trade_status` in `apps/trading/src/trading_service/routers/inter_chain.py`)
- `GET /v1/trading/offers/sync-status` (`get_offer_sync_status` in `apps/trading/src/trading_service/routers/offers.py`)
- `GET /v1/trading/offers/subscription-status` (`get_subscription_status` in `apps/trading/src/trading_service/routers/subscriptions.py`)
- `GET /status` (`get_sla_status` in `apps/pool-hub/src/poolhub/app/routers/sla.py`)
- `GET /rpc/lease/{node_id}` (`lease_status_route_rpc_lease__node_id__get`) on `Blockchain Node`
- `GET /rpc/status` (`get_status_route_rpc_status_get`) on `Blockchain Node`
- `GET /rpc/consensus/status` (`consensus_status_route_rpc_consensus_status_get`) on `Blockchain Node`

## Operational Notes

- **Status / Release:** `✅` / `—`
