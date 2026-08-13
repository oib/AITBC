# Get Subscribers

Get all valid subscribers

- **Status**: ✅
- **Release**: —

## Implementation Details

- API endpoint `GET /validation/compatible-services` implemented in `apps/pool-hub/src/poolhub/app/routers/validation.py`
- API endpoint `GET /validation/hardware-profile` implemented in `apps/pool-hub/src/poolhub/app/routers/validation.py`
- API endpoint `GET /validators` implemented in `apps/coordinator-api/src/coordinator_api/contexts/blockchain/routers/blockchain.py`
- API endpoint `GET /validators/{chain_id}` implemented in `apps/blockchain-node/src/aitbc_chain/rpc/routers/bridge.py`
- `Blockchain Node` exposes `GET /rpc/subscribers` (operation `subscribers_route_rpc_subscribers_get`) — Get all valid subscribers
- `Blockchain Node` exposes `GET /rpc/disputes/active` (operation `get_active_disputes_route_rpc_disputes_active_get`) — Get all active disputes
- `Blockchain Node` exposes `GET /rpc/disputes/arbitrators` (operation `get_authorized_arbitrators_route_rpc_disputes_arbitrators_get`) — Get all authorized arbitrators

## Examples

- `GET /validation/compatible-services` (`get_compatible_services` in `apps/pool-hub/src/poolhub/app/routers/validation.py`)
- `GET /validation/hardware-profile` (`get_hardware_profile` in `apps/pool-hub/src/poolhub/app/routers/validation.py`)
- `GET /validators` (`get_validators` in `apps/coordinator-api/src/coordinator_api/contexts/blockchain/routers/blockchain.py`)
- `GET /validators/{chain_id}` (`get_validator_set_route` in `apps/blockchain-node/src/aitbc_chain/rpc/routers/bridge.py`)
- `POST /join` (`join_island` in `apps/edge/src/aitbc_edge/routers/islands.py`)
- `GET /rpc/subscribers` (`subscribers_route_rpc_subscribers_get`) on `Blockchain Node`
- `GET /rpc/disputes/active` (`get_active_disputes_route_rpc_disputes_active_get`) on `Blockchain Node`
- `GET /rpc/disputes/arbitrators` (`get_authorized_arbitrators_route_rpc_disputes_arbitrators_get`) on `Blockchain Node`

## Operational Notes

- **Status / Release:** `✅` / `—`
- Listens for on-chain events and propagates them to interested subscribers in real-time.
