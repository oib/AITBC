# AITBC Repository File Structure

This document describes the current organization and status of files and folders in the repository.

Last updated: 2026-03-06

---

## Whitelist ✅ (Active & Essential)

### Core Applications (`apps/`)

| Path | Status | Notes |
|------|--------|-------|
| `apps/coordinator-api/` | ✅ Active | Main API service, standardized (Mar 2026) |
| `apps/blockchain-explorer/` | ✅ Active | Agent-first blockchain explorer, recently optimized (Mar 2026) |
| `apps/blockchain-node/` | ✅ Active | Blockchain node, standardized (Mar 2026) |
| `apps/trade-exchange/` | ✅ Active | Bitcoin exchange, deployed |
| `apps/marketplace-web/` | ✅ Active | Marketplace frontend, deployed |
| `apps/coordinator-api/src/app/domain/gpu_marketplace.py` | ✅ Active | GPURegistry, GPUBooking, GPUReview SQLModel tables (Feb 2026) |
| `apps/coordinator-api/tests/test_gpu_marketplace.py` | ✅ Active | 22 GPU marketplace tests (Feb 2026) |
| `apps/coordinator-api/tests/test_billing.py` | ✅ Active | 21 billing/usage-tracking tests (Feb 2026) |
| `apps/coordinator-api/tests/conftest.py` | ✅ Active | App namespace isolation for coordinator tests |
| `tests/cli/test_cli_integration.py` | ✅ Active | 24 CLI → live coordinator integration tests (Feb 2026) |

### Scripts (`scripts/`)

| Path | Status | Notes |
|------|--------|-------|
| `scripts/aitbc-cli.sh` | ✅ Active | Main CLI tool, heavily used |
| `scripts/dev/gpu/gpu_miner_host.py` | ✅ Active | Production GPU miner, standardized (Mar 2026) |
| `scripts/deploy/` | ✅ Active | Deployment scripts (35 files) |
| `scripts/deploy/deploy-multimodal-services.sh` | ✅ Active | Environment-aware multimodal deployment (Mar 2026) |
| `scripts/verify-codebase-update.sh` | ✅ Active | Automated codebase verification (Mar 2026) |
| `scripts/service/` | ✅ Active | Service management |
| `scripts/dev_services.sh` | ✅ Active | Local development |
| `scripts/testing/` | ✅ Active | Test scripts (moved from root, 13 files) |

### Infrastructure (`infra/`, `systemd/`)

| Path | Status | Notes |
|------|--------|-------|
| `infra/nginx/` | ✅ Active | Production nginx configs |
| `systemd/` | ✅ Active | All 19+ standardized service files (Mar 2026) |
| `systemd/aitbc-gpu-miner.service` | ✅ Active | Standardized GPU miner service |
| `systemd/aitbc-multimodal-gpu.service` | ✅ Active | Renamed GPU multimodal service (Mar 2026) |
| `systemd/aitbc-blockchain-node.service` | ✅ Active | Standardized blockchain node |
| `systemd/aitbc-blockchain-rpc.service` | ✅ Active | Standardized RPC service |
| `systemd/aitbc-coordinator-api.service` | ✅ Active | Standardized coordinator API |
| `systemd/aitbc-wallet.service` | ✅ Active | Fixed and standardized (Mar 2026) |
| `systemd/aitbc-loadbalancer-geo.service` | ✅ Active | Fixed and standardized (Mar 2026) |
| `systemd/aitbc-marketplace-enhanced.service` | ✅ Active | Fixed and standardized (Mar 2026) |

### Website (`website/`)

| Path | Status | Notes |
|------|--------|-------|
| `website/docs/` | ✅ Active | HTML documentation, recently refactored |
| `website/docs/css/docs.css` | ✅ Active | Shared CSS (1232 lines) |
| `website/docs/js/theme.js` | ✅ Active | Theme toggle |
| `website/index.html` | ✅ Active | Main website |
| `website/dashboards/` | ✅ Active | Admin/miner dashboards |

### Documentation (`docs/`)

