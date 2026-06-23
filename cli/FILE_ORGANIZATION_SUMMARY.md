# CLI File Organization Summary

**Updated**: 2026-06-22
**Status**: Active — modular `aitbc_cli` package layout
**Runtime version**: 2.1.0
**Package**: `aitbc-cli` (editable install into `/opt/aitbc/venv`)

## Directory Structure

```
cli/
├── README.md                       # User-facing CLI overview & command reference
├── CLI_USAGE_GUIDE.md              # Detailed usage guide with workflows
├── FILE_ORGANIZATION_SUMMARY.md    # This file
├── __init__.py                     # Package marker
├── setup.py                        # setuptools setup (entry point: aitbc_cli.core.main:main)
├── requirements-cli.txt            # CLI-specific dependencies
├── pytest.ini                      # CLI test config
├── integrate_miner_cli.sh          # Miner CLI integration helper
├── advanced_wallet.py              # Advanced wallet helpers (legacy module)
├── extended_features.py            # Extended feature helpers (legacy module)
├── keystore_auth.py                # Keystore auth helper (legacy module)
├── miner_cli.py                    # Miner CLI helper (legacy module)
├── miner_management.py             # Miner management helper (legacy module)
│
├── aitbc_cli/                      # Main CLI package (importable as `aitbc_cli`)
│   ├── __init__.py                 # Compatibility surface; lazy `cli`/`main` exports
│   ├── config.py                   # CLI configuration loader
│   ├── auth/
│   │   └── __init__.py             # Auth helpers (placeholder package)
│   ├── core/                       # Core CLI engine
│   │   ├── __init__.py
│   │   ├── __version__.py          # __version__ = "0.2.2" (package metadata)
│   │   ├── main.py                 # Click entry point; registers 50+ command groups
│   │   ├── imports.py              # Import utilities
│   │   ├── plugins.py              # Plugin system
│   │   ├── analytics.py            # Core analytics
│   │   ├── chain_manager.py        # Chain manager
│   │   ├── genesis_generator.py    # Genesis generator
│   │   ├── marketplace.py          # Core marketplace
│   │   ├── node_client.py          # Node client
│   │   └── agent_communication.py  # Agent communication core
│   ├── commands/                   # Command groups (one file per group, plus packages)
│   │   ├── account.py              agent_comm.py        agent_sdk.py
│   │   ├── ai.py                   analytics.py         bridge.py
│   │   ├── chain.py                cluster.py           coin_requests.py
│   │   ├── compliance.py           config.py            contract.py
│   │   ├── cross_chain.py          economics.py         edge.py
│   │   ├── explorer.py             genesis.py           governance.py
│   │   ├── gpu_marketplace.py      gpu_resources.py     agent.py
│   │   ├── marketplace_cmd.py   messaging.py
│   │   ├── mining.py               monitor.py           network.py
│   │   ├── node.py                 operations.py        performance.py
│   │   ├── pool_hub.py             reputation.py        resource.py
│   │   ├── script.py               security.py          simulate.py
│   │   ├── sync.py                 system.py            system_architect.py
│   │   ├── transactions.py         workflow.py
│   │   ├── exchange/               # Exchange package (main, bridge, payments, trading, wallet)
│   │   ├── market/                 # Market package (escrow, exchange, jobs, offers, ratings)
│   │   ├── node/                   # Node package (bridge, chain, hub, island, main, monitor)
│   │   └── wallet/                 # Wallet package (basic, misc, multisig, staking)
│   ├── models/
│   │   ├── __init__.py
│   │   └── chain.py                # Chain data model
│   └── utils/                      # CLI-internal utilities
│       ├── __init__.py
│       ├── blockchain.py           chain_id.py
│       ├── crypto_utils.py         dual_mode_wallet_adapter.py
│       ├── error_handling.py       http_client.py
│       ├── island_credentials.py   subprocess.py
│       ├── wallet.py               wallet_daemon_client.py
│
├── aitbc/                          # Compatibility shim package (re-exports)
│   └── __init__.py
│
├── auth/
│   └── __init__.py                 # Top-level auth (placeholder)
│
├── completion/                     # Shell completion scripts
│   ├── aitbc_completion.sh
│   └── aitbc_shell_completion.sh
│
├── config_data/                    # Static config data
│   ├── __init__.py
│   └── chains.py
│
├── docs/                           # CLI-internal documentation
│   ├── README.md                   # CLI technical docs landing page
│   ├── DISABLED_COMMANDS_CLEANUP.md
│   └── FILE_ORGANIZATION_SUMMARY.md
│
├── examples/                       # Example scripts
│   ├── client.py
│   ├── client_enhanced.py
│   ├── miner.py
│   └── wallet.py
│
├── man/                            # Manpage
│   └── aitbc.1
│
├── models/                         # Top-level models (legacy)
│   ├── __init__.py
│   └── chain.py
│
├── scripts/                        # CLI helper scripts
│   ├── activate_aitbc_cli.sh
│   ├── install_local_package.sh
│   └── setup_man_page.sh
│
├── security/                       # Security policies
│   ├── __init__.py
│   └── translation_policy.py
│
├── setup/                          # Alternate setup location
│   └── setup.py
│
├── templates/                      # Templates
│   ├── genesis/
│   └── handler_template.py
│
├── tests/                          # CLI-internal smoke tests (6 files)
│   ├── conftest.py
│   ├── run_cli_tests.py
│   ├── test_cli_basic.py
│   ├── test_cli_comprehensive.py
│   ├── test_exchange_island.py
│   ├── test_explorer.py
│   ├── test_gpu_marketplace.py
│   └── test_island_credentials.py
│
└── utils/                          # Top-level utilities (legacy helpers)
    ├── __init__.py
    ├── crypto_utils.py
    ├── dual_mode_wallet_adapter.py
    ├── error_handling.py
    ├── kyc_aml_providers.py
    ├── secure_audit.py
    ├── security.py
    ├── subprocess.py
    ├── wallet_daemon_client.py
    └── wallet_migration_service.py
```

