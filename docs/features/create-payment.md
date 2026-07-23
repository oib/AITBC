# Create Payment

Create exchange payment

- **Status**: ✅
- **Release**: —
## Implementation Details
- `apps/coordinator-api/src/coordinator_api/contexts/infrastructure/routers/exchange.py` — ETH Exchange Router for AITBC v0.5.1: Payment state migrated from module-global dict to RedisStateMa...
- `apps/trading/src/trading_service/routers/exchange_compat.py` — Migrated exchange payment endpoints (compatibility layer).
- `aitbc/crypto/payment_escrow.py` — Status of a payment escrow.
- `Coordinator API` exposes `POST /v1/exchange/create-payment` (operation `create_payment_v1_exchange_create_payment_post`) — Create Payment
- `Openapi` exposes `POST /v1/exchange/create-payment` (operation `create_payment_v1_exchange_create_payment_post`) — Create Payment
- `Coordinator API` exposes `POST /v1/payments` (operation `create_payment_v1_payments_post`) — Create payment for a job
## Examples

- `POST /v1/exchange/create-payment` (`create_exchange_payment` in `apps/trading/src/trading_service/routers/exchange_compat.py`)
- `POST /exchange/create-payment` (`create_payment` in `apps/coordinator-api/src/coordinator_api/contexts/infrastructure/routers/exchange.py`)
- `GET /v1/exchange/payment-status/{payment_id}` (`get_exchange_payment_status` in `apps/trading/src/trading_service/routers/exchange_compat.py`)
- `POST /v1/exchange/confirm-payment/{payment_id}` (`confirm_exchange_payment` in `apps/trading/src/trading_service/routers/exchange_compat.py`)
- `POST /payments` (`create_payment` in `apps/coordinator-api/src/coordinator_api/contexts/payments/routers/payments.py`)
- `POST /v1/exchange/create-payment` (`create_payment_v1_exchange_create_payment_post`) on `Coordinator API`
- `POST /v1/exchange/create-payment` (`create_payment_v1_exchange_create_payment_post`) on `Openapi`
- `POST /v1/payments` (`create_payment_v1_payments_post`) on `Coordinator API`
## Operational Notes
- **Status / Release:** `✅` / `—`