| Path | Status | Notes |
|------|--------|-------|
| `docs/1_project/` | ✅ Active | Project management docs (restructured) |
| `docs/infrastructure/` | ✅ Active | Infrastructure documentation (Mar 2026) |
| `docs/infrastructure/codebase-update-summary.md` | ✅ Active | Comprehensive standardization summary (Mar 2026) |
| `docs/DOCS_WORKFLOW_COMPLETION_SUMMARY.md` | ✅ Active | Documentation updates completion (Mar 2026) |
| `docs/0_getting_started/` | ✅ Active | Getting started guides |
| `docs/2_clients/` | ✅ Active | Client documentation |
| `docs/3_miners/` | ✅ Active | Miner documentation |
| `docs/4_blockchain/` | ✅ Active | Blockchain documentation |
| `docs/5_reference/` | ✅ Active | Reference materials |
| `docs/6_architecture/` | ✅ Active | Architecture documentation |
| `docs/7_deployment/` | ✅ Active | Deployment guides |
| `docs/8_development/` | ✅ Active | Development documentation |
| `docs/9_security/` | ✅ Active | Security documentation |
| `docs/10_plan/` | ✅ Active | Planning documentation, updated (Mar 2026) |
| `docs/10_plan/99_currentissue.md` | ✅ Active | Current issues with standardization completion (Mar 2026) |
| `.windsurf/workflows/` | ✅ Active | Development workflows (Mar 2026) |
| `.windsurf/workflows/aitbc-services-monitoring.md` | ✅ Active | Services monitoring workflow (Mar 2026) |

### CLI Tools (`cli/`)

| Path | Status | Notes |
|------|--------|-------|
| `cli/aitbc_cli/commands/client.py` | ✅ Active | Client CLI (submit, batch-submit, templates, history) |
| `cli/aitbc_cli/commands/miner.py` | ✅ Active | Miner CLI (register, earnings, capabilities, concurrent) |
| `cli/aitbc_cli/commands/wallet.py` | ✅ Active | Wallet CLI (balance, staking, multisig, backup/restore) |
| `cli/aitbc_cli/commands/auth.py` | ✅ Active | Auth CLI (login, tokens, API keys) |
| `cli/aitbc_cli/commands/blockchain.py` | ✅ Active | Blockchain queries |
| `cli/aitbc_cli/commands/marketplace.py` | ✅ Active | GPU marketplace operations |
| `cli/aitbc_cli/commands/admin.py` | ✅ Active | System administration, audit logging |
| `cli/aitbc_cli/commands/config.py` | ✅ Active | Configuration, profiles, encrypted secrets |
| `cli/aitbc_cli/commands/monitor.py` | ✅ Active | Dashboard, metrics, alerts, webhooks |
| `cli/aitbc_cli/commands/simulate.py` | ✅ Active | Test simulation framework |
| `cli/aitbc_cli/plugins.py` | ✅ Active | Plugin system for custom commands |
| `cli/aitbc_cli/main.py` | ✅ Active | CLI entry point (12 command groups) |
| `cli/man/aitbc.1` | ✅ Active | Man page |
| `cli/aitbc_shell_completion.sh` | ✅ Active | Shell completion script |
| `cli/test_ollama_gpu_provider.py` | ✅ Active | GPU testing |
| `.github/workflows/cli-tests.yml` | ✅ Active | CI/CD for CLI tests (Python 3.11/3.12/3.13) |

### Home Scripts (`home/`)

| Path | Status | Notes |
|------|--------|-------|
| `home/client/` | ✅ Active | Client test scripts |
| `home/miner/` | ✅ Active | Miner test scripts |
| `home/quick_job.py` | ✅ Active | Quick job submission |
| `home/simple_job_flow.py` | ✅ Active | Job flow testing |

### Plugins (`plugins/`)

| Path | Status | Notes |
|------|--------|-------|
| `plugins/ollama/` | ✅ Active | Ollama integration |

### Development Utilities (`dev/`)

| Path | Status | Notes |
|------|--------|-------|
| `dev/` | ✅ Active | Development environment (reorganized, Mar 2026) |
| `dev/cli/` | ✅ Active | CLI development environment (moved from cli-dev, Mar 2026) |
| `dev/scripts/` | ✅ Active | Development scripts (79 Python files) |
| `dev/cache/` | ✅ Active | Development cache files |
| `dev/env/` | ✅ Active | Environment configurations |
| `dev/multi-chain/` | ✅ Active | Multi-chain development files |
| `dev/tests/` | ✅ Active | Development test files |

