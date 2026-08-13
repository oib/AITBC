# Wallet Balance/Info

Get exchange wallet balance and info

- **Status**: ✅
- **Release**: —

## Implementation Details

- `apps/trading/src/trading_service/routers/exchange_compat.py` — Migrated exchange payment endpoints (compatibility layer).
- `apps/coordinator-api/src/coordinator_api/agent_identity/wallet_adapter_enhanced.py` — Enhanced Multi-Chain Wallet Adapter Production-ready wallet adapter for cross-chain operations with ...
- `apps/exchange/simple_exchange/handlers/exchange.py` — Convert a database row to an order dict with Decimal monetary values.
- `apps/coordinator-api/src/coordinator_api/contexts/wallet/services/wallet_service.py` — Multi-Chain Wallet Service Service for managing agent wallets across multiple blockchain networks.
- `Openapi` exposes `GET /v1/exchange/wallet/balance` (operation `get_wallet_balance_api_v1_exchange_wallet_balance_get`) — Get Wallet Balance Api
- `Openapi` exposes `GET /v1/exchange/wallet/info` (operation `get_wallet_info_api_v1_exchange_wallet_info_get`) — Get Wallet Info Api
- `Coordinator API` exposes `GET /v1/cross-chain/wallets/{wallet_address}/balance` (operation `get_wallet_balance_v1_cross_chain_wallets__wallet_address__balance_get`) — Get Wallet Balance

## Examples

- `GET /v1/exchange/wallet/balance` (`get_exchange_wallet_balance` in `apps/trading/src/trading_service/routers/exchange_compat.py`)
- `GET /v1/exchange/wallet/info` (`get_exchange_wallet_info` in `apps/trading/src/trading_service/routers/exchange_compat.py`)
- `GET /wallets/{wallet_address}/balance` (`get_wallet_balance` in `apps/coordinator-api/src/coordinator_api/contexts/cross_chain/routers/cross_chain_integration.py`)
- `GET /identities/{agent_id}/wallets/{chain_id}/balance` (`get_wallet_balance` in `apps/coordinator-api/src/coordinator_api/contexts/agent_identity/routers/agent_identity.py`)
- `GET /v1/exchange/payment-status/{payment_id}` (`get_exchange_payment_status` in `apps/trading/src/trading_service/routers/exchange_compat.py`)
- `GET /v1/exchange/wallet/balance` (`get_wallet_balance_api_v1_exchange_wallet_balance_get`) on `Openapi`
- `GET /v1/exchange/wallet/info` (`get_wallet_info_api_v1_exchange_wallet_info_get`) on `Openapi`
- `GET /v1/cross-chain/wallets/{wallet_address}/balance` (`get_wallet_balance_v1_cross_chain_wallets__wallet_address__balance_get`) on `Coordinator API`

## Operational Notes

- **Status / Release:** `✅` / `—`
