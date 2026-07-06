# v0.10.7 — Agent Task Assignment

**Last Updated**: 2026-07-06
**Version**: 1.0 — Initial plan from dead code and duplicate code scan

**Release Theme**: Dead Code Elimination (coordinator-api + agent-management) & Duplicate Consolidation — Delete ~5,800 lines of dead code (coordinator-api never-integrated modules, dead classes, dead re-export shims), collapse agent-management services onto coordinator-api's agent_coordination context (~4,800 lines), and consolidate high-impact duplicates (blockchain RPC clients, CLI error handling, DB init, config classes, security utils, health endpoints, CORS setup).

**Goal**: Eliminate dead code identified by vulture static analysis and consolidate duplicate code identified by targeted duplicate detection. This is a mechanical cleanup release following v0.10.6's more complex Decimal migration and performance fixes.

> **Scope**: 45 tasks across 13 categories. All P2 (dead code deletion) and P3 (duplicate consolidation) findings from the comprehensive codebase scan.

> **Prerequisites**: [v0.10.6](../v0.10.6/change.log) (in progress — dead code elimination, Decimal migration completion, duplicate consolidation).

> **Risk**: Medium. Dead code deletion is mechanical and low-risk. Duplicate consolidation requires careful testing of the consolidated implementations. The agent-management collapse requires deciding whether to deprecate the service entirely or keep it as a thin wrapper. Mitigated by: (1) comprehensive test suite, (2) incremental task completion with verification at each step, (3) git history for rollback.

---

## Task Split Overview

| Agent | Capability | Tasks | Focus |
|-------|------------|-------|-------|
| **Agent A** | SWE 1.6 (fast mechanical tasks) | 5 items | Dead code deletion (coordinator-api modules, CLI migration service, aitbc/ shims, dead classes, orphan tests) |
| **Agent B** | GLM 5.2 (complex tasks) | 8 items | Duplicate consolidation (agent-management collapse, blockchain RPC client, CLI error handling, DB init, config classes, security utils, small copy-pastes, Decimal gap fix) |

**Conflict boundary**: Agent A owns all dead code deletion (mechanical, no business logic). Agent B owns all duplicate consolidation (requires understanding of business logic, API compatibility, and service architecture). No coordination required — tasks are independent.

**Rationale**: SWE 1.6 excels at fast, mechanical code changes (deletion, grep verification, test cleanup). GLM 5.2 handles complex tasks requiring deeper understanding of API compatibility, service architecture, and business logic (agent-management collapse, shared client design, config inheritance).

---

## Agent A — Dead Code Elimination (SWE 1.6)

**Scope**: Delete dead modules, dead classes, dead re-export shims, and orphan tests. Simple, mechanical code changes that don't require deep business logic understanding.

**Working directory**: `/opt/aitbc/`

**Verification command**:
```bash
cd /opt/aitbc && ./venv/bin/python -m ruff check . && ./venv/bin/python -m pytest tests/unit -q -o addopts=""
```

### Tasks

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| A1 | Delete 11 dead coordinator-api modules (~4,800 lines) | 🟡 P2 | coordinator-api contexts: trading/amm, agent_coordination/portfolio, reputation/cross_chain_aggregator, infrastructure/distributed_framework, repositories/confidential, marketplace/marketplace_enhanced*, marketplace/marketplace_cache_optimizer, marketplace/marketplace_scaler, utils/cache_management | ✅ |
| A2 | Delete dead CLI migration service (~313 lines) | 🟡 P2 | `cli/utils/wallet_migration_service.py` | ✅ |
| A3 | Delete 5 dead aitbc/ re-export shims (~300 lines) | 🟡 P2 | `aitbc/access_control.py`, `aitbc/crypto/password.py`, `aitbc/security_hardening.py`, `aitbc/metrics.py`, `aitbc/log_utils/logging.py` (confirm with AGENTS.md first) | ✅ (4/5 — `log_utils/logging.py` kept per AGENTS.md) |
| A4 | Delete dead classes in live files (~1,000 lines) | 🟡 P2 | `TaskDecompositionEngine`, `EthereumBridge`, `MockHSMStorage`, `HSMProviderInterface`, `AutoOptimizer`, `ModalityOptimizationManager`, `RedisMessageBroker`, `WebSocketHandler`, `QuotaMiddleware` | ✅ |
| A5 | Delete orphan tests for dead modules | 🟡 P2 | tests for deleted modules + `tests/test_access_control.py`, `tests/test_metrics.py`, `tests/test_imports.py` (if those shims are deleted) | ✅ |