### Development Utilities (`dev-utils/`)

| Path | Status | Notes |
|------|--------|-------|
| `dev-utils/` | ✅ Active | Development utilities (legacy) |
| `dev-utils/aitbc-pythonpath.pth` | ✅ Active | Python path configuration |

### Data Directory (`data/`)

| Path | Status | Notes |
|------|--------|-------|
| `data/` | ✅ Active | Runtime data directory (gitignored) |
| `data/coordinator.db` | ⚠️ Runtime | SQLite database, moved from root |

### Root Files

| Path | Status | Notes |
|------|--------|-------|
| `README.md` | ✅ Active | Project readme, updated with standardization badges (Mar 2026) |
| `LICENSE` | ✅ Active | License file |
| `.gitignore` | ✅ Active | Recently updated (145 lines) |
| `pyproject.toml` | ✅ Active | Python project config |
| `.editorconfig` | ✅ Active | Editor config |
| `pytest.ini` | ✅ Active | Pytest configuration with custom markers |
| `CLEANUP_SUMMARY.md` | ✅ Active | Documentation of directory cleanup |
| `test_block_import.py` | ✅ Resolved | Moved to `tests/verification/test_block_import.py` |

### Backup Directory (`backup/`)

| Path | Status | Notes |
|------|--------|-------|
| `backup/` | ✅ Active | Backup archive storage (organized, Mar 2026) |
| `backup/explorer_backup_20260306_162316.tar.gz` | ✅ Active | Explorer TypeScript source backup (15.2 MB) |
| `backup/BACKUP_INDEX.md` | ✅ Active | Backup inventory and restoration instructions |

---

### Blockchain Node (`apps/blockchain-node/`)

| Path | Status | Notes |
|------|--------|-------|
| `apps/blockchain-node/` | ✅ Active | Blockchain node with PoA, mempool, sync (Stage 20/21/22 complete) |
| `apps/blockchain-node/src/aitbc_chain/mempool.py` | ✅ Active | Dual-backend mempool (memory + SQLite) |
| `apps/blockchain-node/src/aitbc_chain/sync.py` | ✅ Active | Chain sync with conflict resolution |
| `apps/blockchain-node/src/aitbc_chain/consensus/poa.py` | ✅ Active | PoA proposer with circuit breaker |
| `apps/blockchain-node/src/aitbc_chain/app.py` | ✅ Active | FastAPI app with rate limiting middleware |
| `apps/blockchain-node/tests/test_mempool.py` | ✅ Active | 27 mempool tests |
| `apps/blockchain-node/tests/test_sync.py` | ✅ Active | 23 sync tests |

### Smart Contracts (`contracts/`) 📜 **EXPANDED**

| Path | Status | Notes |
|------|--------|-------|
| `contracts/contracts/AIPowerRental.sol` | ✅ Active | Handles decentralized GPU/AI compute rentals |
| `contracts/contracts/AITBCPaymentProcessor.sol` | ✅ Active | AITBC token flow and automated settlements |
| `contracts/contracts/DisputeResolution.sol` | ✅ Active | Arbitration for OpenClaw marketplace disputes |
| `contracts/contracts/EscrowService.sol` | ✅ Active | Multi-signature execution escrow locks |
| `contracts/contracts/DynamicPricing.sol` | ✅ Active | Supply/Demand algorithmic pricing |
| `contracts/contracts/PerformanceVerifier.sol` | ✅ Active | On-chain ZK verification of AI inference quality |
| `contracts/contracts/AgentStaking.sol` | ✅ Active | Agent ecosystem reputation staking |
| `contracts/contracts/AgentBounty.sol` | ✅ Active | Crowdsourced task resolution logic |
| `contracts/contracts/ZKReceiptVerifier.sol` | ✅ Active | ZK receipt verifier contract |
| `contracts/contracts/BountyIntegration.sol` | ✅ Active | Cross-contract event handling |
| `contracts/AgentWallet.sol` | ✅ Active | Isolated agent-specific wallets |
| `contracts/AgentMemory.sol` | ✅ Active | IPFS CID anchoring for agent memory |
| `contracts/KnowledgeGraphMarket.sol` | ✅ Active | Shared knowledge graph marketplace |
| `contracts/MemoryVerifier.sol` | ✅ Active | ZK-proof verification for data retrieval |
| `contracts/CrossChainReputation.sol` | ✅ Active | Portable reputation scores |
| `contracts/AgentCommunication.sol` | ✅ Active | Secure agent messaging |
| `contracts/scripts/` | ✅ Active | Hardhat deployment & verification scripts |

