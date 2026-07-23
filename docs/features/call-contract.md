# Call Contract

Call a contract method

- **Status**: ✅
- **Release**: —
## Implementation Details
- `apps/blockchain-node/src/aitbc_chain/contracts/htlc_contract.py` — Return the configured block time for a chain, falling back to the global default.
- `apps/blockchain-node/src/aitbc_chain/rpc/contract_service.py` — Contract Service Module — queries deployed contracts from the database.
- `Blockchain Node` exposes `POST /rpc/contracts/call` (operation `call_contract_route_rpc_contracts_call_post`) — Call a contract method
- `Blockchain Node` exposes `POST /rpc/contracts/deploy/messaging` (operation `deploy_messaging_contract_route_rpc_contracts_deploy_messaging_post`) — Deploy messaging contract
- `Blockchain Node` exposes `POST /rpc/contracts/deploy` (operation `deploy_contract_route_rpc_contracts_deploy_post`) — Deploy a smart contract
## Examples

- `POST /call` (`call_contract_route` in `apps/blockchain-node/src/aitbc_chain/rpc/routers/contracts.py`)
- `POST /v1/trading/offers/subscribe` (`subscribe_to_offers` in `apps/trading/src/trading_service/routers/subscriptions.py`)
- `POST /v1/trading/offers/heartbeat` (`offer_heartbeat` in `apps/trading/src/trading_service/routers/subscriptions.py`)
- `GET /v1/trading/offers/subscription-status` (`get_subscription_status` in `apps/trading/src/trading_service/routers/subscriptions.py`)
- `GET /v1/trading/offers/search` (`search_offers` in `apps/trading/src/trading_service/routers/subscriptions.py`)
- `POST /rpc/contracts/call` (`call_contract_route_rpc_contracts_call_post`) on `Blockchain Node`
- `POST /rpc/contracts/deploy/messaging` (`deploy_messaging_contract_route_rpc_contracts_deploy_messaging_post`) on `Blockchain Node`
- `POST /rpc/contracts/deploy` (`deploy_contract_route_rpc_contracts_deploy_post`) on `Blockchain Node`
## Operational Notes
- **Status / Release:** `✅` / `—`
- Alerts operators to anomalies and bridge contract events.
