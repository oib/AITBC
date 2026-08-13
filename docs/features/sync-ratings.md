# Sync Ratings

Sync ratings to blockchain

- **Status**: ✅
- **Release**: —

## Implementation Details

- `apps/pool-hub/src/poolhub/clients/blockchain.py` — Return the exact bytes that are hashed and signed for a transaction.
- `apps/coordinator-api/src/coordinator_api/contexts/blockchain/routers/blockchain.py` — Get blockchain status.
- `apps/blockchain-node/scripts/blockchain_simple.py` — Blockchain Node Service for AITBC Production
- `apps/edge/src/aitbc_edge/clients/blockchain_rpc.py` — Blockchain RPC client for Edge API Service
- `Coordinator API` exposes `GET /v1/sync-status` (operation `blockchain_sync_status_v1_sync_status_get`) — Blockchain Sync Status
- `Marketplace` exposes `POST /v1/marketplace/ratings/sync` (operation `sync_ratings_v1_marketplace_ratings_sync_post`) — Sync Ratings
- `Openapi` exposes `GET /v1/sync-status` (operation `blockchain_sync_status_v1_sync_status_get`) — Blockchain Sync Status

## Examples

- `GET /sync-status` (`blockchain_sync_status` in `apps/coordinator-api/src/coordinator_api/contexts/blockchain/routers/blockchain.py`)
- `POST /join` (`join_island` in `apps/edge/src/aitbc_edge/routers/islands.py`)
- `POST /leave` (`leave_island` in `apps/edge/src/aitbc_edge/routers/islands.py`)
- `GET /` (`list_islands` in `apps/edge/src/aitbc_edge/routers/islands.py`)
- `GET /{island_id}` (`get_island` in `apps/edge/src/aitbc_edge/routers/islands.py`)
- `GET /v1/sync-status` (`blockchain_sync_status_v1_sync_status_get`) on `Coordinator API`
- `POST /v1/marketplace/ratings/sync` (`sync_ratings_v1_marketplace_ratings_sync_post`) on `Marketplace`
- `GET /v1/sync-status` (`blockchain_sync_status_v1_sync_status_get`) on `Openapi`

## Operational Notes

- **Status / Release:** `✅` / `—`
