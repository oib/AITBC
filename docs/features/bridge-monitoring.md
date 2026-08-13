# Bridge Monitoring

Start bridge monitoring on startup

- **Status**: ✅
- **Release**: —

## Implementation Details

- `apps/wallet/src/wallet_app/bridge/bridge_monitor.py` — ETH-AIT Bridge Monitor Polls Ethereum RPC for incoming ETH transactions to the bridge wallet address...
- `apps/blockchain-node/src/aitbc_chain/network/bridge_manager.py` — Bridge Manager Manages island bridging with manual approval for federated mesh
- `apps/bridge-monitor/aitbc-bridge-monitor-wrapper.py` — Bridge monitor service wrapper.
- `apps/blockchain-event-bridge/src/blockchain_event_bridge/bridge.py` — Core bridge logic for blockchain event to agent trigger mapping.
- `Blockchain Node` exposes `POST /rpc/islands/bridge` (operation `request_bridge_route_rpc_islands_bridge_post`) — Request a bridge to another island
- `Blockchain Node` exposes `POST /rpc/chains/start` (operation `start_chain_route_rpc_chains_start_post`) — Start a secondary chain (v0.6.4)
- `Blockchain Node` exposes `POST /rpc/bridge/settlement/create` (operation `create_escrow_route_rpc_bridge_settlement_create_post`) — Create cross-chain escrow

## Examples

- `POST /join` (`join_island` in `apps/edge/src/aitbc_edge/routers/islands.py`)
- `POST /leave` (`leave_island` in `apps/edge/src/aitbc_edge/routers/islands.py`)
- `GET /` (`list_islands` in `apps/edge/src/aitbc_edge/routers/islands.py`)
- `GET /{island_id}` (`get_island` in `apps/edge/src/aitbc_edge/routers/islands.py`)
- `POST /bridge` (`request_bridge` in `apps/edge/src/aitbc_edge/routers/islands.py`)
- `POST /rpc/islands/bridge` (`request_bridge_route_rpc_islands_bridge_post`) on `Blockchain Node`
- `POST /rpc/chains/start` (`start_chain_route_rpc_chains_start_post`) on `Blockchain Node`
- `POST /rpc/bridge/settlement/create` (`create_escrow_route_rpc_bridge_settlement_create_post`) on `Blockchain Node`

## Operational Notes

- **Status / Release:** `✅` / `—`
