# agent_identity

Agent identity registry — creation, cross-chain mapping, wallet management, and reputation sync.

## Domain Models

- agent_identity.py

## Routes

- POST /identities
- GET /identities/{agent_id}
- PUT /identities/{agent_id}
- POST /identities/{agent_id}/deactivate
- POST /identities/{agent_id}/cross-chain/register
- GET /identities/{agent_id}/cross-chain/mapping
- PUT /identities/{agent_id}/cross-chain/{chain_id}
- POST /identities/{agent_id}/cross-chain/{chain_id}/verify
- POST /identities/{agent_id}/migrate
- POST /identities/{agent_id}/wallets
- GET /identities/{agent_id}/wallets/{chain_id}/balance
- POST /identities/{agent_id}/wallets/{chain_id}/transactions
- GET /identities/{agent_id}/wallets/{chain_id}/transactions
- GET /identities/{agent_id}/wallets
- POST /identities/{agent_id}/wallets/{chain_id}/export
- DELETE /identities/{agent_id}/wallets/{chain_id}
- POST /identities/{agent_id}/wallets/{chain_id}/sign
- GET /identities/search
- POST /identities/{agent_id}/sync-reputation
- GET /registry/health
- GET /registry/statistics
- GET /chains/supported
- POST /identities/{agent_id}/export
- POST /identities/import
- POST /registry/cleanup-expired
- POST /identities/batch-verify
- GET /identities/{agent_id}/resolve/{chain_id}
- GET /address/{chain_address}/resolve/{chain_id}

## Services

- None (stub)
