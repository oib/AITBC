# Agent B Tasks - v0.4.26

## Lower-Risk / Structural Refactoring Tasks

### P1: `aitbc/security_hardening.py` (475 lines) ✅ COMPLETED

**Current state**: Security headers, CSP, HSTS, XSS protection, content sniffing, frame options, all in one module.

**Actual architecture implemented**:
```
aitbc/security/
  __init__.py           # Re-exports for backward compatibility
  validators.py         # SecurityValidator
  audit.py            # SecurityAuditLog, SecurityAuditor
  rate_limiter.py     # RateLimiter
```

**Note**: The actual file content was security validation, audit logging, and rate limiting rather than middleware headers/CSP/HSTS. The `SecurityHeadersMiddleware` already lives in `aitbc/middleware.py`.

**Migration steps completed**:
1. Created `aitbc/security/` subpackage
2. Moved `SecurityValidator` to `validators.py`
3. Moved `SecurityAuditLog` and `SecurityAuditor` to `audit.py`
4. Created `RateLimiter` in `rate_limiter.py`
5. Updated `__init__.py` exports
6. Converted `security_hardening.py` to deprecation shim:
   ```python
   # DEPRECATED: Use aitbc.security
   from aitbc.security import SecurityValidator, SecurityAuditLog, SecurityAuditor, RateLimiter
   import warnings
   warnings.warn("aitbc.security_hardening is deprecated, use aitbc.security", DeprecationWarning, stacklevel=2)
   ```

**Classes/Functions Migrated** (from `aitbc/security_hardening.py`):
- `SecurityValidator` class → `validators.py`
- `SecurityAuditLog` class + `SecurityAuditor` class → `audit.py`
- `RateLimiter` class → `rate_limiter.py` (new addition)

**Risk**: Low — mostly used internally by middleware.

**Estimated effort**: 1 day
**Actual effort**: Completed

---

### P1: `aitbc/agent_registry/src/registration.py` (454 lines)

**Current state**: Agent registration, discovery, health tracking, and metadata management all in one file.

**Target architecture**:
```
aitbc/agent_registry/src/
  registration.py       # Core registration API (shrunk)
  discovery.py          # Agent discovery logic
  health.py             # Health tracking
  metadata.py           # Metadata validation/storage
```

**Migration steps**:
1. Extract discovery, health, and metadata into separate modules:
   - Agent discovery logic → `discovery.py`
   - Health tracking → `health.py`
   - Metadata validation/storage → `metadata.py`
2. Keep `registration.py` focused on registration API
3. Update `aitbc/agent_registry/src/__init__.py` exports

**Classes/Functions to Migrate** (from `aitbc/agent_registry/src/registration.py`):
- `AgentRegistry` class with registration methods (lines ~30-200)
- Discovery logic: `discover_agents()`, `find_agent()`, `list_agents()` (lines ~202-300)
- Health tracking: `AgentHealth`, `check_health()`, `heartbeat()` (lines ~302-380)
- Metadata: `AgentMetadata`, `validate_metadata()`, `store_metadata()` (lines ~382-454)

**Risk**: Low — internal to agent_registry package.

**Estimated effort**: 1 day

---

### P2: `aitbc/training_setup/environment.py` (414 lines) ✅ COMPLETED

**Current state**: Training environment configuration, validation, hardware detection, dependency checking, and dataset management.

**Actual architecture implemented**:
```
aitbc/training_setup/
  __init__.py           # Re-exports for backward compatibility
  environment.py        # Shrunk to core env config and prerequisites
  blockchain.py         # Genesis allocation, faucet setup
  messaging.py          # Messaging authentication setup
  services.py           # Faucet service deployment
```

**Note**: The actual file content was blockchain/wallet setup (genesis allocation, faucet setup, messaging auth) rather than ML training hardware/dataset management. The module name is historical.

**Migration steps completed**:
1. Split into focused modules:
   - Core environment config and prerequisites → `environment.py` (shrunk)
   - Genesis allocation and faucet setup → `blockchain.py`
   - Messaging authentication setup → `messaging.py`
   - Faucet service deployment → `services.py`
2. Updated `aitbc/training_setup/__init__.py` exports

**Classes/Functions Migrated** (from `aitbc/training_setup/environment.py`):
- `TrainingEnvironment` class → `environment.py` (shrunk)
- Genesis allocation, faucet setup → `blockchain.py`
- Messaging authentication → `messaging.py`
- Faucet service deployment → `services.py`

**Risk**: Low — internal to training_setup package.

**Estimated effort**: 0.5-1 day
**Actual effort**: Completed

---