### Agent A — Detailed Instructions

#### A1: Delete 11 dead coordinator-api modules

**Files** (all verified to have zero importers via grep and package `__init__.py` checks):

1. `apps/coordinator-api/src/app/contexts/trading/services/trading_marketplace/amm.py` (519 lines)
2. `apps/coordinator-api/src/app/contexts/agent_coordination/services/portfolio.py` (413 lines)
3. `apps/coordinator-api/src/app/contexts/reputation/services/cross_chain_aggregator.py` (360 lines)
4. `apps/coordinator-api/src/app/contexts/infrastructure/services/distributed_framework.py` (360 lines)
5. `apps/coordinator-api/src/app/repositories/confidential.py` (337 lines)
6. `apps/coordinator-api/src/app/contexts/marketplace/services/marketplace_enhanced.py` (273 lines)
7. `apps/coordinator-api/src/app/contexts/governance/services/dao_governance_service.py` (252 lines)
8. `apps/coordinator-api/src/app/contexts/marketplace/services/marketplace_cache_optimizer.py` (206 lines)
9. `apps/coordinator-api/src/app/contexts/marketplace/services/marketplace_scaler.py` (204 lines)
10. `apps/coordinator-api/src/app/contexts/marketplace/services/marketplace_enhanced_simple.py` (203 lines)
11. `apps/coordinator-api/src/app/utils/cache_management.py` (203 lines)

**Verification** (run before deleting):
```bash
# Each module should show zero importers outside itself
for mod in trading_marketplace/amm agent_coordination/portfolio reputation/cross_chain_aggregator infrastructure/distributed_framework repositories/confidential marketplace/marketplace_enhanced marketplace/marketplace_enhanced_simple marketplace/marketplace_scaler marketplace/marketplace_cache_optimizer governance/dao_governance_service utils/cache_management; do
  echo "=== $mod ==="
  grep -rln "from.*$mod\|import.*$mod" --include="*.py" apps/coordinator-api/src | grep -v "$mod.py" | head
done
# Expected: no output for any module (all are dead)
```

**Fix**: Delete all 11 files. Also remove any commented-out imports in package `__init__.py` files that reference these modules.

**Note**: The `repositories/confidential.py` import in `models/__init__.py` is already commented out (line 72). Remove the comment as well.

#### A2: Delete dead CLI migration service

**File**: `cli/utils/wallet_migration_service.py` (313 lines)

**Evidence**: `WalletMigrationService` is only mentioned in `cli/FILE_ORGANIZATION_SUMMARY.md` (a docs file). No production code imports it.

**Verification**:
```bash
grep -rln "wallet_migration_service\|WalletMigrationService" --include="*.py" cli | grep -v "wallet_migration_service.py"
# Expected: no output
```

**Fix**: Delete `cli/utils/wallet_migration_service.py`.

#### A3: Delete 5 dead aitbc/ re-export shims

**Files**:
1. `aitbc/access_control.py` (~50 lines) — only `tests/test_access_control.py` + old docs import it
2. `aitbc/crypto/password.py` (~20 lines) — zero importers
3. `aitbc/security_hardening.py` (~30 lines) — docs only
4. `aitbc/metrics.py` (~157 lines) — only `tests/test_metrics.py`
5. `aitbc/log_utils/logging.py` (~40 lines) — only `tests/test_imports.py`

**Verification** (run before deleting):
```bash
for mod in access_control crypto/password security_hardening metrics log_utils/logging; do
  echo "=== $mod ==="
  grep -rln "from aitbc.$mod\|from aitbc import $mod\|aitbc\.$mod" --include="*.py" . | grep -v "aitbc/$mod" | grep -v "test_" | grep -v "docs/"
done
# Expected: no output for any module (all are dead or test-only)
```

