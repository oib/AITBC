# CLI Packaging Restructuring Plan

**Last Updated:** 2026-05-28
**Version:** 1.0

## Objective

Restructure the AITBC CLI into a proper installable Python package to eliminate sys.path manipulation debt and improve maintainability.

## Current State

### Entry Points
- `/opt/aitbc/cli/aitbc_cli.py` - Main entrypoint (symlinked from `/opt/aitbc/aitbc-cli`)
- `/opt/aitbc/cli/click_cli.py` - Legacy Click entrypoint
- `/opt/aitbc/cli/unified_cli.py` - Unified nested command hierarchy
- `/opt/aitbc/cli/miner_cli.py` - Miner-specific CLI
- `/opt/aitbc/cli/variants/main_minimal.py` - Minimal variant

### Package Structure
```
cli/
├── __init__.py
├── aitbc_cli.py (main entrypoint)
├── click_cli.py (legacy)
├── unified_cli.py (unified)
├── miner_cli.py (miner-specific)
├── variants/
│   └── main_minimal.py
├── handlers/
│   └── wallet.py
├── utils/
│   ├── wallet_daemon_client.py
│   └── dual_mode_wallet_adapter.py
├── core/
│   └── imports.py
├── aitbc_cli/
│   ├── __init__.py
│   ├── commands/
│   │   ├── wallet.py
│   │   ├── blockchain.py
│   │   ├── network.py
│   │   ├── market.py
│   │   ├── ai.py
│   │   ├── mining.py
│   │   ├── system.py
│   │   ├── agent.py
│   │   ├── hermes.py
│   │   ├── workflow.py
│   │   ├── resource.py
│   │   ├── simulate.py
│   │   ├── node.py
│   │   ├── exchange.py
│   │   └── agent_sdk.py
│   ├── config.py
│   └── utils/
│       ├── __init__.py
│       ├── output.py
│       ├── error.py
│       ├── success.py
│       └── warning.py
└── build/
    └── lib/
        └── aitbc_cli/
            └── main.py (generated)
```

### Issues
1. Multiple entrypoints with overlapping functionality
2. sys.path manipulation in every entrypoint
3. No proper package installation (run directly from source)
4. Generated code in `cli/build/` directory
5. Legacy files (cli/aitbc_cli.legacy.py at 3,257 lines)
6. Mixed import patterns (absolute vs relative)

## Target State

### Package Structure
```
cli/
├── pyproject.toml (new)
├── setup.py (optional, for compatibility)
├── src/
│   └── aitbc_cli/
│       ├── __init__.py
│       ├── main.py (single entrypoint)
│       ├── commands/
│       │   ├── __init__.py
│       │   ├── wallet.py
│       │   ├── blockchain.py
│       │   ├── network.py
│       │   ├── market.py
│       │   ├── ai.py
│       │   ├── mining.py
│       │   ├── system.py
│       │   ├── agent.py
│       │   ├── hermes.py
│       │   ├── workflow.py
│       │   ├── resource.py
│       │   ├── simulate.py
│       │   ├── node.py
│       │   ├── exchange.py
│       │   └── agent_sdk.py
│       ├── config.py
│       └── utils/
│           ├── __init__.py
│           ├── output.py
│           ├── error.py
│           ├── success.py
│           └── warning.py
├── tests/ (move from root tests/cli/)
└── README.md
```

### Entry Points
- Single console script: `aitbc-cli` pointing to `aitbc_cli.main:cli`
- Backward compatibility symlinks for legacy commands

### Installation
```bash
cd /opt/aitbc/cli
pip install -e .
```

## Implementation Plan

### Phase 1: Create Package Structure

1. **Create pyproject.toml**
   ```toml
   [build-system]
   requires = ["setuptools>=61.0", "wheel"]
   build-backend = "setuptools.build_meta"

   [project]
   name = "aitbc-cli"
   version = "0.1.0"
   description = "AITBC Command Line Interface"
   authors = [{name = "AITBC Team"}]
   license = {text = "MIT"}
   requires-python = ">=3.11"
   dependencies = [
       "click>=8.0",
       "rich>=13.0",
       "PyYAML",
       "requests",
       "cryptography",
   ]

   [project.scripts]
   aitbc-cli = "aitbc_cli.main:cli"

   [tool.setuptools]
   package-dir = {"" = "src"}

   [tool.setuptools.packages.find]
   where = ["src"]
   ```

2. **Restructure directories**
   - Create `cli/src/aitbc_cli/`
   - Move `cli/aitbc_cli/commands/` to `cli/src/aitbc_cli/commands/`
   - Move `cli/aitbc_cli/config.py` to `cli/src/aitbc_cli/config.py`
   - Move `cli/aitbc_cli/utils/` to `cli/src/aitbc_cli/utils/`
   - Create `cli/src/aitbc_cli/main.py` as single entrypoint

3. **Update imports**
   - Change all imports to use relative imports within package
   - Remove sys.path manipulation from all modules
   - Use `from ..config import get_config` instead of absolute imports

### Phase 2: Consolidate Entry Points

