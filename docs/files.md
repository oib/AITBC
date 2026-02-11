# AITBC Repository File Audit

This document categorizes all files and folders in the repository by their status:
- **Whitelist (✅)**: Active, up-to-date, essential
- **Greylist (⚠️)**: Uncertain status, may need review
- **Blacklist (❌)**: Legacy, unused, outdated, candidates for removal

Last updated: 2026-02-11

---

## Whitelist ✅ (Active & Essential)

### Core Applications (`apps/`)

| Path | Status | Notes |
|------|--------|-------|
| `apps/coordinator-api/` | ✅ Active | Main API service, recently updated (Jan 2026) |
| `apps/explorer-web/` | ✅ Active | Blockchain explorer, recently updated |
| `apps/wallet-daemon/` | ✅ Active | Wallet service, deployed in production |
| `apps/trade-exchange/` | ✅ Active | Bitcoin exchange, deployed |
| `apps/zk-circuits/` | ✅ Active | ZK proof circuits, deployed |
| `apps/marketplace-web/` | ✅ Active | Marketplace frontend, deployed |

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
| `docs/done.md` | ✅ Active | Completion tracking |
| `docs/roadmap.md` | ✅ Active | Development roadmap |
| `docs/developer/testing/localhost-testing-scenario.md` | ✅ Active | Testing guide |
| `docs/reference/components/miner_node.md` | ✅ Active | Miner documentation |
| `docs/reference/components/coordinator_api.md` | ✅ Active | API documentation |
| `docs/developer/integration/skills-framework.md` | ✅ Active | Skills documentation |
| `docs/guides/` | ✅ Active | Development guides (moved from root) |
| `docs/reports/` | ✅ Active | Generated reports (moved from root) |

### CLI Tools (`cli/`)

| Path | Status | Notes |
|------|--------|-------|
| `cli/client.py` | ✅ Active | Client CLI |
| `cli/miner.py` | ✅ Active | Miner CLI |
| `cli/wallet.py` | ✅ Active | Wallet CLI |
| `cli/test_ollama_gpu_provider.py` | ✅ Active | GPU testing |

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
| `README.md` | ✅ Active | Project readme, updated with new structure |
| `LICENSE` | ✅ Active | License file |
| `.gitignore` | ✅ Active | Recently updated (145 lines) |
| `pyproject.toml` | ✅ Active | Python project config |
| `.editorconfig` | ✅ Active | Editor config |
| `pytest.ini` | ✅ Active | Pytest configuration with custom markers |
| `CLEANUP_SUMMARY.md` | ✅ Active | Documentation of directory cleanup |
| `test_block_import.py` | ⚠️ Duplicate | Recreated in root (exists in scripts/testing/) |

---

## Greylist ⚠️ (Needs Review)

### Applications - Uncertain Status

| Path | Status | Notes |
|------|--------|-------|
| `apps/blockchain-node/` | 📋 Planned | Has code, SQLModel issues - see roadmap Stage 20 |

### Packages

| Path | Status | Notes |
|------|--------|-------|
| `packages/solidity/aitbc-token/` | 📋 Planned | Smart contracts, deployment planned - see roadmap Stage 20 |

### Scripts

| Path | Status | Notes |
|------|--------|-------|
| `scripts/test/` | ✅ Keep | 7 test scripts, all current (Jan 2026) |

### Documentation

| Path | Status | Notes |
|------|--------|-------|
| `docs/developer/` | ✅ Keep | 6 markdown files |
| `docs/operator/` | ✅ Keep | 5 markdown files |
| `docs/user/` | ✅ Keep | 1 markdown file |
| `docs/tutorials/` | ✅ Keep | 3 markdown files |

### Infrastructure

| Path | Status | Notes |
|------|--------|-------|
| `infra/k8s/` | ✅ Keep | 5 yaml files (backup, cert-manager, netpol, sealed-secrets) |

### Extensions

| Path | Status | Notes |
|------|--------|-------|
| `extensions/aitbc-wallet-firefox/` | ✅ Keep | Firefox extension source (7 files) |
| `extensions/aitbc-wallet-firefox-v1.0.5.xpi` | ✅ Keep | Built extension package |

### Other

| Path | Status | Notes |
|------|--------|-------|
| `contracts/ZKReceiptVerifier.sol` | 📋 Planned | ZK verifier contract - see roadmap Stage 20 |
| `docs/reference/specs/receipt-spec.md` | ✅ Keep | Canonical receipt schema (moved from protocols/) |

---

## Future Placeholders 📋 (Keep - Will Be Populated)

These empty folders are intentional scaffolding for planned future work per the roadmap.

