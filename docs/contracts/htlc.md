# Htlc Contract

Python-native HTLC contract implementation (v0.9.0 B4).

## Implementation Details

- `SwapStatus`
- `HTLCSwapRecord` — In-memory representation of a swap (persisted via DB).
- `HTLCContract` — Python-native HTLC contract that manages swap state and fund movement.

## Key Functions

- `_get_chain_block_time_seconds() — Return the configured block time for a chain, falling back to the global default.`
- `_compute_swap_id() — Compute a deterministic swap ID (mirrors Solidity keccak256 pattern).`
- `_get_or_create_account() — Get an account or create it with zero balance.`
- `_transfer_balance() — Transfer ``amount`` from one account to another within a DB session.`

## Examples

Python contract source: [`apps/blockchain-node/src/aitbc_chain/contracts/htlc_contract.py`](../../apps/blockchain-node/src/aitbc_chain/contracts/htlc_contract.py)

## Operational Notes

- This is an in-memory Python implementation used by the blockchain-node RPC layer.
- See [`docs/api/blockchain-node-openapi.json`](../../docs/api/blockchain-node-openapi.json) for related RPC endpoints.
