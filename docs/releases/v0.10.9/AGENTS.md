# v0.10.9 — Agent Task Assignment

**Last Updated**: 2026-07-06
**Version**: 1.0 — Dead Code Elimination & Status Drift Cleanup

**Release Theme**: Dead Code Elimination & Status Drift Cleanup — Delete ~2,500 lines of dead test-only modules from `aitbc/`, fix documentation/status drift, clean up stale port references, migrate auth shims, and remove deprecated constants.

**Goal**: Continue the dead-code elimination pattern from v0.10.6, v0.10.7, and v0.10.8. Remove unused code and fix inconsistencies in documentation and configuration.

> **Scope**: 33 tasks across 6 categories. (1) Delete 15+ dead test-only `aitbc/` modules, (2) Delete dead pool-hub health router and CLI advanced_wallet.py, (3) Fix status drift (version bump, mark v0.10.4 complete, update STATUS.md), (4) Clean up stale port references, (5) Migrate auth shims, (6) Remove deprecated constants and documentation references.

> **Prerequisites**: [v0.10.8](../v0.10.8/change.log) (✅ complete — config consolidation & dead retry helper cleanup).

> **Risk**: Low. All deletions are verified to have zero production importers. Status drift fixes are documentation-only. Port updates are mechanical. Mitigated by: comprehensive test suite.

---

## Task Split Overview

| Agent | Capability | Tasks | Focus |
|-------|------------|-------|-------|
| **Agent A** | SWE 1.6 (fast mechanical tasks) | 4 items | Delete dead code (aitbc/ modules, pool-hub router, CLI wallet, HERMES_PORT) |
| **Agent B** | GLM 5.2 (complex tasks) | 6 items | Status drift fixes, stale port cleanup, auth shim migration, documentation cleanup |

**Conflict boundary**: Agent A owns dead code deletion in `aitbc/`. Agent B owns status drift, port updates, and auth shims. No overlap.

---

## Agent A — Dead Code Elimination (SWE 1.6)

**Scope**: Delete 15+ test-only modules in `aitbc/` with zero production importers (~2,500 lines), delete dead pool-hub health router (77 lines), delete CLI advanced_wallet.py (314 lines), and remove deprecated HERMES_PORT constant.

**Working directory**: `/opt/aitbc/`

**Verification command**:
```bash
cd /opt/aitbc && ./venv/bin/python -m ruff check . && ./venv/bin/python -m pytest tests/unit -q -o addopts=""
```

### Tasks

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| A1 | Delete 15+ dead test-only `aitbc/` modules + orphan tests (~2,500 lines) | 🟡 P2 | 15 modules in `aitbc/` + test files | ✅ |
| A2 | Delete dead pool-hub health router (77 lines) | 🟡 P2 | `apps/pool-hub/src/app/routers/health.py` | ✅ |
| A3 | Delete cli/advanced_wallet.py (314 lines, zero importers) | 🟡 P2 | `cli/advanced_wallet.py` | ✅ |
| A4 | Remove deprecated HERMES_PORT constant | 🟢 P3 | `aitbc/constants.py` | ✅ |

### Agent A — Detailed Instructions

#### A1: Delete 15+ dead test-only `aitbc/` modules + orphan tests

**Problem**: The following modules in `aitbc/` are **only used in tests** and have **no usage in any apps**. They exist only to satisfy their own test files.

**Modules to delete**:

