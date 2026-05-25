# sys.path Manipulation Debt

## Overview

The AITBC codebase contains approximately 105 files with `sys.path` manipulation. This is structural debt that requires CLI packaging restructuring to eliminate properly.

## Current State

### CLI Modules (~14 files)
The CLI has multiple entrypoints and command modules that manipulate sys.path to find the repo root and sibling utilities:

- `cli/aitbc_cli.py` - Main entrypoint, inserts REPO_ROOT and CLI_DIR
- `cli/click_cli.py` - Legacy Click entrypoint, inserts hardcoded `/opt/aitbc` paths
- `cli/unified_cli.py` - Unified CLI, inserts parent directory
- `cli/miner_cli.py` - Miner-specific CLI, inserts CLI directory
- `cli/__init__.py` - Package init, inserts CLI_DIR
- `cli/variants/main_minimal.py` - Minimal variant, inserts CLI_DIR
- `cli/handlers/wallet.py` - Wallet handler, inserts `/opt/aitbc/cli` for dynamic imports
- `cli/utils/wallet_daemon_client.py` - Wallet client, inserts `/opt/aitbc/cli`
- `cli/utils/dual_mode_wallet_adapter.py` - Wallet adapter, inserts `/opt/aitbc/cli`
- `cli/core/imports.py` - Import helper, inserts coordinator-api src
- `cli/aitbc_cli/commands/wallet.py` - Wallet commands, inserts parent directories
- `cli/aitbc_cli/commands/simulate.py` - Simulate commands, inserts parent directory
- `cli/aitbc_cli/commands/node.py` - Node commands, inserts blockchain-node src
- `cli/aitbc_cli/commands/exchange.py` - Exchange commands, inserts apps/exchange (now dynamic)
- `cli/aitbc_cli/commands/agent_sdk.py` - Agent SDK commands, inserts agent-sdk src

### Wrapper Scripts (14 files)
All systemd service wrappers in `scripts/wrappers/` use sys.path.insert to import aitbc constants before setting PYTHONPATH for the child process:

- `aitbc-agent-management-wrapper.py`
- `aitbc-agent-coordinator-wrapper.py`
- `aitbc-agent-daemon-wrapper.py`
- `aitbc-agent-registry-wrapper.py`
- `aitbc-blockchain-node-wrapper.py`
- `aitbc-blockchain-rpc-wrapper.py`
- `aitbc-blockchain-p2p-wrapper.py`
- `aitbc-blockchain-sync-wrapper.py`
- `aitbc-blockchain-event-bridge-wrapper.py`
- `aitbc-coordinator-api-wrapper.py`
- `aitbc-exchange-api-wrapper.py`
- `aitbc-explorer-wrapper.py`
- `aitbc-hermes-wrapper.py`
- `aitbc-marketplace-wrapper.py`
- `aitbc-monitoring-wrapper.py`
- `aitbc-plugin-wrapper.py`
- `aitbc-wallet-wrapper.py`

### Tests (~25 files)
Test files use sys.path manipulation for test isolation and to import fixtures:

- `tests/conftest.py` - Root test configuration
- `tests/cli/test_cli_integration.py` - CLI integration tests
- `tests/fixtures/blockchain.py` - Blockchain fixtures
- `tests/fixtures/coordinator.py` - Coordinator fixtures
- `tests/fixtures/common.py` - Common fixtures
- `tests/fixtures/staking_fixtures.py` - Staking fixtures
- `tests/integration/test_agent_coordinator.py` - Agent coordinator integration tests
- `tests/integration/test_staking_lifecycle.py` - Staking lifecycle tests
- `tests/services/test_staking_service.py` - Staking service tests
- Various other test files

### Scripts (~25 files)
Utility scripts in `scripts/` use sys.path for ad-hoc imports:

- `scripts/utils/chain_regen_node.py`
- `scripts/utils/migrate_secrets_to_keystore.py`
- `scripts/utils/init_production_genesis.py`
- `scripts/utils/fix_gpu_release.py`
- `scripts/utils/fix_database_persistence.py`
- `scripts/utils/encrypt_keystore_password.py`
- `scripts/utils/cleanup_fake_gpus_db.py`
- `scripts/utils/verify-production-advanced.sh`
- `scripts/service/manage-services.sh`
- `scripts/training/scenario_47_sdk_test.py`
- `scripts/services/*.py` - Various service scripts
- `scripts/testing/*.py` - Testing scripts
- `scripts/monitoring/*.sh` - Monitoring scripts
- `scripts/deployment/*.sh` - Deployment scripts

### Apps (~20 files)
App-specific scripts and modules use sys.path for local imports:

