# Dispute Resolution Contract

Dispute Resolution Smart Contract

## Implementation Details

- `DisputeStatus`
- `DisputeType`
- `Dispute`
- `Evidence`
- `ArbitrationVote`
- `DisputeResolutionContract` — In-memory implementation of Dispute Resolution contract

## Examples

Python contract source: [`apps/blockchain-node/src/aitbc_chain/contracts/dispute_resolution.py`](../../apps/blockchain-node/src/aitbc_chain/contracts/dispute_resolution.py)

## Operational Notes

- This is an in-memory Python implementation used by the blockchain-node RPC layer.
- See [`docs/api/blockchain-node-openapi.json`](../../docs/api/blockchain-node-openapi.json) for related RPC endpoints.