---

## Future Placeholders 📋 (Keep - Will Be Populated)

These empty folders are intentional scaffolding for planned future work per the roadmap.

| Path | Status | Roadmap Stage |
|------|--------|---------------|
| `docs/user/guides/` | ✅ Complete | Stage 19 - Documentation (Q1 2026) |
| `docs/developer/tutorials/` | ✅ Complete | Stage 19 - Documentation (Q1 2026) |
| `docs/reference/specs/` | ✅ Complete | Stage 19 - Documentation (Q1 2026) |
| `infra/terraform/environments/staging/` | ✅ Complete | Stage 19 - Infrastructure (Q1 2026) |
| `infra/terraform/environments/prod/` | ✅ Complete | Stage 19 - Infrastructure (Q1 2026) |
| `infra/helm/values/dev/` | ✅ Complete | Stage 19 - Infrastructure (Q1 2026) |
| `infra/helm/values/staging/` | ✅ Complete | Stage 19 - Infrastructure (Q1 2026) |
| `infra/helm/values/prod/` | ✅ Complete | Stage 19 - Infrastructure (Q1 2026) |
| `apps/coordinator-api/migrations/` | ✅ Complete | Stage 19 - Application Components (Q1 2026) |
| `apps/pool-hub/src/app/routers/` | ✅ Complete | Stage 19 - Application Components (Q1 2026) |
| `apps/pool-hub/src/app/registry/` | ✅ Complete | Stage 19 - Application Components (Q1 2026) |
| `apps/pool-hub/src/app/scoring/` | ✅ Complete | Stage 19 - Application Components (Q1 2026) |

---

## Summary Statistics

| Category | Count | Status |
|----------|-------|--------|
| **Whitelist ✅** | ~85 items | Active and maintained (Mar 2026) |
| **Placeholders 📋** | 12 folders | All complete (Stage 19) |
| **Standardized Services** | 19+ services | 100% standardized (Mar 2026) |
| **Development Scripts** | 79 files | Organized in dev/scripts/ (Mar 2026) |
| **Deployment Scripts** | 35 files | Organized in scripts/deploy/ (Mar 2026) |
| **Documentation Files** | 200+ files | Updated and current (Mar 2026) |
| **Backup Archives** | 1+ files | Organized in backup/ (Mar 2026) |
| **Debug prints** | 17 statements | Replace with logger |

## Recent Major Updates (March 2026)

### ✅ Complete Infrastructure Standardization
- **19+ services** standardized to use `aitbc` user and `/opt/aitbc` paths
- **Duplicate services** removed and cleaned up
- **Service naming** conventions improved (e.g., GPU multimodal renamed)
- **All services** operational with 100% health score
- **Automated verification** tools implemented

### ✅ Enhanced Documentation
- **Infrastructure documentation** created and updated
- **Service monitoring workflow** implemented
- **Codebase verification script** developed
- **Project files documentation** updated to reflect current state

### ✅ Improved Organization
- **Development environment** reorganized into `dev/` structure
- **Scripts organized** by purpose (deploy, dev, testing)
- **Workflows documented** for repeatable processes
- **File organization prevention** system implemented

### ✅ CLI Development Environment Optimization (March 6, 2026)
- **CLI development tools** moved from `cli-dev` to `dev/cli`
- **Centralized development** environment in unified `/dev/` structure
- **Improved project organization** with reduced root-level clutter
- **Backup system** implemented with proper git exclusion

