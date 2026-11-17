# C901 / except-ratchet watch-list

Machine-regenerated reference for reviewers (#1517). **Do not edit by hand** —
run `scripts/ci/render-c901-watch-list.py > scripts/ci/c901-watch-list.md`.

## Gates

- **C901:** `scripts/ci/check-c901-ratchet.sh` (pre-push hook `c901-complexity-ratchet`)
- **BLE001/S110:** `scripts/ci/check-except-ratchet.sh` (pre-push hook `except-ratchet`)
- Baseline files: 10 C901 files, 2 except files

## Tier 1 — brushing complexity 11–12 in hot files

Extract a helper before adding branches to these functions.


## Tier 2 — highest C901 baseline counts (per-file ceiling)

- `cli/aitbc_cli/core/node_client.py`: 2
- `aitbc/trading/subscription_client.py`: 1
- `apps/blockchain-node/src/aitbc_chain/cross_chain/bridge.py`: 1
- `cli/aitbc_cli/core/chain_manager.py`: 1
- `cli/aitbc_cli/core/genesis_generator.py`: 1
- `cli/aitbc_cli/utils/error_handling.py`: 1
- `cli/aitbc_cli/utils/help_quality.py`: 1
- `cli/aitbc_cli/utils/wallet_loader.py`: 1
- `packages/py/aitbc-agent-sdk/src/aitbc_agent/cli_contract_client.py`: 1
- `packages/py/aitbc-agent-sdk/src/aitbc_agent/compute_provider.py`: 1

## Tier 3 — deep complexity (ratchet-blind to in-function growth)


## C901 volume by top-level path

- `cli`: 7
- `packages`: 2
- `aitbc`: 1
- `apps`: 1

## Except baseline hotspots (BLE001/S110)

- `cli/security/translation_policy.py`: 2
- `cli/config_data/__init__.py`: 1
