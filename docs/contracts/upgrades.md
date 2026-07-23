# Upgrades Contract

Contract Upgrade System

## Implementation Details

- `UpgradeStatus`
- `UpgradeType`
- `ContractVersion`
- `UpgradeProposal`
- `ContractUpgradeManager` — Manages contract upgrades and versioning

## Key Functions

- `log_info()`
- `log_error()`
- `log_warn()`
- `get_upgrade_manager() — Get global upgrade manager`
- `create_upgrade_manager() — Create and set global upgrade manager`

## Examples

Python contract source: [`apps/blockchain-node/src/aitbc_chain/contracts/upgrades.py`](../../apps/blockchain-node/src/aitbc_chain/contracts/upgrades.py)

## Operational Notes

- This is an in-memory Python implementation used by the blockchain-node RPC layer.
- See [`docs/api/blockchain-node-openapi.json`](../../docs/api/blockchain-node-openapi.json) for related RPC endpoints.