### ✅ Explorer Architecture Simplification (March 6, 2026)
- **TypeScript explorer** merged into Python blockchain-explorer
- **Agent-first architecture** strengthened with single service
- **Source code deleted** with proper backup (15.2 MB archive)
- **Documentation updated** across all reference files

---

## Folder Structure Recommendation

```
aitbc/
├── apps/                    # Core applications
│   ├── coordinator-api/     # ✅ Keep - Standardized (Mar 2026)
│   ├── explorer-web/        # ✅ Keep
│   ├── marketplace-web/     # ✅ Keep
│   ├── trade-exchange/      # ✅ Keep
│   ├── blockchain-node/     # ✅ Keep - Standardized (Mar 2026)
│   ├── blockchain-explorer/ # ✅ Keep - Standardized (Mar 2026)
│   └── zk-circuits/         # ✅ Keep
├── cli/                     # ✅ CLI tools
├── contracts/               # ✅ Smart contracts
├── dev/                     # ✅ Development environment (Mar 2026)
│   ├── cli/                 # ✅ CLI development environment (moved Mar 2026)
│   ├── scripts/             # Development scripts (79 files)
│   ├── cache/               # Development cache
│   ├── env/                 # Environment configs
│   ├── multi-chain/         # Multi-chain files
│   └── tests/               # Development tests
├── backup/                  # ✅ Backup archive storage (Mar 2026)
│   ├── explorer_backup_*.tar.gz  # Application backups
│   └── BACKUP_INDEX.md      # Backup inventory
├── docs/                    # ✅ Numbered documentation structure
│   ├── infrastructure/      # ✅ Infrastructure docs (Mar 2026)
│   ├── 0_getting_started/   # Getting started guides
│   ├── 1_project/           # Project management
│   ├── 2_clients/           # Client documentation
│   ├── 3_miners/            # Miner documentation
│   ├── 4_blockchain/        # Blockchain documentation
│   ├── 5_reference/         # Reference materials
│   ├── 6_architecture/      # Architecture documentation
│   ├── 7_deployment/        # Deployment guides
│   ├── 8_development/       # Development documentation
│   ├── 9_security/          # Security documentation
│   └── 10_plan/             # Planning documentation
├── extensions/              # ✅ Browser extensions (Firefox wallet)
├── infra/                   # ✅ Infrastructure configs
│   ├── k8s/                 # Kubernetes manifests
│   └── nginx/               # Nginx configurations
├── packages/                # ✅ Shared libraries
│   ├── py/aitbc-crypto/     # Cryptographic primitives
│   ├── py/aitbc-sdk/        # Python SDK
│   └── solidity/aitbc-token/# ERC-20 token contract
├── plugins/                 # ✅ Keep (ollama)
├── scripts/                 # ✅ Keep - organized by purpose
│   ├── deploy/              # ✅ Deployment scripts (35 files)
│   ├── dev/                 # ✅ Development scripts
│   └── testing/             # ✅ Test scripts
├── systemd/                 # ✅ Systemd service units (19+ files)
├── tests/                   # ✅ Test suites
├── website/                 # ✅ Public website and HTML docs
├── dev-utils/               # ✅ Development utilities (legacy)
├── data/                    # ✅ Runtime data (gitignored)
├── .windsurf/               # ✅ Keep - Workflows (Mar 2026)
└── config/                  # ✅ Configuration files
```

This structure represents the current clean state of the AITBC repository with all essential components organized for optimal development and deployment workflows. The March 2026 standardization effort has resulted in:

- **100% service standardization** across all systemd services
- **Improved file organization** with proper dev/ structure
- **Enhanced documentation** with comprehensive infrastructure guides
- **Automated verification tools** for maintaining standards
- **Production-ready infrastructure** with all services operational
- **Optimized CLI development** with centralized dev/cli environment
- **Agent-first architecture** with simplified explorer service
- **Comprehensive backup system** with proper git exclusion

**Note**: Redundant `apps/logs/` directory removed - central `logs/` directory at root level is used for all logging. Redundant `assets/` directory removed - Firefox extension assets are properly organized in `extensions/aitbc-wallet-firefox/`. CLI development environment moved from `cli-dev` to `dev/cli` for better organization. Explorer TypeScript source merged into Python service and backed up.
