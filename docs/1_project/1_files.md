# AITBC Repository File Structure

This document describes the current organization and status of files and folders in the repository.

Last updated: 2026-02-22

---

## Whitelist ✅ (Active & Essential)

### Core Applications (`apps/`)

| Path | Status | Notes |
|------|--------|-------|
| `apps/coordinator-api/` | ✅ Active | Main API service, recently updated (Feb 2026) |
| `apps/explorer-web/` | ✅ Active | Blockchain explorer, recently updated |
| `apps/wallet-daemon/` | ✅ Active | Wallet service, deployed in production |
| `apps/trade-exchange/` | ✅ Active | Bitcoin exchange, deployed |
| `apps/zk-circuits/` | ✅ Active | ZK proof circuits, deployed |
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
| `scripts/gpu/gpu_miner_host.py` | ✅ Active | Production GPU miner |
| `scripts/gpu/gpu_miner_host_wrapper.sh` | ✅ Active | Systemd wrapper |
| `scripts/deploy/` | ✅ Active | Deployment scripts |
| `scripts/service/` | ✅ Active | Service management |
| `scripts/dev_services.sh` | ✅ Active | Local development |
| `scripts/testing/` | ✅ Active | Test scripts (moved from root, 13 files) |

### Infrastructure (`infra/`, `systemd/`)

| Path | Status | Notes |
|------|--------|-------|
| `infra/nginx/` | ✅ Active | Production nginx configs |
| `systemd/aitbc-host-gpu-miner.service` | ✅ Active | Production service |
| `systemd/coordinator-api.service` | ✅ Active | Production service |

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
| `docs/0_getting_started/` | ✅ Active | Getting started guides |
| `docs/2_clients/` | ✅ Active | Client documentation |
| `docs/3_miners/` | ✅ Active | Miner documentation |
| `docs/4_blockchain/` | ✅ Active | Blockchain documentation |
| `docs/5_reference/` | ✅ Active | Reference materials |
| `docs/6_architecture/` | ✅ Active | Architecture documentation |
| `docs/7_deployment/` | ✅ Active | Deployment guides |
| `docs/8_development/` | ✅ Active | Development documentation |
| `docs/9_security/` | ✅ Active | Security documentation |

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
| `.github/workflows/cli-tests.yml` | ✅ Active | CI/CD for CLI tests (Python 3.10/3.11/3.12) |

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

### Development Utilities (`dev-utils/`)

| Path | Status | Notes |
|------|--------|-------|
| `dev-utils/` | ✅ Active | Development utilities (newly created) |
| `dev-utils/aitbc-pythonpath.pth` | ✅ Active | Python path configuration |

### Data Directory (`data/`)

| Path | Status | Notes |
|------|--------|-------|
| `data/` | ✅ Active | Runtime data directory (gitignored) |
| `data/coordinator.db` | ⚠️ Runtime | SQLite database, moved from root |

### Root Files

| Path | Status | Notes |
|------|--------|-------|
| `README.md` | ✅ Active | Project readme, streamlined for idea/overview |
| `LICENSE` | ✅ Active | License file |
| `.gitignore` | ✅ Active | Recently updated (145 lines) |
| `pyproject.toml` | ✅ Active | Python project config |
| `.editorconfig` | ✅ Active | Editor config |
| `pytest.ini` | ✅ Active | Pytest configuration with custom markers |
| `CLEANUP_SUMMARY.md` | ✅ Active | Documentation of directory cleanup |
| `test_block_import.py` | ✅ Resolved | Moved to `tests/verification/test_block_import.py` |

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

### Smart Contracts (`contracts/`)

| Path | Status | Notes |
|------|--------|-------|
| `contracts/ZKReceiptVerifier.sol` | ✅ Active | ZK receipt verifier contract |
| `contracts/Groth16Verifier.sol` | ✅ Active | Groth16 verifier stub (snarkjs-replaceable) |
| `contracts/scripts/security-analysis.sh` | ✅ Active | Slither + Mythril analysis script |
| `contracts/scripts/deploy-testnet.sh` | ✅ Active | Testnet deployment script |

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
| **Whitelist ✅** | ~60 items | Active and maintained |
| **Placeholders 📋** | 12 folders | All complete (Stage 19) |
| **Debug prints** | 17 statements | Replace with logger |

---

## Folder Structure Recommendation

```
aitbc/
├── apps/                    # Core applications
│   ├── coordinator-api/     # ✅ Keep
│   ├── explorer-web/        # ✅ Keep
│   ├── marketplace-web/     # ✅ Keep
│   ├── trade-exchange/      # ✅ Keep
│   ├── wallet-daemon/       # ✅ Keep
│   ├── blockchain-node/     # ✅ Keep
│   └── zk-circuits/         # ✅ Keep
├── cli/                     # ✅ CLI tools
├── contracts/               # ✅ Smart contracts
├── docs/                    # ✅ Numbered documentation structure
│   ├── 0_getting_started/   # Getting started guides
│   ├── 1_project/           # Project management
│   ├── 2_clients/           # Client documentation
│   ├── 3_miners/            # Miner documentation
│   ├── 4_blockchain/        # Blockchain documentation
│   ├── 5_reference/         # Reference materials
│   ├── 6_architecture/      # Architecture documentation
│   ├── 7_deployment/        # Deployment guides
│   ├── 8_development/       # Development documentation
│   └── 9_security/          # Security documentation
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
├── systemd/                 # ✅ Systemd service units
├── tests/                   # ✅ Test suites
├── website/                 # ✅ Public website and HTML docs
├── dev-utils/               # ✅ Development utilities
├── data/                    # ✅ Runtime data (gitignored)
└── .windsurf/               # ✅ Keep
```

This structure represents the current clean state of the AITBC repository with all essential components organized for optimal development and deployment workflows.

**Note**: Redundant `apps/logs/` directory removed - central `logs/` directory at root level is used for all logging. Redundant `assets/` directory removed - Firefox extension assets are properly organized in `extensions/aitbc-wallet-firefox/`.