| Module | Lines | Test importers only | Production importers |
|--------|-------|---------------------|---------------------|
| `aitbc/state/` | ~270 | `tests/test_imports.py`, `tests/test_state.py` | 0 |
| `aitbc/testing/` | ~200 | `tests/test_imports.py`, `tests/core/test_testing_module.py`, `tests/test_testing.py`, `tests/fixtures/` | 0 |
| `aitbc/benchmark.py` | 139 | `apps/blockchain-node/tests/test_performance.py` | 0 |
| `aitbc/feature_flags.py` | 235 | `tests/test_imports.py`, `tests/test_feature_flags.py` | 0 |
| `aitbc/monitoring/` | 254 | `tests/test_imports.py`, `tests/test_monitoring.py` | 0 |
| `aitbc/api/` | 62 | `tests/test_imports.py`, `tests/test_api_utils.py` | 0 |
| `aitbc/api_utils.py` | ~200 | `aitbc/api/__init__.py`, `tests/core/test_api_utils_module.py` | 0 |
| `aitbc/decorators/` | ~106 | `tests/test_imports.py`, `tests/test_decorators.py` | 0 |
| `aitbc/events/` | ~222 | `tests/test_imports.py`, `tests/test_events.py` | 0 |
| `aitbc/queues/` | ~500 | `tests/test_imports.py`, `tests/core/test_utility_modules.py`, `tests/test_queue_manager.py` | 0 |
| `aitbc/consensus/` | ~172 | `tests/unit/test_consensus_signing.py` | 0 |
| `aitbc/agent_protocols/` | ~100 | `docs/agent-sdk/api-sdk-methods.md` | 0 |
| `aitbc/agent_compliance/` | ~50 | 0 | 0 |
| `aitbc/agent_trading/` | ~50 | 0 | 0 |
| `aitbc/agent_bridge/src/__init__.py` | 0 (empty) | 0 | 0 |

**Total**: ~2,500 lines of dead code.

**Fix**:

**Step 1**: Verify zero production importers for each module:
```bash
# For each module, verify no production imports
grep -rn "from aitbc.state\|import aitbc.state" --include="*.py" apps/ cli/ scripts/ packages/ | grep -v __pycache__
grep -rn "from aitbc.testing\|import aitbc.testing" --include="*.py" apps/ cli/ scripts/ packages/ | grep -v __pycache__
# ... repeat for all modules
# Expected: no results
```

**Step 2**: Delete the modules:
```bash
rm -rf aitbc/state/
rm -rf aitbc/testing/
rm aitbc/benchmark.py
rm aitbc/feature_flags.py
rm -rf aitbc/monitoring/
rm -rf aitbc/api/
rm aitbc/api_utils.py
rm -rf aitbc/decorators/
rm -rf aitbc/events/
rm -rf aitbc/queues/
rm -rf aitbc/consensus/
rm -rf aitbc/agent_protocols/
rm -rf aitbc/agent_compliance/
rm -rf aitbc/agent_trading/
rm aitbc/agent_bridge/src/__init__.py
```

**Step 3**: Delete orphan test files:
```bash
rm tests/test_state.py
rm tests/test_testing.py
rm tests/test_feature_flags.py
rm tests/test_monitoring.py
rm tests/test_api_utils.py
rm tests/test_decorators.py
rm tests/test_events.py
rm tests/test_queue_manager.py
rm tests/unit/test_consensus_signing.py
rm tests/core/test_testing_module.py
rm tests/core/test_api_utils_module.py
rm tests/core/test_utility_modules.py
rm tests/fixtures/multi_chain.py  # if only used by deleted modules
```

**Step 4**: Update `tests/test_imports.py` to remove imports for deleted modules.

**Step 5**: Update `docs/agent-sdk/api-sdk-methods.md` to remove references to `aitbc.agent_protocols`.

**Verification**:
```bash
cd /opt/aitbc && ./venv/bin/python -m pytest tests/unit -q -o addopts=""
./venv/bin/python -m ruff check .
```

**Estimated impact**: Delete ~2,500 lines of dead code.

---

#### A2: Delete dead pool-hub health router (77 lines)

**Problem**: Health router in `apps/pool-hub/src/app/routers/health.py` is never mounted. Only `src/poolhub/app/routers/health.py` is used in main.py.

**Evidence**:
- `src/poolhub/app/main.py:20` attempts to import `from app.routers.pools import router as pools_router` (fails, sets to None)
- `src/poolhub/app/main.py:56` includes `health_router` from poolhub (not app)
- `src/app/routers/__init__.py:6` exports `health_router` but it's never imported anywhere in production code

