# Auto-Import

Auto-import genesis wallet and wallet directory on startup

- **Status**: ✅
- **Release**: —

## Implementation Details

- `apps/blockchain-node/scripts/unified_genesis.py` — Compute block hash
- `apps/wallet/scripts/import_file_wallets.py` — Import file-based wallets from ~/.aitbc/wallets/ into the wallet daemon.
- `apps/blockchain-node/scripts/create_genesis_wallet.py` — Create genesis wallet with secure random secp256k1 private key
- `apps/blockchain-node/src/aitbc_chain/contracts/agent_wallet_security.py` — Security profile for an agent
- `apps/blockchain-node/scripts/make_genesis.py` — Load address allocations from a JSON file. Expected format: [ {"address": "0x...", "balance": 100000...
- `Blockchain Node` exposes `GET /rpc/genesis_allocations` (operation `get_genesis_allocations_route_rpc_genesis_allocations_get`) — Get genesis allocations from blockchain
- `Blockchain Node` exposes `POST /rpc/importBlock` (operation `import_block_route_rpc_importBlock_post`) — Import a block
- `Blockchain Node` exposes `POST /rpc/import-chain` (operation `import_chain_route_rpc_import_chain_post`) — Import chain state

## Examples

- `POST /join` (`join_island` in `apps/edge/src/aitbc_edge/routers/islands.py`)
- `POST /leave` (`leave_island` in `apps/edge/src/aitbc_edge/routers/islands.py`)
- `GET /` (`list_islands` in `apps/edge/src/aitbc_edge/routers/islands.py`)
- `GET /{island_id}` (`get_island` in `apps/edge/src/aitbc_edge/routers/islands.py`)
- `POST /bridge` (`request_bridge` in `apps/edge/src/aitbc_edge/routers/islands.py`)
- `GET /rpc/genesis_allocations` (`get_genesis_allocations_route_rpc_genesis_allocations_get`) on `Blockchain Node`
- `POST /rpc/importBlock` (`import_block_route_rpc_importBlock_post`) on `Blockchain Node`
- `POST /rpc/import-chain` (`import_chain_route_rpc_import_chain_post`) on `Blockchain Node`

## Operational Notes

- **Status / Release:** `✅` / `—`