### P2: `aitbc/testing/testing.py` (406 lines) ✅ COMPLETED

**Current state**: Test fixtures, mock generators, assertion helpers, and test utilities all in one file.

**Actual architecture implemented**:
```
aitbc/testing/
  __init__.py           # Re-exports for backward compatibility
  factories.py          # MockFactory, TestDataGenerator
  mocks.py              # MockResponse, MockDatabase, MockCache
  assertions.py         # TestHelpers
  decorators.py           # mock_async_call, create_mock_config, create_test_scenario
```

**Note**: The actual file content had factory classes, mock classes, assertion helpers, and test decorators rather than pytest fixtures. `decorators.py` was created instead of `fixtures.py`.

**Migration steps completed**:
1. Split into utilities package:
   - MockFactory, TestDataGenerator → `factories.py`
   - MockResponse, MockDatabase, MockCache → `mocks.py`
   - TestHelpers → `assertions.py`
   - mock_async_call, create_mock_config, create_test_scenario → `decorators.py`
2. Updated `aitbc/testing/__init__.py` exports

**Classes/Functions Migrated** (from `aitbc/testing/testing.py`):
- `MockFactory` class + `TestDataGenerator` class → `factories.py`
- `MockResponse` class + `MockDatabase` class + `MockCache` class → `mocks.py`
- `TestHelpers` class → `assertions.py`
- `mock_async_call()`, `create_mock_config()`, `create_test_scenario()` → `decorators.py`

**Risk**: Low — internal to testing package.

**Estimated effort**: 0.5-1 day
**Actual effort**: Completed

---

### P2: `aitbc/queues/queue_manager.py` (398 lines) ✅ COMPLETED

**Current state**: Task queue, job scheduler, worker pool, priority queue, debounce/throttle decorators all in one file.

**Actual architecture implemented**:
```
aitbc/queues/
  __init__.py           # Re-exports for backward compatibility
  task.py              # Job, JobStatus, JobPriority, TaskQueue
  scheduler.py          # JobScheduler
  worker.py            # BackgroundTaskManager, WorkerPool
  decorators.py         # debounce, throttle
```

**Note**: Minor naming differences from initial plan (`task.py` instead of `queue.py`, `worker.py` singular instead of `workers.py`).

**Migration steps completed**:
1. Split into components:
   - `Job` + `JobStatus` + `JobPriority` + `TaskQueue` → `task.py`
   - `JobScheduler` → `scheduler.py`
   - `BackgroundTaskManager` + `WorkerPool` → `worker.py`
   - `debounce` + `throttle` decorators → `decorators.py`
2. Updated `aitbc/queues/__init__.py` exports

**Classes/Functions Migrated** (from `aitbc/queues/queue_manager.py`):
- `Job` dataclass + `JobStatus` + `JobPriority` enums + `TaskQueue` class → `task.py`
- `JobScheduler` class → `scheduler.py`
- `BackgroundTaskManager` class + `WorkerPool` class → `worker.py`
- `debounce` decorator + `throttle` decorator → `decorators.py`

**Risk**: Low — internal to queues package.

**Estimated effort**: 0.5-1 day
**Actual effort**: Completed

---

## Critical Infrastructure Tasks

### SQLAlchemy Table Conflicts (High Priority — Sprint 1)

**Problem**: 4 coordinator API test files fail collection due to duplicate ORM model definitions:
- `MarketplaceBid` — defined in `apps/marketplace` and `apps/coordinator-api`
- `JobPayment` / `PaymentEscrow` — defined in `apps/payments` and `apps/coordinator-api`

**Error**: `sqlalchemy.exc.InvalidRequestError: Table 'marketplace_bid' is already defined for this MetaData instance`

**Solution**: Create shared models package
```
packages/aitbc-shared/
  models/
    __init__.py
    marketplace.py       # MarketplaceBid, MarketplaceOffer
    payments.py          # JobPayment, PaymentEscrow
  orm.py                 # Shared declarative_base + session handling
```

**Migration steps**:
1. Create `packages/aitbc-shared/` with shared ORM models:
   - `packages/aitbc-shared/models/marketplace.py` — `MarketplaceBid`, `MarketplaceOffer`
   - `packages/aitbc-shared/models/payments.py` — `JobPayment`, `PaymentEscrow`
   - `packages/aitbc-shared/orm.py` — shared `declarative_base()` + session handling
2. Refactor apps to import from shared package:
   - Update `apps/marketplace/...` imports
   - Update `apps/payments/...` imports
   - Update `apps/coordinator-api/...` imports
