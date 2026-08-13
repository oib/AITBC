# Leave Pool

Remove a miner from a pool

- **Status**: ✅
- **Release**: v0.6.7

## Implementation Details

- `apps/miner/production_miner.py` — Real GPU Miner Client for AITBC - runs on host with actual GPU
- `apps/pool-hub/src/poolhub/repositories/miner_repository.py` — Coordinates miner registry persistence across PostgreSQL and Redis.
- `apps/coordinator-api/src/coordinator_api/contexts/infrastructure/routers/miner.py` — List jobs assigned to a specific miner
- `Blockchain Node` exposes `POST /rpc/islands/leave` (operation `leave_island_route_rpc_islands_leave_post`) — Leave an island
- `Coordinator API` exposes `POST /v1/admin/debug/create-test-miner` (operation `create_test_miner_v1_admin_debug_create_test_miner_post`) — Create a test miner for debugging
- `Coordinator API` exposes `GET /v1/marketplace/miner-offers` (operation `list_miner_offers_v1_marketplace_miner_offers_get`) — List all miner offers

## Examples

- `POST /join` (`join_island` in `apps/edge/src/aitbc_edge/routers/islands.py`)
- `POST /leave` (`leave_island` in `apps/edge/src/aitbc_edge/routers/islands.py`)
- `GET /` (`list_islands` in `apps/edge/src/aitbc_edge/routers/islands.py`)
- `GET /{island_id}` (`get_island` in `apps/edge/src/aitbc_edge/routers/islands.py`)
- `POST /bridge` (`request_bridge` in `apps/edge/src/aitbc_edge/routers/islands.py`)
- `POST /rpc/islands/leave` (`leave_island_route_rpc_islands_leave_post`) on `Blockchain Node`
- `POST /v1/admin/debug/create-test-miner` (`create_test_miner_v1_admin_debug_create_test_miner_post`) on `Coordinator API`
- `GET /v1/marketplace/miner-offers` (`list_miner_offers_v1_marketplace_miner_offers_get`) on `Coordinator API`

## Operational Notes

- **Status / Release:** `✅` / `v0.6.7`
- Manages pool configuration, worker tracking, and payout scheduling.
