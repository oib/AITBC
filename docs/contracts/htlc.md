# Htlc Contract

> **Skeleton stub** — the source file it points to is
> authoritative; internal helper lists were removed because they drift.

Python-native HTLC contract implementation (v0.9.0 B4).

## Implementation Details

- `SwapStatus`
- `HTLCSwapRecord` — In-memory representation of a swap (persisted via DB).
- `HTLCContract` — Python-native HTLC contract that manages swap state and fund movement.

## Examples

Python contract source: [`apps/blockchain-node/src/aitbc_chain/contracts/htlc_contract.py`](../../apps/blockchain-node/src/aitbc_chain/contracts/htlc_contract.py)

## Operational Notes

- This is an in-memory Python implementation used by the blockchain-node RPC layer.
- See [`docs/api/blockchain-node-openapi.json`](../../docs/api/blockchain-node-openapi.json) for related RPC endpoints.
