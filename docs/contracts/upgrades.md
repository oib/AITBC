# Upgrades Contract

> **Skeleton stub** — the source file it points to is
> authoritative; internal helper lists were removed because they drift.

Contract Upgrade System

## Implementation Details

- `UpgradeStatus`
- `UpgradeType`
- `ContractVersion`
- `UpgradeProposal`
- `ContractUpgradeManager` — Manages contract upgrades and versioning

## Examples

Python contract source: [`apps/blockchain-node/src/aitbc_chain/contracts/upgrades.py`](../../apps/blockchain-node/src/aitbc_chain/contracts/upgrades.py)

## Operational Notes

- This is an in-memory Python implementation used by the blockchain-node RPC layer.
- See [`docs/api/blockchain-node-openapi.json`](../../docs/api/blockchain-node-openapi.json) for related RPC endpoints.