1. **Create unified main.py**
   ```python
   # cli/src/aitbc_cli/main.py
   import click
   from .commands import (
       wallet, blockchain, network, market, ai, mining,
       system, agent, hermes, workflow, resource, simulate,
       node, exchange, agent_sdk
   )

   @click.group()
   @click.version_option(version="0.1.0")
   def cli():
       """AITBC Command Line Interface"""
       pass

    # Add command groups
    cli.add_command(wallet.wallet)
    cli.add_command(blockchain.blockchain)
    cli.add_command(network.network)
    cli.add_command(market.market)
    cli.add_command(ai.ai)
    cli.add_command(mining.mining)
    cli.add_command(system.system)
    cli.add_command(agent.agent)
    cli.add_command(hermes.hermes)
    cli.add_command(workflow.workflow)
    cli.add_command(resource.resource)
    cli.add_command(simulate.simulate)
    cli.add_command(node.node)
    cli.add_command(exchange.exchange)
    cli.add_command(agent_sdk.agent_sdk)

    if __name__ == "__main__":
        cli()
   ```

2. **Deprecate legacy entrypoints**
   - Keep `cli/click_cli.py` but add deprecation warning
   - Keep `cli/miner_cli.py` but add deprecation warning
   - Keep `cli/unified_cli.py` as reference during migration
   - Document deprecation in README

3. **Update symlinks**
   - `/opt/aitbc/aitbc-cli` should point to installed entrypoint
   - Or keep as symlink to `cli/src/aitbc_cli/main.py` during transition

### Phase 3: Remove sys.path Manipulation

1. **CLI modules**
   - Remove sys.path.insert from `cli/src/aitbc_cli/main.py`
   - Remove sys.path.insert from all command modules
   - Remove sys.path.insert from utils modules
   - Use PYTHONPATH environment variable for cross-package imports if needed

2. **Special cases**
   - `cli/core/imports.py` - Keep as helper for coordinator-api imports, but make it optional
   - `cli/handlers/wallet.py` - Refactor to use proper imports or deprecate
   - `cli/utils/wallet_daemon_client.py` - Refactor to use proper imports

3. **Cross-package imports**
   - For imports from `aitbc` package, use PYTHONPATH in environment
   - For imports from `apps/*`, use PYTHONPATH in environment
   - Document required PYTHONPATH in README

### Phase 4: Update Systemd Services

1. **Update wrapper scripts**
   - Keep sys.path in wrappers for constants import (acceptable)
   - Ensure PYTHONPATH includes installed CLI package
   - Update exec commands to use installed `aitbc-cli`

2. **Update service files**
   - Change `ExecStart=/opt/aitbc/aitbc-cli` to use installed path
   - Or keep using `/opt/aitbc/aitbc-cli` symlink for compatibility

### Phase 5: Update Tests

1. **Move CLI tests**
   - Move `tests/cli/` to `cli/tests/`
   - Update test imports to use package imports
   - Remove sys.path manipulation from test conftest

2. **Update test execution**
   - Run tests with `pytest cli/tests/`
   - Use PYTHONPATH for test isolation if needed

### Phase 6: Documentation

1. **Update README**
   - Document installation process
   - Document required PYTHONPATH
   - Document backward compatibility

2. **Update docs**
   - Update CLI usage documentation
   - Document deprecated entrypoints
   - Update development setup instructions

3. **Update systemd docs**
   - Document wrapper script pattern
   - Document acceptable sys.path usage

## Migration Strategy

### Step 1: Create New Package (Non-Breaking)
- Create `cli/src/aitbc_cli/` structure alongside existing
- Implement new entrypoint in parallel
- Test new package without affecting existing CLI

### Step 2: Test New Package
- Install new package in venv: `pip install -e cli/`
- Test `aitbc-cli` command
- Verify all commands work
- Run test suite

### Step 3: Update Symlinks
- Update `/opt/aitbc/aitbc-cli` to point to new entrypoint
- Test with existing systemd services
- Rollback if issues

### Step 4: Deprecate Old Files
- Add deprecation warnings to legacy entrypoints
- Document deprecation timeline
- Keep for 1-2 release cycles

### Step 5: Remove Legacy Files
- Remove `cli/click_cli.py`
- Remove `cli/miner_cli.py`
- Remove `cli/unified_cli.py`
- Remove `cli/aitbc_cli.legacy.py`
- Remove `cli/build/` directory
- Remove old `cli/aitbc_cli/` directory

## Rollback Plan

If issues arise during migration:

1. **Immediate rollback**
   - Restore `/opt/aitbc/aitbc-cli` symlink to old entrypoint
   - Uninstall new package: `pip uninstall aitbc-cli`
   - Old CLI continues to work

2. **Partial rollback**
   - Keep new package installed
   - Use old entrypoint for critical services
   - Fix issues in new package

3. **Documentation rollback**
   - Document rollback procedure
   - Keep legacy files until stable

## Testing Checklist

