# Exchange Rates

Get exchange rates

- **Status**: ✅
- **Release**: —

## Implementation Details

- `apps/coordinator-api/src/coordinator_api/contexts/infrastructure/routers/exchange.py` — ETH Exchange Router for AITBC v0.5.1: Payment state migrated from module-global dict to RedisStateMa...
- `apps/trading/src/trading_service/routers/exchange_compat.py` — Migrated exchange payment endpoints (compatibility layer).
- `apps/exchange/simple_exchange/handlers/exchange.py` — Convert a database row to an order dict with Decimal monetary values.
- `Coordinator API` exposes `GET /v1/exchange/rates` (operation `get_exchange_rates_v1_exchange_rates_get`) — Get Exchange Rates
- `Openapi` exposes `GET /v1/exchange/rates` (operation `get_exchange_rates_v1_exchange_rates_get`) — Get Exchange Rates
- `Coordinator API` exposes `GET /v1/exchange/payment-status/{payment_id}` (operation `get_payment_status_v1_exchange_payment_status__payment_id__get`) — Get Payment Status

## Examples

- `GET /v1/exchange/rates` (`get_exchange_rates` in `apps/trading/src/trading_service/routers/exchange_compat.py`)
- `GET /exchange/rates` (`get_exchange_rates` in `apps/coordinator-api/src/coordinator_api/contexts/infrastructure/routers/exchange.py`)
- `GET /v1/exchange/payment-status/{payment_id}` (`get_exchange_payment_status` in `apps/trading/src/trading_service/routers/exchange_compat.py`)
- `GET /v1/exchange/market-stats` (`get_market_stats` in `apps/trading/src/trading_service/routers/exchange_compat.py`)
- `GET /v1/exchange/wallet/balance` (`get_exchange_wallet_balance` in `apps/trading/src/trading_service/routers/exchange_compat.py`)
- `GET /v1/exchange/rates` (`get_exchange_rates_v1_exchange_rates_get`) on `Coordinator API`
- `GET /v1/exchange/rates` (`get_exchange_rates_v1_exchange_rates_get`) on `Openapi`
- `GET /v1/exchange/payment-status/{payment_id}` (`get_payment_status_v1_exchange_payment_status__payment_id__get`) on `Coordinator API`

## Operational Notes

- **Status / Release:** `✅` / `—`