| Path | Status | Roadmap Stage |
|------|--------|---------------|
| `docs/user/guides/` | 📋 Placeholder | Stage 5 - Documentation |
| `docs/developer/tutorials/` | 📋 Placeholder | Stage 5 - Documentation |
| `docs/reference/specs/` | 📋 Placeholder | Stage 5 - Documentation |
| `infra/terraform/environments/staging/` | 📋 Placeholder | Stage 5 - Infrastructure |
| `infra/terraform/environments/prod/` | 📋 Placeholder | Stage 5 - Infrastructure |
| `infra/helm/values/dev/` | 📋 Placeholder | Stage 5 - Infrastructure |
| `infra/helm/values/staging/` | 📋 Placeholder | Stage 5 - Infrastructure |
| `infra/helm/values/prod/` | 📋 Placeholder | Stage 5 - Infrastructure |
| `apps/coordinator-api/migrations/` | 📋 Placeholder | Alembic migrations |
| `apps/pool-hub/src/app/routers/` | 📋 Placeholder | Stage 3 - Pool Hub |
| `apps/pool-hub/src/app/registry/` | 📋 Placeholder | Stage 3 - Pool Hub |
| `apps/pool-hub/src/app/scoring/` | 📋 Placeholder | Stage 3 - Pool Hub |

---

## Blacklist ❌ (Abandoned - Remove)

### Abandoned Empty Folders (Created but never used)

| Path | Status | Notes |
|------|--------|-------|
| `apps/client-web/src/` | ❌ Remove | Created Sep 2025, never implemented |
| `apps/client-web/public/` | ❌ Remove | Created Sep 2025, never implemented |
| `apps/marketplace-ui/` | ❌ Remove | Superseded by `marketplace-web` |
| `apps/wallet-cli/` | ❌ Remove | Superseded by `cli/wallet.py` |
| `packages/py/aitbc-core/src/` | ❌ Remove | Created Sep 2025, never implemented |
| `packages/py/aitbc-p2p/src/` | ❌ Remove | Created Sep 2025, never implemented |
| `packages/py/aitbc-scheduler/src/` | ❌ Remove | Created Sep 2025, never implemented |
| `packages/js/ui-widgets/src/` | ❌ Remove | Created Sep 2025, never implemented |
| `protocols/api/` | ❌ Remove | Never implemented |
| `protocols/payouts/` | ❌ Remove | Never implemented |
| `data/fixtures/` | ❌ Remove | Never populated |
| `data/samples/` | ❌ Remove | Never populated |
| `tools/mkdiagram/` | ❌ Remove | Never implemented |
| `examples/quickstart-client-python/` | ❌ Remove | Never implemented |
| `examples/quickstart-client-js/node/` | ❌ Remove | Never implemented |
| `examples/quickstart-client-js/browser/` | ❌ Remove | Never implemented |
| `examples/receipts-sign-verify/python/` | ❌ Remove | Never implemented |
| `examples/receipts-sign-verify/js/` | ❌ Remove | Never implemented |
| `scripts/env/` | ❌ Remove | Never populated |
| `windsurf/prompts/` | ❌ Remove | Superseded by `.windsurf/` |
| `windsurf/tasks/` | ❌ Remove | Superseded by `.windsurf/` |

### Duplicate/Redundant Folders

| Path | Status | Notes |
|------|--------|-------|
| `python-sdk/` | ❌ Duplicate | Duplicates `packages/py/aitbc-sdk/` |
| `windsurf/` | ❌ Duplicate | Superseded by `.windsurf/` |
| `configs/` | ❌ Duplicate | Empty subfolders, duplicates `infra/` and `systemd/` |
| `docs/user-guide/` | ❌ Duplicate | Duplicates `docs/user/` |

### Ecosystem Folders (Scaffolded but Unused)

| Path | Status | Notes |
|------|--------|-------|
| `ecosystem/` | ❌ Unused | Only has empty `academic/` subfolder |
| `ecosystem-analytics/` | ❌ Unused | Scaffolded Dec 2025, never used |
| `ecosystem-certification/` | ❌ Unused | Scaffolded Dec 2025, never used |
| `ecosystem-extensions/` | ❌ Unused | Only has template folder |
| `enterprise-connectors/` | ❌ Unused | Scaffolded Dec 2025, never used |

### Research Folders (Scaffolded but Unused)

| Path | Status | Notes |
|------|--------|-------|
| `research/autonomous-agents/` | ❌ Unused | Scaffolded, no active work |
| `research/consortium/` | ❌ Unused | Scaffolded, no active work |
| `research/prototypes/` | ❌ Unused | Scaffolded, no active work |
| `research/standards/` | ❌ Unused | Scaffolded, no active work |

