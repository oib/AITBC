# Payment Status

Get payment status

- **Status**: ✅
- **Release**: —

## Implementation Details

- `aitbc/crypto/payment_escrow.py` — Status of a payment escrow.
- `apps/coordinator-api/src/coordinator_api/contexts/payments/domain/payment.py` — Payment domain model
- API endpoint `GET /v1/exchange/payment-status/{payment_id}` implemented in `apps/trading/src/trading_service/routers/exchange_compat.py`
- API endpoint `GET /exchange/payment-status/{payment_id}` implemented in `apps/coordinator-api/src/coordinator_api/contexts/infrastructure/routers/exchange.py`
- API endpoint `GET /v1/trading/inter-chain/{trade_id}/status` implemented in `apps/trading/src/trading_service/routers/inter_chain.py`
- `Coordinator API` exposes `GET /v1/exchange/payment-status/{payment_id}` (operation `get_payment_status_v1_exchange_payment_status__payment_id__get`) — Get Payment Status
- `Openapi` exposes `GET /v1/exchange/payment-status/{payment_id}` (operation `get_payment_status_v1_exchange_payment_status__payment_id__get`) — Get Payment Status
- `Blockchain Node` exposes `GET /rpc/lease/{node_id}` (operation `lease_status_route_rpc_lease__node_id__get`) — Get lease status for a subscriber

## Examples

- `GET /v1/exchange/payment-status/{payment_id}` (`get_exchange_payment_status` in `apps/trading/src/trading_service/routers/exchange_compat.py`)
- `GET /exchange/payment-status/{payment_id}` (`get_payment_status` in `apps/coordinator-api/src/coordinator_api/contexts/infrastructure/routers/exchange.py`)
- `GET /v1/trading/inter-chain/{trade_id}/status` (`get_inter_chain_trade_status` in `apps/trading/src/trading_service/routers/inter_chain.py`)
- `GET /v1/trading/offers/sync-status` (`get_offer_sync_status` in `apps/trading/src/trading_service/routers/offers.py`)
- `GET /v1/trading/offers/subscription-status` (`get_subscription_status` in `apps/trading/src/trading_service/routers/subscriptions.py`)
- `GET /v1/exchange/payment-status/{payment_id}` (`get_payment_status_v1_exchange_payment_status__payment_id__get`) on `Coordinator API`
- `GET /v1/exchange/payment-status/{payment_id}` (`get_payment_status_v1_exchange_payment_status__payment_id__get`) on `Openapi`
- `GET /rpc/lease/{node_id}` (`lease_status_route_rpc_lease__node_id__get`) on `Blockchain Node`

## Operational Notes

- **Status / Release:** `✅` / `—`