**Fix**:
1. Delete all 5 files.
2. Delete orphan tests: `tests/test_access_control.py`, `tests/test_metrics.py`, and update `tests/test_imports.py` if it imports `log_utils/logging`.
3. **IMPORTANT**: AGENTS.md documents `aitbc/log_utils/logging.py` as an intentional re-export shim. Confirm with the user before deleting this one specifically.

#### A4: Delete dead classes in live files

**Files and classes** (all verified unused via vulture and grep):

1. `apps/coordinator-api/src/app/contexts/agent_coordination/services/task_decomposition.py` — `TaskDecompositionEngine` (446 lines)
2. `apps/coordinator-api/src/app/settlement/bridges/base.py` — `EthereumBridge` (131 lines)
3. `apps/coordinator-api/src/app/contexts/security/services/key_management.py` — `MockHSMStorage` (68 lines), `HSMProviderInterface` (39 lines)
4. `apps/coordinator-api/src/app/contexts/analytics/services/performance_monitoring.py` — `AutoOptimizer` (74 lines)
5. `apps/coordinator-api/src/app/contexts/multimodal/services/modality_optimization.py` — `ModalityOptimizationManager` (66 lines)
6. `apps/agent-coordinator/src/app/protocols/communication.py` — `RedisMessageBroker` (32 lines), `WebSocketHandler` (36 lines)
7. `apps/coordinator-api/src/app/contexts/security/services/quota_enforcement.py` — `QuotaMiddleware` (33 lines)

**Verification** (run before deleting):
```bash
for class in TaskDecompositionEngine EthereumBridge MockHSMStorage HSMProviderInterface AutoOptimizer ModalityOptimizationManager RedisMessageBroker WebSocketHandler QuotaMiddleware; do
  echo "=== $class ==="
  grep -rln "$class" --include="*.py" apps coordinator-api | grep -v "class $class" | head
done
# Expected: no output (or only the class definition itself)
```

**Fix**: Delete each class definition from its file. Keep the file itself if it contains other live code (e.g., `task_decomposition.py` has live dataclasses).

**Note**: `models/multitenant.py` has ~190 lines of unreferenced SQLModel table models (`TenantUser`, `Invoice`, `TenantApiKey`, `TenantAuditLog`, `TenantMetric`). Do NOT delete these — they are database models, and deleting them changes `create_all` schema. Treat as "multitenancy feature never wired up" and leave for a future feature decision.

#### A5: Delete orphan tests for dead modules

**Files**:
- `tests/test_access_control.py` (if `aitbc/access_control.py` is deleted)
- `tests/test_metrics.py` (if `aitbc/metrics.py` is deleted)
- Update `tests/test_imports.py` if it imports `log_utils/logging`
- Any other tests that import the deleted modules

**Verification**:
```bash
# Run tests after deletion to ensure no broken imports
./venv/bin/python -m pytest tests/unit -q -o addopts=""
```

**Fix**: Delete orphan test files or update imports.

---

## Agent B — Duplicate Consolidation (GLM 5.2)

**Scope**: Duplicate consolidation — agent-management collapse, shared blockchain RPC client, CLI error handling merge, DB init consolidation, config class adoption, security utils consolidation, small copy-paste elimination, Decimal gap fix. Complex tasks requiring understanding of API compatibility, service architecture, and business logic.

**Working directory**: `/opt/aitbc/`

**Verification command**:
```bash
cd /opt/aitbc && ./venv/bin/python -m mypy --show-error-codes aitbc/ && ./venv/bin/python -m pytest tests/unit -q -o addopts=""
cd /opt/aitbc/apps/coordinator-api && PYTHONPATH=src ../../venv/bin/python -m pytest tests -q -o addopts=""
```

