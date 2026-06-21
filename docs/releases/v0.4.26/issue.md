# AITBC v0.4.26 - Remaining Issues & Bug Fixes

> **Context**: Documenting all known remaining issues after v0.4.25 completion. These are structural/pre-existing issues that require planned effort beyond quick fixes.

---

## 📋 Issue Categories

### 1. SQLAlchemy Table Definition Conflicts (High Impact)
**Affected**: 4 coordinator API test files fail collection
- `tests/test_coordinator_api.py`
- `tests/test_coordinator_api_extended.py`
- `tests/test_coordinator_api_utils.py`
- `tests/test_coordinator_api_v1.py`

**Root Cause**: Multiple apps define identical ORM models with different `declarative_base()`:
- `MarketplaceBid` - defined in `apps/marketplace` and `apps/coordinator-api`
- `JobPayment` - defined in `apps/payments` and `apps/coordinator-api`
- `PaymentEscrow` - defined in `apps/payments` and `apps/coordinator-api`

**Error**: `sqlalchemy.exc.InvalidRequestError: Table 'marketplace_bid' is already defined for this MetaData instance`

**Suggested Fix**:
1. **Create shared models package** (`packages/aitbc-shared-models/`) with common ORM definitions
2. **Refactor all apps** to import from shared package instead of local definitions
3. **Use single `declarative_base()`** per service, shared via dependency injection
4. **Alternative**: Run each app's tests in isolated pytest sessions (`--forked` or separate CI jobs)

**Effort**: 1-2 weeks (medium)

---

### 2. Overall Test Coverage Below 50% Target (Medium Impact)
**Current**: ~47% (with caching tests), ~35% (without caching)
**Target**: ≥50%

**Untested Areas**:
| Area | Modules | Approx Lines | Effort |
|------|---------|--------------|--------|
| 42 apps in `apps/` | ~42 apps | ~50,000+ | Months |
| `aitbc/async_helpers/` | 2 modules | 80 | 1 week |
| `aitbc/access_control.py` | 1 | 120 | 3 days |
| `aitbc/api_utils.py` | 1 | 130 | 3 days |
| `aitbc/data_layer/` | 3 | ~300 | 1 week |
| `aitbc/blockchain/` | 4 | ~400 | 1 week |
| `aitbc/oracles/` | 2 | ~120 | 3 days |
| `aitbc/testing/` | 2 | ~230 | 1 week |

**Suggested Fix**:
1. **Prioritize by impact**: Core infrastructure (`access_control`, `async_helpers`) first
2. **Incremental**: Add tests module-by-module per sprint
3. **Exclude legacy apps**: Mark inactive apps with `# pragma: no cover`

**Effort**: Ongoing (2-3 months for meaningful improvement)

---

### 3. External Dependency Deprecation Warnings (Low Impact)
**Cannot fix in our code - require upstream updates**:

| Warning | Source | Fix |
|---------|--------|-----|
| `websockets.legacy` deprecated | `websockets` library v15+ internal | Upgrade to use `websockets.server.ServerProtocol` (done in our code) |
| `starlette.testclient` + `httpx` | `tests/cli/test_cli_integration.py:15` | Migrate to `httpx2` test client |

**Action**:
- `websockets.legacy`: Already mitigated in our code (using `ServerProtocol`)
- `httpx2` migration: Requires test client rewrite (~1 week)

---

### 4. SQLAlchemy SAWarnings: Duplicate Model Definitions (Low Impact)
**Cause**: Same model class defined in multiple apps with different bases:
```
SAWarning: This declarative base already contains a class with the same class name...
  app.contexts.marketplace.domain.marketplace.MarketplaceBid
  app.contexts.payments.domain.payment.JobPayment
  app.contexts.payments.domain.payment.PaymentEscrow
```

**Fix**: Same as Issue #1 - shared models package.

---

### 5. Apps Directory Audit Needed (Low Impact)
**Problem**: 42 apps in `apps/` directory - many likely inactive/legacy.

**Known Active Apps** (from service logs and test references):
- `agent-coordinator` ✅
- `coordinator-api` ✅
- `blockchain-node` ✅
- `hermes` ✅
- `marketplace` ✅
- `gpu` ✅
- `pool-hub` ✅
- `exchange` ✅
- `governance` ✅

**Suggested Fix**:
1. **Audit script** to check git activity, CI references, service logs
2. **Archive inactive apps** to `apps/archive/`
3. **Document active apps** in `docs/architecture/active_apps.md`

**Effort**: 2-3 days

---

### 6. Monolithic Files Needing Refactoring (Technical Debt)
| File | Lines | Suggestion |
|------|-------|------------|
| `aitbc/caching.py` | 926 | Split: `cache_backends.py`, `cache_strategies.py`, `cache_invalidation.py` |
| `aitbc/network/http_client.py` | 654 | Split: `client.py`, `retry_policy.py`, `circuit_breaker.py` |
| `aitbc/queues/queue_manager.py` | 398 | Split: `task_queue.py`, `job_scheduler.py`, `worker_pool.py` |

**Effort**: 1-2 weeks per file (incremental)

---

## 🎯 v0.4.26 Sprint Priorities

### Sprint 1 (Week 1-2): High Impact Fixes
- [ ] **Fix SQLAlchemy table conflicts** - Create shared models package
- [ ] **Migrate `httpx` → `httpx2`** in CLI integration tests
- [ ] **Run full test suite** without collection errors

### Sprint 2 (Week 3-4): Coverage & Debt
- [ ] **Add tests for `access_control.py`** (security critical)
- [ ] **Add tests for `async_helpers/`** (core infrastructure)
- [ ] **Refactor `caching.py`** into smaller modules
- [ ] **Audit `apps/` directory** - archive inactive apps

### Sprint 3 (Week 5-6): Infrastructure
- [ ] **Create shared ORM models package** (`packages/aitbc-shared/`)
- [ ] **Refactor `caching.py`** into smaller modules
- [ ] **Add CI job isolation** for per-app test runs

### Sprint 4 (Week 7-8): Polish
- [ ] **Document active apps**
- [ ] **Archive inactive apps** to `apps/archive/`
- [ ] **Update coverage targets** based on reality

---

## 📊 Tracking

| Issue | GitHub Issue | Owner | Status | Target |
|-------|--------------|-------|--------|--------|
| SQLAlchemy conflicts | #TBD | - | Planned | Sprint 1 |
| httpx2 migration | #TBD | - | Planned | Sprint 1 |
| Shared models package | #TBD | - | Planned | Sprint 3 |
| Coverage improvement | #TBD | - | Ongoing | Sprint 2+ |
| Apps audit | #TBD | - | Planned | Sprint 2 |

---

## 📝 Notes for Next Release

1. **Release criteria for v0.4.26**:
   - ✅ 0 collection errors
   - ✅ All deprecation warnings fixed
   - 🎯 ≥40% overall coverage (realistic)
   - 🎯 0 SQLAlchemy warnings
   - ✅ All P0 bugs fixed

2. **Realistic coverage target**: 40-45% (given 42 untested apps). 50% requires major app test effort.

3. **Consider splitting release**: Core library v0.4.26 + Apps suite separate versioning.

---

*Last updated: v0.4.25 completion*
*Next review: Sprint planning v0.4.26*
