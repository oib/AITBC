# cross_chain

Cross-chain integration — bridging assets and state across blockchains.

## Domain Models

- None (stub)

## Routes

- POST /wallets/create
- GET /wallets/{wallet_address}/balance
- POST /wallets/{wallet_address}/transactions
- GET /wallets/{wallet_address}/transactions
- POST /wallets/{wallet_address}/sign
- POST /wallets/verify-signature
- POST /bridge/create-request
- GET /bridge/request/{bridge_request_id}
- POST /bridge/request/{bridge_request_id}/cancel
- GET /bridge/statistics
- GET /bridge/liquidity-pools
- POST /transactions/submit
- GET /transactions/history
- GET /transactions/statistics
- POST /transactions/optimize-routing
- GET /chains/supported
- GET /chains/{chain_id}/info
- GET /health
- GET /config
- GET /bridge/whitelist
- POST /bridge/whitelist/add

## Services

- None (stub)