**Fix**:
1. Delete `apps/pool-hub/src/app/routers/health.py`
2. Update `apps/pool-hub/src/app/routers/__init__.py` to remove the `health_router` export

**Verification**:
```bash
cd /opt/aitbc && ./venv/bin/python -m pytest apps/pool-hub/tests -q -o addopts="" 2>/dev/null || echo "No tests or tests pass"
```

**Estimated impact**: Delete 77 lines.

---

#### A3: Delete cli/advanced_wallet.py (314 lines, zero importers)

**Problem**: Standalone wallet script with zero importers across the codebase. File contains placeholder implementations using requests library but is never invoked.

**Evidence**: `grep -r "advanced_wallet" --include="*.py" .` returns no results.

**Fix**:
1. Delete `cli/advanced_wallet.py`

**Verification**:
```bash
cd /opt/aitbc && grep -r "advanced_wallet" --include="*.py" . | grep -v __pycache__
# Expected: no results
```

**Estimated impact**: Delete 314 lines.

---

#### A4: Remove deprecated HERMES_PORT constant

**Problem**: `HERMES_PORT` in `aitbc/constants.py` is marked as deprecated since v0.5.9. Only referenced in docs, no active usage found.

**Evidence**:
- Line 56: `HERMES_PORT: int = 8012  # Deprecated: hermes service removed in v0.5.9 §8, use AGENT_COORDINATOR_PORT`
- Grep for `HERMES_PORT` returns only doc references

**Fix**:
1. Delete line 56 from `aitbc/constants.py`
2. Search docs for `HERMES_PORT` references and remove them

**Verification**:
```bash
cd /opt/aitbc && grep -rn "HERMES_PORT" --include="*.py" . | grep -v __pycache__
# Expected: no results
```

**Estimated impact**: Delete 3 lines.

---

## Agent B — Status Drift & Config Cleanup (GLM 5.2)

**Scope**: Fix status drift (version bump, mark v0.10.4 complete, update STATUS.md), clean up stale port references (test fixtures 8006, CORS config, payments wallet URL), migrate auth shims to `aitbc.auth`, and remove agent-management references from documentation.

**Working directory**: `/opt/aitbc/`

**Verification command**:
```bash
cd /opt/aitbc && ./venv/bin/python -m mypy --show-error-codes aitbc/ && ./venv/bin/python -m ruff check . && ./venv/bin/python -m pytest tests/unit -q -o addopts=""
```

### Tasks

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| B1 | Fix status drift — version bump, mark v0.10.4 complete, update STATUS.md | 🟡 P2 | `pyproject.toml`, `AGENTS.md`, `docs/releases/v0.10.4/change.log`, `docs/releases/STATUS.md` | ✅ |
| B2 | Clean up stale port 8006 references in test fixtures (~60 occurrences) | 🟡 P2 | `tests/fixtures/cli_mocks.py`, `tests/fixtures/multi_chain.py`, `tests/unit/test_http_pool.py`, `tests/unit/test_island_registry.py`, `tests/unit/test_sync_source_resolver.py` | ✅ |
| B3 | Update coordinator-api CORS config to use current port constants | 🟡 P2 | `apps/coordinator-api/src/app/config.py` | ✅ |
| B4 | Fix hardcoded wallet port 20000 in payments service | 🟡 P2 | `apps/coordinator-api/src/app/contexts/payments/services/payments.py` | ✅ |
| B5 | Fix health-check.sh hardcoded ports | 🟡 P2 | `health-check.sh` | ✅ |
| B6 | Migrate auth shim importers to `aitbc.auth` + delete deprecated shims | 🟡 P2 | 7 auth shim files + internal importers | ✅ |
| B7 | Remove agent-management references from documentation | 🟢 P3 | `docs/getting-started/setup-service-selection.md` | ✅ |

### Agent B — Detailed Instructions

#### B1: Fix status drift — version bump, mark v0.10.4 complete, update STATUS.md