### Generated/Build Artifacts (Should be in .gitignore)

| Path | Status | Notes |
|------|--------|-------|
| `packages/solidity/aitbc-token/typechain-types/` | ❌ Generated | Build artifact |
| `apps/explorer-web/dist/` | ❌ Generated | Build artifact |
| `logs/` | ❌ Generated | Runtime logs |

---

## Issues Found (2026-02-11)

### Empty Directories (Delete)

| Path | Action |
|------|--------|
| `apps/blockchain-node/src/aitbc_chain/ledger/` | Delete — empty placeholder, never implemented |
| `apps/blockchain-node/src/aitbc_chain/mempool/` | Delete — empty dir, mempool logic is in `mempool.py` |
| `apps/coordinator-api/src/app/ws/` | Delete — empty WebSocket placeholder, never implemented |
| `apps/explorer-web/public/js/components/` | Delete — empty, TS components are in `src/components/` |
| `apps/explorer-web/public/js/pages/` | Delete — empty, TS pages are in `src/pages/` |
| `apps/explorer-web/public/js/vendors/` | Delete — empty vendor dir |
| `apps/explorer-web/public/assets/` | Delete — empty assets dir |
| `packages/py/aitbc-crypto/build/bdist.linux-x86_64/` | Delete — build artifact |

### Files in Wrong Location (Move)

| Current Path | Correct Path | Reason |
|-------------|-------------|--------|
| `apps/coordinator-api/coordinator.db` | gitignored / `data/` | SQLite database should not be in git |
| `apps/coordinator-api/.env` | gitignored | Environment file with secrets, should not be in git |
| `apps/.service_pids` | gitignored | Runtime PID file, should not be in git |
| `src/aitbc_chain/` | `apps/blockchain-node/src/aitbc_chain/` | Duplicate/stale copy of blockchain node source |
| `website/docs-clients.html` | `website/docs/docs-clients.html` | Inconsistent location, duplicate of file in `docs/` |
| `website/docs-developers.html` | `website/docs/docs-developers.html` | Inconsistent location, duplicate of file in `docs/` |
| `website/docs-miners.html` | `website/docs/docs-miners.html` | Inconsistent location, duplicate of file in `docs/` |
| `website/docs-index.html` | `website/docs/index.html` | Inconsistent location, duplicate of file in `docs/` |

### Legacy Files (Delete)

| Path | Reason |
|------|--------|
| `SECURITY_CLEANUP_GUIDE.md` | One-time cleanup guide, already completed |
| `apps/trade-exchange/index_working.html` | Backup copy of `index.html` |
| `apps/trade-exchange/index.prod.html` | Superseded by `build.py` production build |
| `apps/trade-exchange/index.real.html` | Superseded by `build.py` production build |
| `tests/conftest_fixtures.py` | Unused alternate conftest |
| `tests/conftest_full.py` | Unused alternate conftest |
| `tests/conftest_path.py` | Unused alternate conftest |
| `tests/pytest_simple.ini` | Duplicate of root `pytest.ini` |
| `tests/test_blockchain_simple.py` | Superseded by `test_blockchain_nodes.py` |
| `tests/test_blockchain_final.py` | Superseded by `test_blockchain_nodes.py` |
| `tests/test_discovery.py` | One-time discovery script |
| `tests/test_windsurf_integration.py` | IDE-specific test, not for GitHub |
| `scripts/exchange-router-fixed.py` | One-time fix script |
| `scripts/start_mock_blockchain.sh` | Superseded by `tests/mock_blockchain_node.py` |
| `apps/marketplace-web/src/counter.ts` | Vite template boilerplate, unused |
| `apps/marketplace-web/src/typescript.svg` | Vite template boilerplate, unused |
| `apps/marketplace-web/public/vite.svg` | Vite template boilerplate, unused |
| `.vscode/` | IDE-specific, should be gitignored |

### Debug Print Statements (Replace with logging)

| File | Lines | Statement |
|------|-------|-----------|
| `apps/coordinator-api/src/app/routers/exchange.py` | 112 | `print(f"Error minting tokens: {e}")` |
| `apps/coordinator-api/src/app/routers/governance.py` | 352-376 | 4x `print(f"Executing ...")` |
| `apps/coordinator-api/src/app/services/receipts.py` | 132 | `print(f"Failed to generate ZK proof: {e}")` |
| `apps/coordinator-api/src/app/services/blockchain.py` | 47 | `print(f"Error getting balance: {e}")` |
| `apps/coordinator-api/src/app/services/bitcoin_wallet.py` | 34-134 | 8x `print(...)` debug statements |
| `apps/coordinator-api/src/app/storage/db_pg.py` | 206 | `print("✅ PostgreSQL database initialized successfully!")` |

