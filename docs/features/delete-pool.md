# Delete Pool

Delete a pool (must have no miners)

- **Status**: ✅
- **Release**: v0.6.7

## Implementation Details

- `aitbc/network/http_pool.py` — import asyncio from typing import Any import httpx from aitbc.aitbc_logging import get_logger logger...
- `apps/coordinator-api/src/coordinator_api/contexts/infrastructure/services/miners.py` — Deregister a miner from the system
- API endpoint `POST /init` implemented in `apps/edge/src/aitbc_edge/routers/database.py`
- API endpoint `GET /` implemented in `apps/edge/src/aitbc_edge/routers/database.py`
- API endpoint `GET /{database_id}` implemented in `apps/edge/src/aitbc_edge/routers/database.py`
- `Coordinator API` exposes `DELETE /v1/miners/{miner_id}` (operation `deregister_miner_v1_miners__miner_id__delete`) — Deregister miner
- `Blockchain Node` exposes `DELETE /rpc/lease/{node_id}` (operation `revoke_lease_route_rpc_lease__node_id__delete`) — Revoke subscription lease
- `Blockchain Node` exposes `GET /rpc/mining/miners` (operation `list_miners_route_rpc_mining_miners_get`) — List active miners

## Examples

- `POST /init` (`init_database` in `apps/edge/src/aitbc_edge/routers/database.py`)
- `GET /` (`list_databases` in `apps/edge/src/aitbc_edge/routers/database.py`)
- `GET /{database_id}` (`get_database` in `apps/edge/src/aitbc_edge/routers/database.py`)
- `DELETE /{database_id}` (`delete_database` in `apps/edge/src/aitbc_edge/routers/database.py`)
- `POST /{database_id}/sync` (`sync_database` in `apps/edge/src/aitbc_edge/routers/database.py`)
- `DELETE /v1/miners/{miner_id}` (`deregister_miner_v1_miners__miner_id__delete`) on `Coordinator API`
- `DELETE /rpc/lease/{node_id}` (`revoke_lease_route_rpc_lease__node_id__delete`) on `Blockchain Node`
- `GET /rpc/mining/miners` (`list_miners_route_rpc_mining_miners_get`) on `Blockchain Node`

## Operational Notes

- **Status / Release:** `✅` / `v0.6.7`
- Manages pool configuration, worker tracking, and payout scheduling.
- The pool-hub manages miner registration, job assignment, scoring, and reward distribution.
