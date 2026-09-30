# Guardian Contract

> **Skeleton stub** — the source file it points to is
> authoritative; internal helper lists were removed because they drift.

AITBC Guardian Contract - Spending Limit Protection for Agent Wallets

## Implementation Details

- `SpendingLimit` — Spending limit configuration
- `TimeLockConfig` — Time lock configuration for large withdrawals
- `GuardianConfig` — Complete guardian configuration
- `GuardianContract` — Guardian contract implementation for agent wallet protection

## Examples

Python contract source: [`apps/blockchain-node/src/aitbc_chain/contracts/guardian_contract.py`](../../apps/blockchain-node/src/aitbc_chain/contracts/guardian_contract.py)

## Operational Notes

- This is an in-memory Python implementation used by the blockchain-node RPC layer.
- See [`docs/api/blockchain-node-openapi.json`](../../docs/api/blockchain-node-openapi.json) for related RPC endpoints.
