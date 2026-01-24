# AITBC Repository File Audit

This document categorizes all files and folders in the repository by their status:
- **Whitelist (✅)**: Active, up-to-date, essential
- **Greylist (⚠️)**: Uncertain status, may need review
- **Blacklist (❌)**: Legacy, unused, outdated, candidates for removal

Last updated: 2026-01-24

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

### Cascade Skills (`.windsurf/`)

| Path | Status | Notes |
|------|--------|-------|
| `.windsurf/skills/blockchain-operations/` | ✅ Active | Node management skill |
| `.windsurf/skills/deploy-production/` | ✅ Active | Deployment skill |
| `.windsurf/workflows/` | ✅ Active | Workflow definitions |

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

### Root Files

| Path | Status | Notes |
|------|--------|-------|
| `README.md` | ✅ Active | Project readme |
| `LICENSE` | ✅ Active | License file |
| `.gitignore` | ✅ Active | Recently updated (145 lines) |
| `pyproject.toml` | ✅ Active | Python project config |
| `.editorconfig` | ✅ Active | Editor config |

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

## Summary Statistics

| Category | Count | Action |
|----------|-------|--------|
| **Whitelist ✅** | ~60 items | Keep and maintain |
| **Greylist ⚠️** | 0 items | All resolved! |
| **Placeholders 📋** | 12 folders | Fill per roadmap Stage 19 |
| **Removed ❌** | 35 items | Cleaned up 2026-01-24 |

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
├── infra/                   # ✅ Infrastructure configs
├── packages/                # ✅ Keep (aitbc-crypto, aitbc-sdk, aitbc-token)
├── plugins/                 # ✅ Keep (ollama)
├── scripts/                 # ✅ Keep - organized
├── systemd/                 # ✅ Keep
├── tests/                   # ✅ Keep (e2e, integration, unit, security, load)
├── website/                 # ✅ Keep
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