3. Remove duplicate definitions from individual apps
4. Update test fixtures (`tests/conftest.py` or similar) to use shared models
5. Add `packages/aitbc-shared/` to `pyproject.toml` dependencies

**Risk**: Medium — requires coordinated changes across apps

**Estimated effort**: 1-2 weeks

---

### httpx2 Migration for CLI Tests (Sprint 1)

**File**: `tests/cli/test_cli_integration.py:15`
**Problem**: `from starlette.testclient import TestClient as StarletteTestClient` triggers deprecation warning

**Fix**: Migrate to `httpx.AsyncClient` with ASGI transport
```python
# Old (lines 14-16)
from starlette.testclient import TestClient as StarletteTestClient

# New (httpx 0.28+)
from httpx import AsyncClient

# Usage in test fixtures:
async with AsyncClient(app=app, base_url="http://testserver") as client:
    response = await client.get("/health")
```

**Migration steps**:
1. Replace `StarletteTestClient` with `httpx.AsyncClient` in `tests/cli/test_cli_integration.py`
2. Update all test functions to use `await client.get()` / `client.post()` pattern
3. Update context manager usage from `with TestClient()` to `async with AsyncClient()`
4. Ensure all test methods are `async def`
5. Add `pytest-asyncio` marker if needed

**Files to update**:
- `tests/cli/test_cli_integration.py` (main file)
- Any other test files using `StarletteTestClient`

**Estimated effort**: 1 week

---

## Apps Directory Audit & Cleanup

### Inventory & Archive Inactive Apps

**Target**: `apps/` has 42 directories - many inactive/experimental

**Known Active Apps** (by service logs, CI, test references):
- `agent-coordinator` ✅
- `coordinator-api` ✅
- `blockchain-node` ✅
- `hermes` ✅
- `marketplace` ✅
- `gpu` ✅
- `pool-hub` ✅
- `exchange` ✅
- `governance` ✅

**Steps**:
1. Audit script: check git activity (last 6 months), CI workflow references, service logs
   ```bash
   # Check git activity
   for app in apps/*/; do
     echo "=== $app ==="
     git log --oneline -5 -- "$app" 2>/dev/null || echo "No git history"
   done
   ```
2. Move inactive apps to `apps/archive/`
   ```bash
   mkdir -p apps/archive
   mv apps/inactive-app apps/archive/
   ```
3. Document active apps in `docs/architecture/active_apps.md`:
   ```markdown
   # Active AITBC Applications
   
   ## Agent Coordinator
   Path: apps/agent-coordinator
   Purpose: Agent lifecycle management
   Maintainer: @team-ai
   
   ## Coordinator API
   Path: apps/coordinator-api
   Purpose: Main REST API
   ...
   ```

**Estimated effort**: 2-3 days

---

## Common Requirements for All Agent B Tasks:

1. **Tests first**: Add tests to new modules before removing old code
   - Target: 80%+ coverage on new modules
   - Use existing test patterns from `tests/`

2. **Backward compatibility**: Keep shims for 1 release cycle
   - Add `DeprecationWarning` with `stacklevel=2`
   - Document migration path in shim docstrings

3. **Run test suite** after changes:
   ```bash
   pytest tests/ --ignore=tests/test_coordinator_api*.py -x -q
   ```

4. **Document changes** in `docs/releases/v0.4.26/change.log`:
   - Add section for each refactored module
   - Note breaking changes and migration path

---

## Execution Order for Agent B:

All sprints have been completed successfully.

### Sprint 1 (Week 1-2): High Priority ✅ COMPLETED
1. **SQLAlchemy conflicts** — Create shared models package ✅
2. **httpx2 migration** — CLI test fix ✅

### Sprint 2 (Week 2-3): Refactoring ✅ COMPLETED
1. **security_hardening.py** — 1 day ✅
2. **agent_registry/src/registration.py** — 1 day ✅

### Sprint 3 (Week 3-4): More Refactoring ✅ COMPLETED
1. **training_setup/environment.py** — 0.5-1 day ✅
2. **testing/testing.py** — 0.5-1 day ✅
3. **queues/queue_manager.py** — 0.5-1 day ✅

### Sprint 4 (Week 4): Cleanup ✅ COMPLETED
1. **Apps audit & archive** — 2-3 days ✅
2. **Documentation update** — `docs/architecture/active_apps.md` ✅

---

*Source: `/opt/aitbc/docs/releases/v0.4.26/REFACTORING_PLANS.md` (full)*
*Reference: `/opt/aitbc/docs/releases/v0.4.26/issue.md` (issue tracking)*
*Reference: `/opt/aitbc/docs/releases/v0.4.26/change.log` (change tracking)*