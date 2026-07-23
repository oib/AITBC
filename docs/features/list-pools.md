# List Pools

List all pools with pagination

- **Status**: ✅
- **Release**: v0.6.7
## Implementation Details
- API endpoint `POST /join` implemented in `apps/edge/src/aitbc_edge/routers/islands.py`
- API endpoint `POST /leave` implemented in `apps/edge/src/aitbc_edge/routers/islands.py`
- API endpoint `GET /` implemented in `apps/edge/src/aitbc_edge/routers/islands.py`
- API endpoint `GET /{island_id}` implemented in `apps/edge/src/aitbc_edge/routers/islands.py`
- API endpoint `POST /bridge` implemented in `apps/edge/src/aitbc_edge/routers/islands.py`
- `Blockchain Node` exposes `GET /rpc/contracts` (operation `list_contracts_route_rpc_contracts_get`) — List deployed contracts
- `Blockchain Node` exposes `GET /rpc/islands` (operation `list_islands_route_rpc_islands_get`) — List all islands
- `Blockchain Node` exposes `GET /rpc/chains` (operation `list_chains_route_rpc_chains_get`) — List all chain instances (v0.6.4)
## Examples

- `POST /join` (`join_island` in `apps/edge/src/aitbc_edge/routers/islands.py`)
- `POST /leave` (`leave_island` in `apps/edge/src/aitbc_edge/routers/islands.py`)
- `GET /` (`list_islands` in `apps/edge/src/aitbc_edge/routers/islands.py`)
- `GET /{island_id}` (`get_island` in `apps/edge/src/aitbc_edge/routers/islands.py`)
- `POST /bridge` (`request_bridge` in `apps/edge/src/aitbc_edge/routers/islands.py`)
- `GET /rpc/contracts` (`list_contracts_route_rpc_contracts_get`) on `Blockchain Node`
- `GET /rpc/islands` (`list_islands_route_rpc_islands_get`) on `Blockchain Node`
- `GET /rpc/chains` (`list_chains_route_rpc_chains_get`) on `Blockchain Node`
## Operational Notes
- **Status / Release:** `✅` / `v0.6.7`
- Miners (compute providers) join pools, receive jobs, submit results, and get paid in AIT coins based on their contribution score.
- **Why this is a dedicated release**: The pool-hub has 3.9K lines of code with routers for jobs, miners, and pools, plus a scoring engine and miner registry — bu...
