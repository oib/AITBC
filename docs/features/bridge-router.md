# Bridge Router

Bridge operations via wallet

- **Status**: ✅
- **Release**: —

## Implementation Details

- `apps/wallet/src/wallet_app/bridge/bridge_routes.py` — ETH-AIT Bridge API Routes REST API endpoints for bridge operations.
- `apps/blockchain-node/src/aitbc_chain/rpc/router.py` — Start mining with specified wallet (requires admin authentication)
- `apps/blockchain-node/src/aitbc_chain/rpc/routers/bridge.py` — Bridge router.
- `apps/coordinator-api/src/coordinator_api/contexts/cross_chain/services/cross_chain/bridge_client_adapter.py` — Underlying BridgeClient instance.
- `Blockchain Node` exposes `POST /rpc/islands/bridge` (operation `request_bridge_route_rpc_islands_bridge_post`) — Request a bridge to another island
- `Blockchain Node` exposes `POST /rpc/bridge/settlement/create` (operation `create_escrow_route_rpc_bridge_settlement_create_post`) — Create cross-chain escrow
- `Blockchain Node` exposes `POST /rpc/bridge/settlement/{escrow_id}/lock` (operation `lock_escrow_route_rpc_bridge_settlement__escrow_id__lock_post`) — Lock escrow funds

## Examples

- `POST /join` (`join_island` in `apps/edge/src/aitbc_edge/routers/islands.py`)
- `POST /leave` (`leave_island` in `apps/edge/src/aitbc_edge/routers/islands.py`)
- `GET /` (`list_islands` in `apps/edge/src/aitbc_edge/routers/islands.py`)
- `GET /{island_id}` (`get_island` in `apps/edge/src/aitbc_edge/routers/islands.py`)
- `POST /bridge` (`request_bridge` in `apps/edge/src/aitbc_edge/routers/islands.py`)
- `POST /rpc/islands/bridge` (`request_bridge_route_rpc_islands_bridge_post`) on `Blockchain Node`
- `POST /rpc/bridge/settlement/create` (`create_escrow_route_rpc_bridge_settlement_create_post`) on `Blockchain Node`
- `POST /rpc/bridge/settlement/{escrow_id}/lock` (`lock_escrow_route_rpc_bridge_settlement__escrow_id__lock_post`) on `Blockchain Node`

## Operational Notes

- **Status / Release:** `✅` / `—`