### Tasks

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| B1 | Collapse agent-management services onto coordinator-api agent_coordination context (~4,800 lines) | 🟡 P2 | agent-management/services vs coordinator-api/…/agent_coordination/services | ⬜ |
| B2 | Create shared blockchain RPC client (~100 lines) | 🟡 P2 | trading/clients/blockchain.py, governance/clients/blockchain.py → aitbc/blockchain/rpc_client.py | ⬜ |
| B3 | Merge CLI error handling (~150 lines) | 🟡 P2 | cli/utils/error_handling.py → re-export from cli/aitbc_cli/utils/error_handling.py | ⬜ |
| B4 | Consolidate DB init modules (~200 lines) | 🟡 P2 | agent-management/database.py, pool-hub/database.py → shared-core/database.py | ⬜ |
| B5 | Adopt ServiceSettings across 5 services (~150 lines) | 🟡 P2 | trading, governance, marketplace, gpu, blockchain-event-bridge config.py → subclass ServiceSettings | ⬜ |
| B6 | Consolidate security utils (~200 lines) | 🟡 P2 | coordinator-api/utils/security.py, cli/utils/security.py, wallet/security.py → aitbc/security/ | ⬜ |
| B7 | Eliminate small copy-pastes (~100 lines) | 🟡 P2 | health endpoints, CORS setup, _to_decimal, retry helpers, GlobalMarketplaceOffer Decimal fix | ⬜ |
| B8 | Fix GlobalMarketplaceOffer Decimal inconsistency (~30 lines) | 🟡 P2 | marketplace service (Decimal) vs coordinator-api (float) → standardize on Decimal | ⬜ |

### Agent B — Detailed Instructions

#### B1: Collapse agent-management services onto coordinator-api agent_coordination context

**Files** (near-identical copies verified by diff):

| agent-management/services | coordinator-api/…/agent_coordination/services | diff lines |
|---|---|---|
| `agent_service_marketplace.py` (722) | `agent_marketplace.py` (722) | **10** |
| `agent_communication.py` (779) | `communication.py` (781) | **20** |
| `agent_orchestrator.py` (527) | `orchestrator.py` (525) | **29** |
| `agent_performance_service.py` (764) | `performance.py` (765) | 75 |
| `agent_portfolio_manager.py` (414) | `portfolio.py` (413) | 80 (both dead) |
| `agent_security.py` (683) | `security.py` (706) | 102 |
| `agent_integration.py` (885) | `integration.py` (879) | diverged |

Also duplicate routers (`submit_service_job` = identical 70-line function) and `adapters/agent_core_adapters.py`.

**Problem**: agent-management duplicates coordinator-api's agent_coordination context almost entirely. agent-management has no systemd unit deployed (only a wrapper script), while coordinator-api is deployed.

**Fix** (requires decision from user):
1. **Option A (deprecate agent-management)**: Delete agent-management services, update any external references to use coordinator-api's agent_coordination context. Delete the agent-management app entirely.
2. **Option B (thin wrapper)**: Keep agent-management as a thin re-export wrapper around coordinator-api's agent_coordination context. Delete the duplicate implementations, replace with imports from coordinator-api.
3. **Option C (keep both)**: If agent-management has a distinct purpose not captured by coordinator-api, document the divergence and keep both.

**Recommendation**: Option A (deprecate agent-management) — the service is not deployed and appears to be legacy. Confirm with user before proceeding.

#### B2: Create shared blockchain RPC client

**Files**:
- `apps/trading/src/trading_service/clients/blockchain.py` (91 lines)
- `apps/governance/src/governance_service/clients/blockchain.py` (183 lines)

**Similarity**: Both implement `__init__(rpc_url, timeout)` with httpx.AsyncClient, `get_block_height(chain_id)`, `get_balance/get_account_balance(address, chain_id)`. Governance version adds transaction signing (`submit_governance_tx`).

**Fix**:
1. Create `aitbc/blockchain/rpc_client.py` with base `BlockchainClient` class.
2. Implement common methods: `__init__`, `get_block_height`, `get_balance`, `get_account_balance`.
3. Governance client extends base with signing methods.
4. Trading client uses base class only.
5. Both services import from shared module.
6. Update imports in trading and governance services.

**Verification**:
```bash
# Verify both services still work after migration
cd apps/trading && ../../venv/bin/python -m pytest tests -q -o addopts=""
cd apps/governance && ../../venv/bin/python -m pytest tests -q -o addopts=""
```

#### B3: Merge CLI error handling

**Files**:
- `cli/utils/error_handling.py` (194 lines)
- `cli/aitbc_cli/utils/error_handling.py` (305 lines)

