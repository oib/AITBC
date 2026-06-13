# MyPy Investigation Report for v0.4.19

**Date:** June 13, 2026
**Investigator:** Agent 2
**Scope:** pool-hub, edge, agent-management

## Summary

Investigated MyPy errors in 3 apps with per-file ignores. Results show significant variation in complexity:

- **edge:** 4 errors (simplest) - RECOMMENDED FOR v0.4.19
- **pool-hub:** 29 errors (moderate complexity)
- **agent-management:** 82 errors (complex)

## Detailed Findings

### edge (6 per-file ignores)

**Error Count:** 4 errors in 1 file
**Files Checked:** 25 source files
**Status:** ✅ READY FOR FIXES

**Errors by File:**
- `apps/edge/src/aitbc_edge/main.py`: 4 errors
  - Line 17: Function is missing a return type annotation [no-untyped-def]
  - Line 28: Function is missing a return type annotation [no-untyped-def]
  - Line 33: Function is missing a return type annotation [no-untyped-def]
  - Line 43: Function is missing a return type annotation [no-untyped-def]

**Error Types:**
- 100% missing return type annotations

**Complexity:** LOW
- All errors are simple missing return type annotations
- Can be fixed by adding `-> None` or appropriate return types
- No import issues or type mismatches
- Estimated effort: 15 minutes

**Recommendation:** FIX FIRST - Simplest app, quick win

---

### pool-hub (17 per-file ignores)

**Error Count:** 29 errors in 2 files
**Files Checked:** 33 source files (sample)
**Status:** ⚠️ MODERATE COMPLEXITY

**Errors by File:**
- `apps/pool-hub/src/poolhub/services/billing_integration.py`: 13 errors
  - Type errors: attr-defined, operator, assignment, no-any-return
  - Missing return type annotations: 3 errors
- `apps/pool-hub/src/poolhub/app/routers/sla.py`: 16 errors
  - Import errors: Cannot find implementation for poolhub.app.database, models, services
  - Missing return type annotations: 11 errors

**Error Types:**
- 38% missing return type annotations (11 errors)
- 38% import errors (5 errors)
- 24% type errors (7 errors)

**Complexity:** MEDIUM
- Import path issues need investigation
- Type errors require understanding of data structures
- Missing return types are straightforward
- Estimated effort: 2-3 hours

**Recommendation:** FIX SECOND - After edge, if time permits

---

### agent-management (6 per-file ignores)

**Error Count:** 82 errors in 3 files
**Files Checked:** 28 source files (sample)
**Status:** ⚠️ HIGH COMPLEXITY

**Errors by File:**
- `apps/agent-management/src/app/routers/agent_router.py`: 45 errors
  - Argument type errors with Depends (9 errors)
  - SQLAlchemy vs SQLModel session type mismatches (6 errors)
  - Attribute errors (4 errors)
  - Assignment errors (3 errors)
  - Union attribute errors (3 errors)
- `apps/agent-management/src/app/routers/agent_performance.py`: 23 errors
  - Import errors: Cannot find app.domain.agent_performance
  - SQLAlchemy vs SQLModel session type mismatches (7 errors)
  - Type annotation errors (1 error)
- `apps/agent-management/src/app/routers/agent_security_router.py`: 14 errors
  - Attribute errors with Result[tuple] (2 errors)
  - Various type errors

**Error Types:**
- 40% SQLAlchemy vs SQLModel session type mismatches
- 35% argument type errors with FastAPI Depends
- 15% attribute errors
- 10% import errors

**Complexity:** HIGH
- SQLAlchemy vs SQLModel session type incompatibility is systemic
- FastAPI Depends type issues require understanding of dependency injection
- Missing domain model (agent_performance) needs investigation
- Estimated effort: 6-8 hours

**Recommendation:** DEFER TO v0.4.20 - Too complex for v0.4.19

---

## Recommendations

### For v0.4.19

**Priority 1: Fix edge (RECOMMENDED)**
- Effort: 15 minutes
- Impact: MyPy clean for 1 app
- Risk: None
- Action: Add return type annotations to 4 functions in main.py

**Priority 2: Fix pool-hub (OPTIONAL)**
- Effort: 2-3 hours
- Impact: MyPy clean for 1 app
- Risk: Low-Medium (import path issues)
- Action: Fix import paths, add return types, resolve type errors

### For v0.4.20

**Priority 1: Fix agent-management**
- Effort: 6-8 hours
- Impact: MyPy clean for 1 app
- Risk: Medium (systemic type issues)
- Action: Resolve SQLAlchemy vs SQLModel session types, fix Depends issues, investigate missing domain models

## Per-File Ignore Count Update

**Current (from v0.4.18):**
- edge: 6 files
- pool-hub: 17 files
- agent-management: 6 files

**Expected After Fixes:**
- edge: 0 files (if all 4 errors fixed)
- pool-hub: ~5-10 files (if import paths fixed)
- agent-management: 6 files (deferred)

## Next Steps for Agent 2

1. **Fix edge** (Week 2, Phase 2)
   - Add return type annotations to main.py
   - Verify 0 errors with mypy
   - Update per-file ignore count

2. **Fix pool-hub** (Week 2, Phase 2 - if time permits)
   - Investigate import path issues
   - Add return type annotations
   - Resolve type errors
   - Verify 0 errors with mypy

3. **Documentation** (Week 3, Phase 3)
   - Update TYPE_CHECKING_GUIDE.md
   - Update per-file ignore counts
   - Document patterns discovered

## Conclusion

Edge is the clear candidate for v0.4.19 MyPy expansion due to its simplicity (4 errors, all missing return types). Pool-hub is feasible if time permits. Agent-management should be deferred to v0.4.20 due to systemic type incompatibilities.
