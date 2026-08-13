# Faucet

Request test tokens for development

- **Status**: ✅
- **Release**: —

## Implementation Details

- `Blockchain Node` exposes `POST /rpc/faucet` (operation `faucet_request_route_rpc_faucet_post`) — Request test tokens from faucet
- `Wallet` exposes `POST /v1/wallets/{wallet_id}/faucet` (operation `faucet_request_v1_wallets__wallet_id__faucet_post`) — Request faucet funds
- `Blockchain Node` exposes `POST /rpc/islands/bridge` (operation `request_bridge_route_rpc_islands_bridge_post`) — Request a bridge to another island

## Examples

- `POST /faucet` (`faucet_request_route` in `apps/blockchain-node/src/aitbc_chain/rpc/routers/core.py`)
- `POST /join` (`join_island` in `apps/edge/src/aitbc_edge/routers/islands.py`)
- `POST /leave` (`leave_island` in `apps/edge/src/aitbc_edge/routers/islands.py`)
- `GET /` (`list_islands` in `apps/edge/src/aitbc_edge/routers/islands.py`)
- `GET /{island_id}` (`get_island` in `apps/edge/src/aitbc_edge/routers/islands.py`)
- `POST /rpc/faucet` (`faucet_request_route_rpc_faucet_post`) on `Blockchain Node`
- `POST /v1/wallets/{wallet_id}/faucet` (`faucet_request_v1_wallets__wallet_id__faucet_post`) on `Wallet`
- `POST /rpc/islands/bridge` (`request_bridge_route_rpc_islands_bridge_post`) on `Blockchain Node`

## Operational Notes

- **Status / Release:** `✅` / `—`
- Provides unified entry point with authentication, rate limiting, and request forwarding.
