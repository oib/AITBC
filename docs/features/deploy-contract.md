# Deploy Contract

Deploy a smart contract to the blockchain

- **Status**: ✅
- **Release**: —
## Implementation Details
- `apps/blockchain-node/src/aitbc_chain/rpc/contract_service.py` — Contract Service Module — queries deployed contracts from the database.
- `apps/coordinator-api/src/coordinator_api/contexts/blockchain/services/blockchain.py` — Blockchain service for the network token operations
- `apps/blockchain-node/src/aitbc_chain/contracts/htlc_contract.py` — Return the configured block time for a chain, falling back to the global default.
- `aitbc/caching/blockchain_decorator.py` — Blockchain-specific caching decorator
- `Blockchain Node` exposes `POST /rpc/contracts/deploy` (operation `deploy_contract_route_rpc_contracts_deploy_post`) — Deploy a smart contract
- `Blockchain Node` exposes `POST /rpc/contracts/deploy/messaging` (operation `deploy_messaging_contract_route_rpc_contracts_deploy_messaging_post`) — Deploy messaging contract
- `Blockchain Node` exposes `POST /rpc/eth_getLogs` (operation `get_logs_route_rpc_eth_getLogs_post`) — Query smart contract event logs
## Examples

- `POST /deploy/messaging` (`deploy_messaging_contract_route` in `apps/blockchain-node/src/aitbc_chain/rpc/routers/contracts.py`)
- `POST /deploy` (`deploy_contract_route` in `apps/blockchain-node/src/aitbc_chain/rpc/routers/contracts.py`)
- `POST /requests` (`submit_compute_request` in `apps/edge/src/aitbc_edge/routers/serve.py`)
- `GET /requests` (`list_compute_requests` in `apps/edge/src/aitbc_edge/routers/serve.py`)
- `GET /requests/{request_id}` (`get_compute_request` in `apps/edge/src/aitbc_edge/routers/serve.py`)
- `POST /rpc/contracts/deploy` (`deploy_contract_route_rpc_contracts_deploy_post`) on `Blockchain Node`
- `POST /rpc/contracts/deploy/messaging` (`deploy_messaging_contract_route_rpc_contracts_deploy_messaging_post`) on `Blockchain Node`
- `POST /rpc/eth_getLogs` (`get_logs_route_rpc_eth_getLogs_post`) on `Blockchain Node`
## Operational Notes
- **Status / Release:** `✅` / `—`