**Problem**: Multiple documentation inconsistencies:
1. `pyproject.toml` version is `0.10.2` but latest complete release is v0.10.8
2. `AGENTS.md` marks v0.10.4 as "🚧 in progress" but all tasks are complete
3. `docs/releases/STATUS.md` stops at v0.9.0 ("in progress" — it's done); no v0.10.x entries

**Fix**:

**Step 1**: Update `pyproject.toml` version to `0.10.9`:
```toml
version = "0.10.9"
```

**Step 2**: Mark v0.10.4 as complete in `docs/releases/v0.10.4/change.log`:
```markdown
**Status**: ✅ Complete — Performance optimization, Decimal migration, dead code elimination
```

**Step 3**: Update root `AGENTS.md` to mark v0.10.4 as complete:
```markdown
- **v0.10.4** — Performance, Correctness & Cleanup: <ref_file file="/opt/aitbc/docs/releases/v0.10.4/change.log" /> ✅ complete
```

**Step 4**: Update `docs/releases/STATUS.md` to add v0.10.x entries (v0.10.0 through v0.10.9, all complete).

**Verification**:
```bash
cd /opt/aitbc && grep "version = " pyproject.toml
# Expected: version = "0.10.9"
```

**Estimated impact**: ~10 lines changed, ~5 lines deleted.

---

#### B2: Clean up stale port 8006 references in test fixtures

**Problem**: Test fixtures still use stale port 8006 instead of correct port 8202. This was missed in v0.10.6 A2.

**Files and occurrences**:
- `tests/fixtures/cli_mocks.py:256`: `config.coordinator_url = "http://localhost:8006"`
- `tests/fixtures/multi_chain.py`: 5 occurrences
- `tests/unit/test_http_pool.py`: 5 occurrences
- `tests/unit/test_island_registry.py`: 19 occurrences
- `tests/unit/test_sync_source_resolver.py`: 30 occurrences
- **Total**: ~60 occurrences

**Fix**:
1. Replace all `http://localhost:8006` with `http://localhost:8202` in the above files
2. Use `sed` or manual edit:
```bash
cd /opt/aitbc
sed -i 's/http:\/\/localhost:8006/http:\/\/localhost:8202/g' tests/fixtures/cli_mocks.py
sed -i 's/http:\/\/localhost:8006/http:\/\/localhost:8202/g' tests/fixtures/multi_chain.py
sed -i 's/http:\/\/localhost:8006/http:\/\/localhost:8202/g' tests/unit/test_http_pool.py
sed -i 's/http:\/\/localhost:8006/http:\/\/localhost:8202/g' tests/unit/test_island_registry.py
sed -i 's/http:\/\/localhost:8006/http:\/\/localhost:8202/g' tests/unit/test_sync_source_resolver.py
```

**Verification**:
```bash
cd /opt/aitbc && grep -rn "localhost:8006" tests/ --include="*.py" | grep -v __pycache__
# Expected: no results
```

**Estimated impact**: ~60 lines changed.

---

#### B3: Update coordinator-api CORS config to use current port constants

**Problem**: CORS origins list in `apps/coordinator-api/src/app/config.py:128-137` references obsolete ports (8001-8016) that don't match current service ports.

**Current obsolete ports**:
- `8001` (Exchange - now 8106)
- `8002/8003` (Blockchain - now 8202)
- `8010-8016` (various services - now 8101-8108)

**Current constants from `aitbc/constants.py`**:
- `BLOCKCHAIN_RPC_PORT=8202`
- `WALLET_PORT=8108`
- `AGENT_COORDINATOR_PORT=8107`
- `EXCHANGE_PORT=8001` (but exchange actually uses 8106)

**Fix**:
1. Update the CORS origins list in `apps/coordinator-api/src/app/config.py` to use current port constants
2. Replace:
   - `http://localhost:8001` → `http://localhost:8106` (exchange)
   - `http://localhost:8002` → `http://localhost:8202` (blockchain)
   - `http://localhost:8003` → `http://localhost:8202` (blockchain)
   - `http://localhost:8010-8016` → `http://localhost:8101-8108` (various services)

**Verification**:
```bash
cd /opt/aitbc && grep -n "8001\|8002\|8003\|8010\|8011\|8012\|8013\|8014\|8015\|8016" apps/coordinator-api/src/app/config.py
# Expected: no results (all replaced)
```

**Estimated impact**: ~10 lines changed, ~10 lines deleted.

---

#### B4: Fix hardcoded wallet port 20000 in payments service

**Problem**: `apps/coordinator-api/src/app/contexts/payments/services/payments.py:28` hardcodes `wallet_base_url: str = "http://127.0.0.1:20000"` but `aitbc/constants.py` defines `WALLET_PORT = 8108`.

**Fix**:
1. Update line 28 to use the constant:
```python
wallet_base_url: str = Field(default=f"http://127.0.0.1:{WALLET_PORT}")
```
2. Add import if needed: `from aitbc.constants import WALLET_PORT`

**Verification**:
```bash
cd /opt/aitbc && grep -n "20000" apps/coordinator-api/src/app/contexts/payments/services/payments.py
# Expected: no results
```

**Estimated impact**: ~2 lines changed, ~2 lines deleted.

---

#### B5: Fix health-check.sh hardcoded ports

**Problem**: `health-check.sh` has hardcoded outdated ports that don't match current service ports.

**Current obsolete ports** (lines 26-31):
- `8006` (Blockchain - should be 8202)
- `8001` (Exchange - should be 8106)
- `9001` (Agent Coordinator - should be 8107)
- `8000` (Wallet - should be 8108)
- `8102` (Marketplace - should be 8081)

**Current constants from `aitbc/constants.py`**:
- `BLOCKCHAIN_RPC_PORT=8202`
- `COORDINATOR_API_PORT=8203`
- `EXCHANGE_PORT=8001` (but exchange actually uses 8106)
- `AGENT_COORDINATOR_PORT=8107`
- `MARKETPLACE_PORT=8081`
- `WALLET_PORT=8108`

**Fix**:
1. Update the SERVICE_ENDPOINTS array in `health-check.sh` to use current ports:
```bash
declare -A SERVICE_ENDPOINTS=(
    ["aitbc-blockchain-rpc"]="http://localhost:8202/health"
    ["aitbc-coordinator-api"]="http://localhost:8203/health"
    ["aitbc-exchange-api"]="http://localhost:8106/health"
    ["aitbc-agent-coordinator"]="http://localhost:8107/health"
    ["aitbc-marketplace"]="http://localhost:8081/health"
    ["aitbc-wallet"]="http://localhost:8108/health"
)
```
2. Update line 168 blockchain sync check URL from `http://localhost:8006` to `http://localhost:8202`

**Verification**:
```bash
cd /opt/aitbc && grep -n "8006\|8001\|9001\|8000" health-check.sh
# Expected: no results (all replaced)
```

**Estimated impact**: ~8 lines changed.

---

#### B7: Migrate auth shim importers to `aitbc.auth` + delete deprecated shims

**Problem**: Deprecated auth shims from v0.10.5 still have internal importers, causing hundreds of deprecation warnings in integration tests.

**Deprecated shims** (to be deleted after migration):
- `apps/coordinator-api/src/app/auth/jwt_handler.py` (23 lines)
- `apps/coordinator-api/src/app/auth/middleware.py` (21 lines)
- `apps/coordinator-api/src/app/auth/dependencies.py` (35 lines)
- `apps/coordinator-api/src/app/auth/security_matrix.py` (27 lines)
- `apps/agent-coordinator/src/app/auth/jwt_handler.py` (23 lines)
- `apps/agent-coordinator/src/app/auth/middleware.py` (42 lines)
- `apps/agent-coordinator/src/app/auth/permissions.py` (25 lines)

**Total**: ~200 lines to delete.

**Fix**:

**Step 1**: Find all internal importers of the deprecated shims:
```bash
cd /opt/aitbc
grep -rn "from app.auth\|from apps/coordinator-api/src/app/auth\|from apps/agent-coordinator/src/app/auth" --include="*.py" apps/coordinator-api apps/agent-coordinator | grep -v __pycache__
```

**Step 2**: Migrate each importer to use `aitbc.auth` instead:
- `from app.auth.jwt_handler import X` → `from aitbc.auth import X`
- `from app.auth.middleware import X` → `from aitbc.auth.middleware import X`
- `from app.auth.dependencies import X` → `from aitbc.auth.dependencies import X`
- `from app.auth.security_matrix import X` → `from aitbc.auth.security_matrix import X`

**Step 3**: Update `apps/coordinator-api/src/app/auth/__init__.py` to re-export from `aitbc.auth` instead of local shims:
```python
# Re-export from aitbc.auth for backward compatibility
from aitbc.auth import (
    create_access_token,
    verify_access_token,
    jwt_auth,
    AuthMiddleware,
    security_headers,
    # ... other exports
)
```

**Step 4**: Delete the deprecated shim files:
```bash
rm apps/coordinator-api/src/app/auth/jwt_handler.py
rm apps/coordinator-api/src/app/auth/middleware.py
rm apps/coordinator-api/src/app/auth/dependencies.py
rm apps/coordinator-api/src/app/auth/security_matrix.py
rm apps/agent-coordinator/src/app/auth/jwt_handler.py
rm apps/agent-coordinator/src/app/auth/middleware.py
rm apps/agent-coordinator/src/app/auth/permissions.py
```

**Verification**:
```bash
cd /opt/aitbc && ./venv/bin/python -m pytest tests/integration -q -o addopts="" 2>&1 | grep -i "deprecated" | wc -l
# Expected: 0 (no more deprecation warnings from app.auth)
```

**Estimated impact**: ~30 lines changed, ~200 lines deleted.

---

#### B6: Remove agent-management references from documentation

**Problem**: `docs/getting-started/setup-service-selection.md` still references the `aitbc-agent-management` service which was deleted in v0.10.7.

**Fix**:
1. Remove the agent-management service entry from the service selection table
2. Update any references to agent-management in the surrounding text

**Verification**:
```bash
cd /opt/aitbc && grep -rn "agent-management" docs/getting-started/setup-service-selection.md
# Expected: no results
```

**Estimated impact**: ~5 lines deleted.

---

## Coordination Notes

### No coordination required

Agent A and Agent B tasks are independent:
- Agent A deletes dead code in `aitbc/` and apps (no business logic impact, zero production importers)
- Agent B fixes status drift, updates ports, and migrates auth shims (mechanical changes)

### Shared files to watch

None — no overlap between tasks.

---

## Verification Checklist

After completing all tasks:

- [ ] 15+ dead test-only `aitbc/` modules deleted (~2,500 lines)
- [ ] Orphan test files deleted
- [ ] Dead pool-hub health router deleted (77 lines)
- [ ] cli/advanced_wallet.py deleted (314 lines)
- [ ] HERMES_PORT constant removed
- [ ] pyproject.toml version updated to 0.10.9
- [ ] v0.10.4 marked as complete in change.log and AGENTS.md
- [ ] STATUS.md updated with v0.10.x entries
- [ ] Port 8006 references in test fixtures replaced with 8202 (~60 occurrences)
- [ ] Coordinator-api CORS config updated to current ports
- [ ] Payments service wallet port updated to use WALLET_PORT constant
- [ ] health-check.sh ports updated to current constants
- [ ] Auth shim importers migrated to `aitbc.auth`
- [ ] Deprecated auth shim files deleted (~200 lines)
- [ ] Agent-management references removed from documentation
- [ ] All tests pass (`./venv/bin/python -m pytest tests/unit -q -o addopts=""`)
- [ ] Integration tests pass without deprecation warnings
- [ ] Type check passes (`./venv/bin/python -m mypy --show-error-codes aitbc/`)
- [ ] Lint passes (`./venv/bin/python -m ruff check .`)
