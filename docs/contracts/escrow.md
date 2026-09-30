# Escrow Contract

> **Skeleton stub** — the source file it points to is
> authoritative; internal helper lists were removed because they drift.

Smart Contract Escrow System

## Implementation Details

- `EscrowState`
- `DisputeReason`
- `EscrowContract`
- `Milestone`
- `EscrowManager` — Manages escrow contracts for AI job market

## Examples

Python contract source: [`apps/blockchain-node/src/aitbc_chain/contracts/escrow.py`](../../apps/blockchain-node/src/aitbc_chain/contracts/escrow.py)

## Operational Notes

- This is an in-memory Python implementation used by the blockchain-node RPC layer.
- See [`docs/api/blockchain-node-openapi.json`](../../docs/api/blockchain-node-openapi.json) for related RPC endpoints.