- [ ] New package installs correctly
- [ ] `aitbc-cli` command works
- [ ] All command groups work (wallet, blockchain, network, etc.)
- [ ] All subcommands work
- [ ] Backward compatibility maintained
- [ ] Systemd services work with new CLI
- [ ] Test suite passes
- [ ] No sys.path manipulation in new package
- [ ] Cross-package imports work with PYTHONPATH
- [ ] Documentation updated

## Blocking Issue Discovered

During implementation, a critical architectural dependency was discovered:

**The CLI has deep dependencies on the broader AITBC monorepo:**

1. **aitbc package** - CLI imports from `aitbc` (get_logger, AITBCHTTPClient, NetworkError, KEYSTORE_DIR, etc.)
2. **models.chain** - Core modules import from `models.chain` (ChainInfo, ChainType, ChainStatus, ConsensusAlgorithm)
3. **Shared modules** - CLI depends on shared modules across the monorepo

**This means the CLI cannot be packaged as a standalone package without:**

1. **Option A**: Include all dependencies in CLI package (massive duplication, bad practice)
2. **Option B**: Make CLI depend on aitbc package being installed (requires aitbc to be packaged first)
3. **Option C**: Refactor CLI to remove these dependencies (major architectural change, high risk)

**Current state:** The CLI was designed to run from the monorepo with sys.path manipulation. It's not designed as a standalone package.

## Revised Approach

Given this blocking issue, the CLI packaging approach needs reconsideration:

### Option 1: Package aitbc first
- Package the `aitbc` module as a standalone library
- Then package CLI with aitbc as a dependency
- Requires significant refactoring of aitbc package structure

### Option 2: Accept sys.path as necessary
- Keep CLI running from monorepo
- Accept sys.path manipulation as acceptable for monorepo CLI
- Focus on reducing but not eliminating sys.path usage
- Document as architectural decision

### Option 3: Minimal CLI package
- Create a minimal CLI package that only contains command definitions
- Use PYTHONPATH environment variable for all imports
- CLI becomes a thin wrapper over monorepo code
- Still requires environment setup

### Option 4: Abandon CLI packaging
- Accept that CLI is monorepo-specific
- Focus on other cleanup tasks
- Document CLI as requiring monorepo context

## Estimated Effort (Original Plan)

- Phase 1: 4-6 hours (package structure, pyproject.toml) - **COMPLETED**
- Phase 2: 3-4 hours (consolidate entry points) - **BLOCKED**
- Phase 3: 4-6 hours (remove sys.path, fix imports) - **BLOCKED by dependencies**
- Phase 4: 2-3 hours (update systemd services)
- Phase 5: 2-3 hours (update tests)
- Phase 6: 2-3 hours (documentation)
- Testing: 4-6 hours

**Status: BLOCKED on architectural dependency issue**

## Implementation Attempt Results

Attempted Option 1 (Package aitbc first, then CLI) but encountered additional blocking issues:

### Issues Discovered During Implementation

1. **CLI internal structure dependencies**
   - CLI commands import from `..config` expecting a `Config` class that doesn't exist
   - CLI has its own `core` module with deployment, analytics, marketplace, etc.
   - These CLI-specific modules are not part of the aitbc package
   - Moving them to aitbc would create circular dependencies

2. **CLI-specific modules**
   - `cli/core/deployment.py` - Production deployment logic
   - `cli/core/analytics.py` - Chain analytics
   - `cli/core/marketplace.py` - Marketplace functionality
   - `cli/core/chain_manager.py` - Multi-chain management
   - These are CLI-specific, not shared library code

3. **Import resolution complexity**
   - CLI uses relative imports (`..config`, `..core`)
   - CLI expects specific internal structure
   - Package structure breaks these assumptions
   - Would require extensive refactoring of CLI internals

### Current State

- **aitbc package**: Successfully installed with models.chain moved to aitbc.models
- **CLI package**: Depends on aitbc>=0.6.0
- **Blocking issue**: CLI internal structure incompatible with package layout
- **Import errors**: Multiple CLI commands fail due to missing internal modules

### Recommendation

**Switch to Option 2: Accept sys.path as necessary**

The CLI was designed as a monorepo-specific tool with:
- Internal core modules
- Relative import structure
- Tight coupling to monorepo layout

Packaging it as a standalone package requires:
- Refactoring all internal imports
- Moving CLI-specific code to aitbc (inappropriate)
- Breaking backward compatibility
- High risk of introducing bugs

**Accept sys.path manipulation as acceptable for monorepo CLI tools.**

## Dependencies

- None (can be done independently)
- Should be done before other CLI refactoring
- Should be done before removing legacy files

## Risks

1. **Breaking changes** - Mitigated by parallel implementation and rollback plan
2. **Systemd service failures** - Mitigated by testing and rollback plan
3. **Import resolution issues** - Mitigated by PYTHONPATH documentation
4. **Backward compatibility** - Mitigated by keeping legacy files temporarily

## Success Criteria

1. CLI is installable as Python package
2. No sys.path manipulation in CLI package
3. Single entrypoint (`aitbc-cli`)
4. All commands work correctly
5. Systemd services work correctly
6. Test suite passes
7. Documentation updated
8. Legacy files removed or deprecated