**Similarity**: Both define `CLIError`, `NetworkError`, `ConfigurationError`, `ValidationError`, `APIError`, `handle_cli_error`, `handle_async_cli_error` decorators, `safe_execute`, `validate_required_fields`, `validate_address`. The `aitbc_cli` version is enhanced with `abort()` function, Click integration, JSON/YAML output support.

**Fix**:
1. Deprecate `cli/utils/error_handling.py` as a re-export shim to `cli/aitbc_cli/utils/error_handling.py`.
2. Ensure all CLI imports use the `aitbc_cli` version.
3. Update any imports from `cli.utils.error_handling` to `cli.aitbc_cli.utils.error_handling`.

**Verification**:
```bash
# Verify all CLI commands still work
./venv/bin/python -m pytest tests/cli -q -o addopts=""
```

#### B4: Consolidate DB init modules

**Files**:
- `apps/agent-management/src/app/core/database.py` (44 lines)
- `apps/shared-core/src/app/core/database.py` (70 lines)
- `apps/pool-hub/src/poolhub/database.py` (53 lines)

**Similarity**: agent-management and shared-core are near-identical (both implement `get_engine`, `get_sessionmaker`, `get_db`). pool-hub is an async-only variant.

**Fix**:
1. Verify shared-core's `database.py` exports cover agent-management's needs.
2. Replace agent-management's `database.py` with a re-export from shared-core, or delete it and update imports.
3. For pool-hub, verify shared-core's async support covers its needs, or keep pool-hub's async variant if it has specific requirements.
4. Update all `from app.core.database import ...` in agent-management to use shared-core.

**Verification**:
```bash
# Verify agent-management and pool-hub still work
cd apps/agent-management && ../../venv/bin/python -m pytest tests -q -o addopts=""
cd apps/pool-hub && ../../venv/bin/python -m pytest tests -q -o addopts=""
```

#### B5: Adopt ServiceSettings across 5 services

**Files** (5 services define their own `Settings(BaseSettings)` with similar fields):
- `apps/trading/src/trading_service/config.py` (80 lines)
- `apps/governance/src/governance_service/config.py` (64 lines)
- `apps/marketplace/src/marketplace_service/config.py` (42 lines)
- `apps/gpu/src/gpu_service/config.py` (16 lines)
- `apps/blockchain-event-bridge/src/blockchain_event_bridge/config.py` (10 lines)

**Problem**: Services re-implement config fields (bind_host, bind_port, blockchain_rpc_url) instead of subclassing `ServiceSettings` from `aitbc_shared/core/config.py` (violates AGENTS.md convention).

**Fix**:
1. Read `packages/aitbc-shared/aitbc_shared/core/config.py` to understand `ServiceSettings` and `DatabaseConfig`.
2. For each service, change `class Settings(BaseSettings)` to `class Settings(ServiceSettings)`.
3. Remove redundant fields if they're already in `ServiceSettings`.
4. Add service-specific fields as needed.
5. Update imports to use `from aitbc_shared.core.config import ServiceSettings`.

**Verification**:
```bash
# Verify all services still start with new config
for service in trading governance marketplace gpu blockchain-event-bridge; do
  cd apps/$service && ../../venv/bin/python -m pytest tests -q -o addopts="" || echo "Failed: $service"
done
```

**Note**: Also resolve `aitbc/config.py` vs `aitbc/config/hierarchical_config.py` — two competing implementations. Choose one approach and deprecate the other.

#### B6: Consolidate security utils

**Files**:
- `apps/coordinator-api/src/app/utils/security.py` (144 lines) — InputValidator, RequestSigner, APIKeyRotator
- `cli/utils/security.py` (259 lines) — encryption, password validation, multisig
- `apps/wallet/src/app/security.py` (23 lines) — validate_password_rules, wipe_buffer

**Similarity**: Overlapping password validation but different implementations. CLI version has comprehensive encryption (PBKDF2+Fernet). Coordinator-api version has input validation (SQL injection, XSS). Wallet version has minimal password rules.

**Fix**:
1. Move coordinator-api's InputValidator to `aitbc/security/validators.py`.
2. Move CLI's encryption to `aitbc/security/encryption.py`.
3. Consolidate password validation to single implementation in `aitbc/security/`.
4. Deprecate app-specific security modules (re-export from `aitbc/security/`).
5. Update all imports.