- `apps/blockchain-node/scripts/*.py` - Blockchain node scripts
- `apps/blockchain-node/tests/conftest.py` - Blockchain node test config
- `apps/coordinator-api/scripts/*.py` - Coordinator API scripts
- `apps/coordinator-api/tests/conftest.py` - Coordinator API test config
- `apps/coordinator-api/src/app/main.py` - Coordinator API main
- `apps/coordinator-api/src/app/services/tenant_management.py` - Tenant management
- `apps/exchange/exchange_api.py` - Exchange API
- `apps/marketplace/scripts/marketplace.py` - Marketplace script
- `apps/agent-coordinator/scripts/agent_daemon.py` - Agent daemon
- Various other app-specific files

### Dev/Docs (~20 files)
Development examples and documentation reference sys.path:

- `dev/examples/*.py` - Example scripts
- `dev/scripts/blockchain/create_genesis_all.py` - Genesis creation
- `dev/onboarding/auto-onboard.py` - Auto-onboarding
- `dev/aitbc-debug` - Debug script
- `docs/agent-training/ENVIRONMENT_SETUP.md` - Training setup docs
- Various other documentation files

## Why This Exists

1. **CLI not packaged as installable** - The CLI is run directly from source without proper package installation
2. **Multiple entrypoints** - Legacy CLI variants (click_cli.py, unified_cli.py, miner_cli.py) coexist
3. **Ad-hoc script execution** - Many scripts are run directly without proper Python package structure
4. **Test isolation** - Tests manipulate sys.path to avoid import conflicts in monorepo
5. **Wrapper scripts** - Systemd wrappers need to import aitbc constants before execing child processes

## Why It's Hard to Eliminate

1. **CLI restructuring required** - CLI needs to be packaged as a proper installable Python package with entry points
2. **Backward compatibility** - Legacy CLI commands and entrypoints must continue working
3. **Monorepo complexity** - Multiple apps in one repo make import resolution complex
4. **Runtime path resolution** - Some scripts need to resolve paths at runtime based on execution context
5. **Wrapper pattern** - Systemd wrappers need to import constants before setting up child process environment

## Recommended Solution

### Phase 1: Package CLI Properly
1. Create proper `pyproject.toml` for CLI with entry points
2. Define CLI as installable package with src-layout
3. Use `console_scripts` entry points for CLI commands
4. Install CLI in venv with `pip install -e .`

### Phase 2: Consolidate Entry Points
1. Deprecate legacy entrypoints (click_cli.py, miner_cli.py)
2. Use unified_cli.py as single entry point
3. Update systemd services to use installed CLI
4. Update documentation to reflect new entry point

### Phase 3: Standardize Imports
1. Remove sys.path manipulation from CLI modules
2. Use relative imports within CLI package
3. Use PYTHONPATH environment variable for cross-package imports
4. Consolidate import helpers into single module

### Phase 4: Wrapper Refactoring
1. Keep sys.path in wrappers for constants import (acceptable pattern)
2. Ensure PYTHONPATH is set before exec for child processes
3. Document wrapper pattern as acceptable for systemd services

### Phase 5: Test and Script Cleanup
1. Keep sys.path in tests (acceptable for test isolation)
2. Add PYTHONPATH to script shebangs or wrapper scripts
3. Document scripts that require specific PYTHONPATH setup

## Acceptable sys.path Usage

The following patterns are acceptable and should remain:

1. **Test fixtures** - Tests may manipulate sys.path for isolation
2. **Wrapper scripts** - Systemd wrappers may use sys.path to import constants before exec
3. **Ad-hoc scripts** - One-off utility scripts may use sys.path for simplicity
4. **App-specific scripts** - Scripts within app directories may use local sys.path

## Unacceptable sys.path Usage

The following patterns should be eliminated:

1. **Hardcoded absolute paths** - e.g., `/home/oib/windsurf/aitbc` (fixed in exchange.py)
2. **CLI entrypoint manipulation** - CLI should be installable package
3. **Production scripts with hardcoded paths** - Should use environment variables
4. **Cross-app imports via sys.path** - Should use proper package structure

## Current Status

- **Fixed**: 7 stale `/home/oib` paths in `cli/aitbc_cli/commands/exchange.py`
- **Accepted**: ~98 remaining sys.path usages as acceptable for monorepo CLI
- **Decision**: CLI packaging abandoned due to architectural incompatibility

## Final Decision

After attempting to package the CLI as a standalone library, it was determined that:

1. **CLI is monorepo-specific** - The CLI was designed to run from the monorepo with internal core modules and relative import structure
2. **Packaging is inappropriate** - CLI-specific modules (deployment, analytics, marketplace, chain_manager) are not shared library code
3. **Risk outweighs benefit** - Refactoring for packaging would break backward compatibility and introduce high risk

**sys.path manipulation is ACCEPTED as necessary for monorepo CLI tools.**

The CLI will continue to use sys.path manipulation to:
- Resolve imports from the aitbc package
- Access CLI-specific core modules
- Maintain backward compatibility
- Support the existing monorepo structure

## Next Steps

1. Accept current sys.path usage as appropriate for monorepo CLI
2. Focus on other cleanup tasks (fix/backup/legacy files)
3. Document sys.path pattern as acceptable in development guidelines
