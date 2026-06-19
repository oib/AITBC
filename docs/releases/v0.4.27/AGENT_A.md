# Agent A Tasks - v0.4.27

## Overview

Agent A is responsible for **Security, Data & API Integrity** tasks in v0.4.27. This is a patch release focused on quick wins — no architecture changes, just completion of pending work.

**Total estimated effort**: ~3.5 hours

---

## Task 1: Fix Production Startup Bug 🚨

**Priority**: P0 (Critical)
**Estimated effort**: 30 minutes
**Risk**: High (blocks production deployment)

### Problem

`apps/coordinator-api/src/app/main.py:131` calls `settings.validate_secrets()`, but the imported `BaseAITBCConfig` (aliased to `ValidatedAITBCConfig` in `aitbc/config/__init__.py:16`) has no `validate_secrets` method. This raises `AttributeError` once production env validation passes.

### Files Involved

- `apps/coordinator-api/src/app/main.py:131` — calls `settings.validate_secrets()`
- `apps/coordinator-api/src/app/config.py:13` — imports `BaseAITBCConfig` from `aitbc.config`
- `aitbc/config/__init__.py:16` — aliases `BaseAITBCConfig` to `ValidatedAITBCConfig`
- `aitbc/config/hierarchical_config.py` — likely contains `ValidatedAITBCConfig` class

### Investigation Steps

1. Read `aitbc/config/__init__.py` to understand the alias
2. Read `aitbc/config/hierarchical_config.py` to find `ValidatedAITBCConfig` class
3. Check if `BaseAITBCConfig` (the original class) has `validate_secrets` method
4. Determine which class should have the method

### Fix Options

**Option A**: Add `validate_secrets` method to `ValidatedAITBCConfig`
- Check if `BaseAITBCConfig` has the method, copy it over
- Ensure it works with the validation logic

**Option B**: Remove the call from `main.py`
- If the method is not needed, remove line 131
- Verify production validation still works without it

**Option C**: Use the original `BaseAITBCConfig` instead of the alias
- Change import in `config.py` to use the original class
- Verify no other code depends on the alias

### Acceptance Criteria

- [ ] Production startup completes without `AttributeError`
- [ ] Environment validation still works correctly
- [ ] Tests pass: `pytest tests/coordinator-api/ -x -q`

### Verification

```bash
# Test production startup
cd apps/coordinator-api
python -c "from app.config import settings; settings.validate_secrets()"

# Run coordinator tests
pytest tests/coordinator-api/ -x -q
```

---

## Task 2: JWT Auth Migration — Remaining High-Risk Routers

**Priority**: P1
**Estimated effort**: 3 hours
**Risk**: Medium (established pattern, 6 routers to migrate)

### Problem

Six routers still use the deprecated `require_admin_key()` function instead of the new `AdminDep` dependency. This was deferred from v0.4.26 to avoid scope creep.

### Routers to Migrate

| Router | File | Action | Effort |
|--------|------|--------|--------|
| Admin router | `routers/admin.py` | Replace `require_admin_key()` with `AdminDep` | ~30 min |
| Cache management | `routers/cache_management.py` | Replace `require_admin_key()` with `AdminDep` | ~20 min |
| Marketplace enhanced | `routers/marketplace_enhanced.py` | Replace `require_admin_key()` with `AdminDep` | ~30 min |
| Marketplace enhanced simple | `routers/marketplace_enhanced_simple.py` | Replace `require_admin_key()` with `AdminDep` | ~20 min |
| Payments | `contexts/payments/routers/payments.py` | Replace `require_admin_key()` with `AdminDep` | ~30 min |
| Security router | `contexts/security/routers/security_router.py` | Replace `require_admin_key()` with `AdminDep` | ~30 min |

### Migration Pattern

**Before**:
```python
from aitbc.deps import require_admin_key

@router.get("/admin-endpoint")
@require_admin_key
async def admin_endpoint():
    ...
```

**After**:
```python
from aitbc.deps import AdminDep

@router.get("/admin-endpoint")
async def admin_endpoint(admin: AdminDep):
    ...
```

### Steps for Each Router

1. Read the router file
2. Find all `@require_admin_key` decorator usages
3. Replace with `AdminDep` dependency injection
4. Remove import of `require_admin_key`
5. Add import of `AdminDep` if not present
6. Test the router endpoints

### Common Changes

1. **Remove import**:
   ```python
   # DELETE
   from aitbc.deps import require_admin_key
   ```

2. **Add import** (if not present):
   ```python
   # ADD
   from aitbc.deps import AdminDep
   ```

3. **Replace decorator**:
   ```python
   # BEFORE
   @router.get("/endpoint")
   @require_admin_key
   async def endpoint():
       ...

   # AFTER
   @router.get("/endpoint")
   async def endpoint(admin: AdminDep):
       ...
   ```

### Acceptance Criteria

- [ ] Zero `require_admin_key` references in all 6 routers
- [ ] All routers still protect admin endpoints
- [ ] Tests pass for each router
- [ ] No breaking changes to API contracts

### Verification

```bash
# Search for remaining require_admin_key usages
grep -r "require_admin_key" apps/coordinator-api/

# Run coordinator tests
pytest tests/coordinator-api/ -x -q

# Test each router manually if needed
curl -X GET http://localhost:8000/admin-endpoint  # Should fail without auth
```

---

## Task 3: Delete deps.py

**Priority**: P2
**Estimated effort**: 5 minutes
**Risk**: Low (blocked on Task 2)
**Dependency**: Must complete Task 2 first

### Problem

After all routers are migrated to `AdminDep`, `deps.py` has zero callers. It should be deleted to clean up deprecated code.

### File Location

`apps/coordinator-api/src/app/deps.py`

### Steps

1. Verify `deps.py` has no callers:
   ```bash
   grep -r "from app.deps import" apps/coordinator-api/
   grep -r "from .deps import" apps/coordinator-api/
   ```

2. If no callers found, delete the file:
   ```bash
   rm apps/coordinator-api/src/app/deps.py
   ```

3. Run tests to ensure nothing breaks:
   ```bash
   pytest tests/coordinator-api/ -x -q
   ```

### Acceptance Criteria

- [ ] `deps.py` deleted
- [ ] Zero import errors in codebase
- [ ] All tests pass

---

## Execution Order

1. **Task 1** (Production startup bug) — Do this first, it's critical
2. **Task 2** (JWT migration) — Main work, 6 routers
3. **Task 3** (Delete deps.py) — Quick cleanup after Task 2

---

## Common Requirements

### Testing

After each task, run:
```bash
# Coordinator API tests
pytest tests/coordinator-api/ -x -q

# Full test suite (if time permits)
pytest tests/ -x -q
```

### Git Workflow

After each task:
```bash
git add -A
git commit -m "fix: [task description]"
```

### Documentation

Update `docs/releases/v0.4.27/change.log` as tasks are completed:
- Mark tasks as ✅ done
- Add notes about any issues encountered
- Update acceptance criteria checkboxes

---

## Total Time Estimate

| Task | Effort |
|------|--------|
| Task 1: Production startup bug | 30 min |
| Task 2: JWT migration (6 routers) | 3 hours |
| Task 3: Delete deps.py | 5 min |
| **Total** | **~3.5 hours** |

---

## Notes

- All tasks are in `apps/coordinator-api/` directory
- No architecture changes required
- Established patterns from v0.4.26 JWT migration apply
- If blockers encountered, document in change.log and move to next task