**Verification**:
```bash
# Verify security utils still work
./venv/bin/python -m pytest tests/unit -q -o addopts=""
cd apps/coordinator-api && PYTHONPATH=src ../../venv/bin/python -m pytest tests -q -o addopts=""
```

#### B7: Eliminate small copy-pastes

**Patterns**:
1. **Health endpoints** — `HealthResponse` + `/health` handler copy-pasted in 6 services
2. **CORS setup** — CORSMiddleware setup block in 27 files
3. **Decimal helpers** — `_to_decimal` duplicated in exchange handlers
4. **Retry helpers** — retry helper in `cli/utils/__init__.py` vs `aitbc/decorators/`
5. **GlobalMarketplaceOffer** — diverged copies in marketplace service (Decimal) vs coordinator-api (float)

**Fix**:
1. **Health endpoints**: Add `create_health_endpoint(service_name)` decorator to `aitbc/health_checks.py`. Services use decorator instead of redefining.
2. **CORS setup**: Create `aitbc/middleware/cors.py` with `setup_cors()` function. Services call `setup_cors(app, settings.allow_origins)`.
3. **Decimal helpers**: Add `to_decimal()` to `aitbc/utils/decimal.py`. Deprecate local implementations.
4. **Retry helpers**: Add `retry_with_backoff` function to `aitbc/decorators/decorators.py`. Deprecate CLI version.
5. **GlobalMarketplaceOffer**: Handle in B8 (Decimal gap fix).

**Verification**:
```bash
# Verify services still work
./venv/bin/python -m pytest tests/unit -q -o addopts=""
```

#### B8: Fix GlobalMarketplaceOffer Decimal inconsistency

**Files**:
- `apps/marketplace/src/marketplace_service/domain/global_marketplace.py` (uses `Decimal` for base_price)
- `apps/coordinator-api/src/app/contexts/marketplace/domain/global_marketplace.py` (uses `float` for base_price)
- `packages/aitbc-shared/aitbc_shared/models/marketplace.py` (has MarketplaceOffer, not GlobalMarketplaceOffer)

**Problem**: Diverged copies of GlobalMarketplaceOffer with inconsistent types (Decimal vs float). This is a Decimal migration gap that v0.10.6 should have addressed.

**Fix**:
1. Add GlobalMarketplaceOffer to `packages/aitbc-shared/aitbc_shared/models/marketplace.py` with Decimal for money fields.
2. Deprecate both app-specific versions (re-export shims).
3. Update imports in marketplace service and coordinator-api to use aitbc-shared version.
4. Fix type inconsistency (standardize on Decimal for money).

**Verification**:
```bash
# Verify Decimal migration doesn't break tests
cd apps/marketplace && ../../venv/bin/python -m pytest tests -q -o addopts=""
cd apps/coordinator-api && PYTHONPATH=src ../../venv/bin/python -m pytest tests -q -o addopts=""
```

---

## Coordination Notes

### No coordination required

Agent A and Agent B tasks are independent:
- Agent A deletes dead code (no business logic impact)
- Agent B consolidates duplicates (requires business logic understanding but doesn't touch files Agent A deletes)

### Shared files to watch

None — Agent A only deletes files, Agent B only consolidates live files. No overlap.

---

## Verification Checklist

After completing all tasks:

- [ ] All dead modules deleted
- [ ] All dead classes deleted
- [ ] All orphan tests deleted
- [ ] agent-management services collapsed or deprecated
- [ ] Shared blockchain RPC client created and adopted
- [ ] CLI error handling merged
- [ ] DB init modules consolidated
- [ ] ServiceSettings adopted across 5 services
- [ ] Security utils consolidated
- [ ] Small copy-pastes eliminated
- [ ] GlobalMarketplaceOffer Decimal inconsistency fixed
- [ ] All tests pass (`./venv/bin/python -m pytest tests/unit -q -o addopts=""`)
- [ ] Coordinator-api tests pass (`cd apps/coordinator-api && PYTHONPATH=src ../../venv/bin/python -m pytest tests -q -o addopts=""`)
- [ ] Type check passes (`./venv/bin/python -m mypy --show-error-codes aitbc/`)
- [ ] Lint passes (`./venv/bin/python -m ruff check .`)