## Package Layout Notes

### `aitbc_cli/` — the importable package
This is the canonical package installed by `pip install -e .`. The Click entry point is `aitbc_cli.core.main:main`, which registers all 50+ command groups.

### `aitbc_cli/commands/` — command groups
Most command groups are single-file modules (e.g. `network.py`, `agent.py`). Four groups have been refactored into subpackages for modularity:
- `exchange/` — bridge, payments, trading, wallet
- `market/` — escrow, exchange, jobs, offers, ratings
- `node/` — bridge, chain, hub, island, main, monitor
- `wallet/` — basic, misc, multisig, staking

### `aitbc_cli/utils/` vs top-level `utils/`
`aitbc_cli/utils/` contains the active utilities imported by command modules (`http_client.py`, `chain_id.py`, `wallet.py`, etc.). The top-level `cli/utils/` directory holds older helper modules retained for compatibility.

### `aitbc/` — compatibility shim
A small package that re-exports from `aitbc_cli` for legacy import paths.

### Tests
- `cli/tests/` — 6 CLI-internal smoke tests
- `tests/cli/` (project root) — 119 comprehensive command & integration tests

### Removed
- `cli/debian/` — Debian packaging tree (removed 2026-06-22; the deployment script installs via `pip install -e .` directly)
- `cli/scripts/build_deb.sh` — Debian package builder (removed with the tree above)

## Entry Point

```python
# setup.py
entry_points={
    "console_scripts": [
        "aitbc=aitbc_cli.core.main:main",
    ],
}
```

The deployment script (`scripts/deployment/setup.sh`) writes a wrapper at `/usr/local/bin/aitbc` that calls `/opt/aitbc/venv/bin/python -m aitbc_cli.core.main "$@"`, making `aitbc` available system-wide.

## Verification

- `aitbc --version` → `aitbc, version 2.1.0`
- `aitbc --help` → lists 50+ command groups
- `pip install -e .` → editable install into `/opt/aitbc/venv`
- `python -m pytest tests/` → CLI smoke tests
- `python -m pytest tests/cli/` → comprehensive command & integration tests

---

*Last updated: 2026-06-22*
*Status: Active — matches the v2.1.0 CLI runtime*
