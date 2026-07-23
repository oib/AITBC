# List Contracts

List deployed contracts

- **Status**: ✅
- **Release**: —
## Implementation Details
- `apps/blockchain-node/src/aitbc_chain/rpc/contracts.py` — Derive a deterministic contract address from deployer, name, and timestamp. Similar to Ethereum's CR...
- `apps/blockchain-node/src/aitbc_chain/rpc/routers/contracts.py` — Contracts router.
- `apps/blockchain-event-bridge/src/blockchain_event_bridge/event_subscribers/contracts.py` — Contract event subscriber for smart contract event monitoring.
- `apps/blockchain-node/src/aitbc_chain/rpc/contracts_stub.py`
- API endpoint `POST /join` implemented in `apps/edge/src/aitbc_edge/routers/islands.py`
- `Blockchain Node` exposes `GET /rpc/contracts` (operation `list_contracts_route_rpc_contracts_get`) — List deployed contracts
- `Blockchain Node` exposes `POST /rpc/contracts/deploy/messaging` (operation `deploy_messaging_contract_route_rpc_contracts_deploy_messaging_post`) — Deploy messaging contract
- `Blockchain Node` exposes `POST /rpc/contracts/deploy` (operation `deploy_contract_route_rpc_contracts_deploy_post`) — Deploy a smart contract
## Examples

- `POST /join` (`join_island` in `apps/edge/src/aitbc_edge/routers/islands.py`)
- `POST /leave` (`leave_island` in `apps/edge/src/aitbc_edge/routers/islands.py`)
- `GET /` (`list_islands` in `apps/edge/src/aitbc_edge/routers/islands.py`)
- `GET /{island_id}` (`get_island` in `apps/edge/src/aitbc_edge/routers/islands.py`)
- `POST /bridge` (`request_bridge` in `apps/edge/src/aitbc_edge/routers/islands.py`)
- `GET /rpc/contracts` (`list_contracts_route_rpc_contracts_get`) on `Blockchain Node`
- `POST /rpc/contracts/deploy/messaging` (`deploy_messaging_contract_route_rpc_contracts_deploy_messaging_post`) on `Blockchain Node`
- `POST /rpc/contracts/deploy` (`deploy_contract_route_rpc_contracts_deploy_post`) on `Blockchain Node`
## Operational Notes
- **Status / Release:** `✅` / `—`
- Includes Groth16 verifier contracts and benchmarking.
