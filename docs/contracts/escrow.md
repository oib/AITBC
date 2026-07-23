# Escrow Contract

Smart Contract Escrow System

## Implementation Details

- `EscrowState`
- `DisputeReason`
- `EscrowContract`
- `Milestone`
- `EscrowManager` — Manages escrow contracts for AI job marketplace

## Key Functions

- `log_info() — Simple logging function`
- `log_info_old() — Legacy logging function - use logger instead`
- `get_escrow_manager() — Get global escrow manager`
- `create_escrow_manager() — Create and set global escrow manager`

## Examples

Python contract source: [`apps/blockchain-node/src/aitbc_chain/contracts/escrow.py`](../../apps/blockchain-node/src/aitbc_chain/contracts/escrow.py)

## Operational Notes

- This is an in-memory Python implementation used by the blockchain-node RPC layer.
- See [`docs/api/blockchain-node-openapi.json`](../../docs/api/blockchain-node-openapi.json) for related RPC endpoints.