---

## Summary Statistics

| Category | Count | Action |
|----------|-------|--------|
| **Whitelist ✅** | ~60 items | Keep and maintain |
| **Greylist ⚠️** | 0 items | All resolved |
| **Placeholders 📋** | 12 folders | Fill per roadmap |
| **Removed ❌** | 35 items | Cleaned up 2026-01-24 |
| **Empty dirs** | 8 dirs | Delete |
| **Misplaced files** | 8 files | Move or gitignore |
| **Legacy files** | 18 files | Delete |
| **Debug prints** | 17 statements | Replace with logger |

### Completed Actions (2026-01-24)

1. **Cleanup Done**:
   - ✅ Removed 21 abandoned/duplicate folders
   - ✅ Updated `.gitignore` with comprehensive rules
   - ✅ Created this audit document

2. **Additional Cleanup (2026-01-24)**:
   - ✅ Removed `apps/miner-node/` (superseded by `scripts/gpu/`)
   - ✅ Removed `apps/miner-dashboard/` (superseded by `website/dashboards/`)
   - ✅ Removed `docs/bootstrap/` (empty)
   - ✅ Removed 5 GPU miner variants (kept only `gpu_miner_host.py`)
   - ✅ Removed 3 extension variants (kept only `aitbc-wallet-firefox/`)

3. **Final Cleanup (2026-01-24)**:
   - ✅ Removed `api/` folder (mock no longer needed - using live production)
   - ✅ Removed `governance/` folder (too far in future)
   - ✅ Removed `protocols/` folder (spec moved to docs/reference/specs/)
   - ✅ Moved `protocols/receipts/spec.md` → `docs/reference/specs/receipt-spec.md`
   - ✅ Added ZKReceiptVerifier and receipt spec to roadmap Stage 20

4. **Placeholder Plan** (see `roadmap.md` Stage 19):
   - Q1 2026: Documentation folders (`docs/user/guides/`, `docs/developer/tutorials/`, `docs/reference/specs/`)
   - Q2 2026: Infrastructure (`infra/terraform/`, `infra/helm/`)
   - Q2 2026: Pool Hub components

5. **Directory Organization (2026-01-29)**:
   - ✅ Created `docs/guides/` and moved 2 guide files from root
   - ✅ Created `docs/reports/` and moved 10 report files from root
   - ✅ Created `scripts/testing/` and moved 13 test scripts from root
   - ✅ Created `dev-utils/` and moved `aitbc-pythonpath.pth`
   - ✅ Moved `coordinator.db` to `data/` directory
   - ✅ Updated README.md with new structure
   - ✅ Created index README files for new directories

---

## Folder Structure Recommendation

```
aitbc/
├── apps/                    # Core applications
│   ├── coordinator-api/     # ✅ Keep
│   ├── explorer-web/        # ✅ Keep
│   ├── marketplace-web/     # ✅ Keep
│   ├── wallet-daemon/       # ✅ Keep
│   └── zk-circuits/         # ✅ Keep
├── cli/                     # ✅ CLI tools
├── docs/                    # ✅ Markdown documentation
│   ├── guides/              # Development guides
│   └── reports/             # Generated reports
├── infra/                   # ✅ Infrastructure configs
├── packages/                # ✅ Keep (aitbc-crypto, aitbc-sdk, aitbc-token)
├── plugins/                 # ✅ Keep (ollama)
├── scripts/                 # ✅ Keep - organized
│   └── testing/             # Test scripts
├── systemd/                 # ✅ Keep
├── tests/                   # ✅ Keep (e2e, integration, unit, security, load)
├── website/                 # ✅ Keep
├── dev-utils/               # ✅ Development utilities
├── data/                    # ✅ Runtime data (gitignored)
└── .windsurf/               # ✅ Keep
```

**Folders Removed (2026-01-24)**:
- ✅ `ecosystem*/` (all 4 folders) - removed
- ✅ `enterprise-connectors/` - removed
- ✅ `research/` - removed
- ✅ `python-sdk/` - removed (duplicate)
- ✅ `windsurf/` - removed (duplicate of `.windsurf/`)
- ✅ `configs/` - removed (duplicated `infra/`)
- ✅ Empty `apps/` subfolders - removed (client-web, marketplace-ui, wallet-cli)
- ✅ Empty `packages/` subfolders - removed (aitbc-core, aitbc-p2p, aitbc-scheduler, ui-widgets)
- ✅ Empty `examples/` subfolders - removed
- ✅ `tools/` - removed (empty)
- ✅ `docs/user-guide/` - removed (duplicate)
