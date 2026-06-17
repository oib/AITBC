# AITBC v0.4.24 Release Plan

**Date**: 2026-06-17
**Status**: 📋 Planning Phase
**Scope**: Architecture Refactoring, Test Coverage Improvement, and Type Safety Completion

## 🎯 Overview

AITBC v0.4.24 focuses on completing the architecture refactoring that was planned but not executed in v0.4.23, improving test coverage to meet the 50% target, and resolving remaining type safety issues. This release addresses the remaining technical debt identified in v0.4.22 and v0.4.23.

## 📊 Current State (Post v0.4.23)

### Achievements from v0.4.23
- ✅ **Architecture refactoring**: Split aitbc/__init__.py into aitbc.logging, aitbc.config submodules (partial - only logging/config)
- ✅ **Type ignore tracking**: 0 files with `# mypy: ignore-errors` (0 files, was 2)
- ✅ **Documentation validation**: Script created and added to pre-commit
- ✅ **API documentation**: OpenAPI specs generated for all 4 services
- ✅ **Correlation ID propagation**: Middleware and HTTP clients updated with X-Request-ID
- ✅ **Security hardening**: Hardcoded ports removed, configurable via env vars in 10 wrapper scripts
- ✅ **Wrapper script templating**: Template and generation script created, 10 wrappers generated
- ✅ **Logging standardization**: All 12+ active services use aitbc.aitbc_logging with INFO level
- ✅ **B008 lint refactor**: 1,105 violations fixed via LibCST transformer
- ✅ **CI/CD improvements**: Test matrix split, coverage gate at 50%
- ✅ **Integration test DB setup**: SQLite in-memory fixtures for database-backed tests
- ✅ **OpenTelemetry Collector**: Deployed with OTLP gRPC (4317), HTTP (4318), health (13133), Prometheus (8889)

### Remaining Technical Debt (from v0.4.23)
- ⚠️ **Test coverage**: 29% below target (goal: 50% → 70% → 85%)
- ⚠️ **MyPy errors**: 30 pre-existing errors in coordinator-api (7 files)
- ⚠️ **B008 type accuracy**: MyPy exposes 28 pre-existing type issues where services expect non-Optional types (types now correctly annotated as `int | None` instead of implicit non-optional)
- ⚠️ **Architecture refactoring**: Full aitbc/__init__.py split not completed (only logging/config submodules created, full 15-submodule plan not executed)

### REFACTORING_PLAN.md Status
- **Status**: 📋 Planning Phase - Not Started
- **Estimated Effort**: 8-12 hours
- **Risk Level**: Medium (requires careful import migration)
- **Scope**: Split monolithic `aitbc/__init__.py` (248 lines, 150+ lazy exports) into 15 logical submodules

## 🎯 Release Goals

### Primary Goals
1. **Complete architecture refactoring** - Execute full aitbc/__init__.py split into 15 submodules (from REFACTORING_PLAN.md)
2. **Improve test coverage** - From 29% to 50% (meet v0.4.23 target)
3. **Resolve MyPy errors** - Fix 30 pre-existing errors in coordinator-api
4. **Fix B008 type accuracy issues** - Resolve 28 type issues exposed by B008 refactor

### Secondary Goals
1. **Documentation updates** - Update all documentation to reflect new module structure
2. **Import migration** - Update 70+ files to use new submodule imports
3. **Lazy loading removal** - Remove __getattr__ mechanism after migration
4. **Verification** - Comprehensive testing of refactored structure

## 📋 Detailed Task Breakdown

### Phase 1: Complete Architecture Refactoring (Priority P0)

#### Current State
- **File**: `/opt/aitbc/aitbc/__init__.py` (248 lines)
- **Structure**: 37 direct imports + 150+ lazy exports via `__getattr__`
- **Problem**: Monolithic design causes import coupling, poor IDE support, difficult maintenance
- **Status**: Only partial completion in v0.4.23 (logging/config submodules only)

#### Full Submodule Structure (from REFACTORING_PLAN.md)
Create 15 submodules:
1. **aitbc.api** - API utilities (api_utils module) - 25 functions
2. **aitbc.async_helpers** - Async utilities (async_helpers module) - 8 functions
3. **aitbc.blockchain** - Blockchain services (blockchain_service) - 3 classes
4. **aitbc.crypto** - Cryptography utilities (crypto.crypto, crypto.security) - 18 functions
5. **aitbc.database** - Database utilities (database, database_service) - 8 classes/functions
6. **aitbc.decorators** - Decorators (decorators module) - 6 functions
7. **aitbc.events** - Event system (events module) - 11 classes/functions
8. **aitbc.monitoring** - Monitoring utilities (monitoring module) - 3 classes
9. **aitbc.network** - Network utilities (http_client) - 4 classes/functions
10. **aitbc.queue** - Queue management (queue_manager) - 9 classes/functions
11. **aitbc.state** - State management (state module) - 10 classes
12. **aitbc.testing** - Testing utilities (testing module) - 9 classes/functions
13. **aitbc.utils** - General utilities (json_utils, time_utils, validation, env, paths) - 42 functions
14. **aitbc.data_layer** - Data abstraction (data_layer) - 4 classes/functions
15. **aitbc.config** - Configuration (hierarchical_config) - 2 classes

#### Implementation Strategy
1. **Phase 1a**: Create 15 submodule __init__.py files with re-exports
2. **Phase 1b**: Update lazy export mappings in __init__.py to point to new submodules
3. **Phase 1c**: Update imports across 70+ files in codebase
4. **Phase 1d**: Remove lazy loading mechanism (_LAZY_EXPORTS, __getattr__)
5. **Phase 1e**: Clean up main __init__.py to <100 lines

#### Estimated Effort
- **Time**: 8-12 hours
- **Complexity**: High (affects entire codebase)
- **Risk**: Medium (backward compatibility maintained during transition)

### Phase 2: Improve Test Coverage to 50% (Priority P1)

#### Current State
- **Coverage**: 29% (below 50% target from v0.4.23)
- **Test categories**: Unit, integration, e2e, security separated
- **Coverage gate**: 50% (currently not met)

#### Target Areas for Coverage Improvement
1. **Low-coverage modules** (identified from coverage reports):
   - `aitbc/blockchain_service.py` - Core blockchain functionality
   - `aitbc/database.py` - Database utilities
   - `aitbc/crypto/` - Cryptography functions
   - `aitbc/events.py` - Event system
   - `aitbc/state.py` - State machine
   - `aitbc/queue_manager.py` - Queue management

2. **Application modules**:
   - `apps/coordinator-api/src/app/contexts/*` - Coordinator contexts
   - `apps/agent-coordinator/src/app/routers/*` - Agent coordinator routers
   - `apps/agent-management/src/app/routers/*` - Agent management routers
   - `apps/hermes/src/hermes_service/handlers/*` - Hermes handlers

3. **Critical paths**:
   - Blockchain RPC endpoints
   - Agent registration and discovery
   - Marketplace operations
   - Wallet transactions
   - Cross-service communication

#### Implementation Tasks
1. **Add unit tests for core utilities** (2-3 hours)
   - Test all crypto functions (sign, verify, hash, key derivation)
   - Test database connection and operations
   - Test event system (publish, subscribe, filters)
   - Test state machine transitions
   - Test queue operations (enqueue, dequeue, scheduling)

2. **Add integration tests for services** (3-4 hours)
   - Test coordinator API endpoints
   - Test agent coordinator workflows
   - Test agent management operations
   - Test hermes message handling
   - Test marketplace service operations

3. **Add e2e tests for workflows** (2-3 hours)
   - Test agent registration → coordinator → execution flow
   - Test wallet → marketplace → settlement flow
   - Test blockchain → hermes → agent communication

4. **Add security tests** (1-2 hours)
   - Test authentication and authorization
   - Test input validation
   - Test rate limiting
   - Test CORS configuration

#### Estimated Effort
- **Time**: 8-12 hours
- **Complexity**: Medium (requires test infrastructure)
- **Risk**: Low (additive changes)

### Phase 3: Resolve MyPy Errors in Coordinator-API (Priority P1)

#### Current State
- **Errors**: 30 pre-existing errors in coordinator-api (7 files)
- **Status**: Identified in v0.4.23 but not fixed
- **Impact**: Type safety not 100% complete

#### Error Categories
1. **Type annotation issues** (10-15 errors)
   - Missing type annotations on variables
   - Missing type annotations on function parameters
   - Incorrect type annotations

2. **Attribute errors** (5-10 errors)
   - Missing attributes on classes
   - Incorrect attribute access patterns

3. **SQLAlchemy issues** (5-10 errors)
   - Session.exec overload issues
   - Query result type issues
   - Column type mismatches

#### Implementation Tasks
1. **Analyze each error** (1 hour)
   - Document root cause for each error
   - Determine fix strategy (type annotation, refactoring, type: ignore)

2. **Fix type annotation issues** (2-3 hours)
   - Add missing type annotations
   - Correct incorrect type annotations
   - Use proper generic types (dict[str, Any], list[Any], etc.)

3. **Fix attribute errors** (1-2 hours)
   - Add missing attributes to classes
   - Fix attribute access patterns
   - Use proper type narrowing

4. **Fix SQLAlchemy issues** (1-2 hours)
   - Add type: ignore comments where appropriate
   - Refactor query patterns
   - Use proper column types

5. **Verification** (1 hour)
   - Run MyPy on coordinator-api
   - Verify 0 errors
   - Run tests to ensure no regressions

#### Estimated Effort
- **Time**: 6-9 hours
- **Complexity**: Medium (requires type system knowledge)
- **Risk**: Low (type fixes, no functional changes)

### Phase 4: Fix B008 Type Accuracy Issues (Priority P2)

#### Current State
- **Issues**: 28 pre-existing type issues exposed by B008 refactor
- **Root cause**: Services expect non-Optional types but types are now correctly annotated as `int | None`
- **Status**: Identified in v0.4.23 but not fixed

#### Problem Description
The B008 refactor in v0.4.23 changed:
```python
# Before
param: Type = Depends(...)

# After
param: Annotated[Type, Depends(...)]
```

This exposed 28 type issues where:
- Services expect `param` to always be non-Optional
- But the type is now correctly annotated as `Type | None`
- Services need to handle None cases or change type annotations

#### Implementation Tasks
1. **Identify all 28 type issues** (1 hour)
   - Search for services using parameters with `Annotated[Type, Depends(...)]`
   - Document which services expect non-Optional types
   - Categorize by severity (critical vs. non-critical)

2. **Fix critical issues** (2-3 hours)
   - Add None checks where appropriate
   - Change type annotations to non-Optional where justified
   - Add default values where appropriate

3. **Fix non-critical issues** (1-2 hours)
   - Add defensive programming (None checks)
   - Update error handling
   - Add validation

4. **Verification** (1 hour)
   - Run MyPy to verify fixes
   - Run tests to ensure no regressions
   - Check for new type issues

#### Estimated Effort
- **Time**: 5-7 hours
- **Complexity**: Medium (requires understanding of type system and service logic)
- **Risk**: Medium (may require logic changes)

### Phase 5: Documentation Updates (Priority P2)

#### Documentation Tasks
1. **Update REFACTORING_PLAN.md** (30 minutes)
   - Mark architecture refactoring as complete
   - Add completion date
   - Document any deviations from plan

2. **Update TYPE_CHECKING.md** (30 minutes)
   - Document MyPy error fixes
   - Update type checking status
   - Document remaining type debt (if any)

3. **Update API documentation** (1 hour)
   - Update import examples to use new submodule structure
   - Update OpenAPI specs if needed
   - Update code examples in docs/api/

4. **Update module documentation** (1 hour)
   - Create README.md for each new submodule
   - Document submodule exports
   - Add usage examples

5. **Update MASTER_INDEX.md** (30 minutes)
   - Add new module documentation links
   - Update import examples
   - Validate all links

#### Estimated Effort
- **Time**: 3-4 hours
- **Complexity**: Low
- **Risk**: Low

## 🎯 Success Criteria

### Minimum Viable v0.4.24
- [ ] aitbc/__init__.py split into 15 submodules (backward compatible)
- [ ] Test coverage improved from 29% to 50%
- [ ] 30 MyPy errors in coordinator-api resolved (0 errors)
- [ ] 28 B008 type accuracy issues fixed

### Stretch Goals
- [ ] Test coverage improved to 55%+
- [ ] All documentation updated and validated
- [ ] All import patterns migrated to new structure
- [ ] Lazy loading mechanism removed
- [ ] __init__.py reduced to <100 lines

## 📅 Timeline Estimate

| Phase | Estimated Time | Priority | Status |
|-------|---------------|----------|--------|
| Phase 1: Architecture refactoring | 8-12 hours | P0 | 📋 Not Started |
| Phase 2: Test coverage improvement | 8-12 hours | P1 | 📋 Not Started |
| Phase 3: MyPy error fixes | 6-9 hours | P1 | 📋 Not Started |
| Phase 4: B008 type accuracy fixes | 5-7 hours | P2 | 📋 Not Started |
| Phase 5: Documentation updates | 3-4 hours | P2 | 📋 Not Started |
| **Total** | **30-44 hours** | - | 📋 Not Started |

### Execution Order
1. **Phase 1**: Architecture refactoring (foundational, affects everything)
2. **Phase 3**: MyPy error fixes (type safety, high priority)
3. **Phase 4**: B008 type accuracy fixes (type safety, medium priority)
4. **Phase 2**: Test coverage improvement (quality, can be done in parallel)
5. **Phase 5**: Documentation updates (can be done throughout)

## 🔧 Technical Considerations

### Architecture Refactoring Risks
- **Breaking changes**: Maintain backward compatibility during transition
- **Import updates**: Use automated refactoring tools where possible
- **Testing**: Comprehensive testing after each migration step
- **Rollback plan**: Keep git branches for easy rollback

### Test Coverage Risks
- **Test quality**: Ensure tests are meaningful, not just for coverage
- **Test flakiness**: Avoid flaky integration tests
- **Performance**: Ensure test suite doesn't become too slow
- **Maintenance**: Keep tests maintainable

### Type Safety Risks
- **Type correctness**: Ensure type annotations are accurate
- **Runtime behavior**: Ensure type fixes don't change runtime behavior
- **MyPy strictness**: Balance strictness with practicality
- **External libraries**: May need type: ignore for external library limitations

## 📝 Decisions Made

### ✅ Resolved Questions

1. **Should architecture refactoring be completed in v0.4.24?**
   - ✅ **DECIDED**: Yes - Priority P0
   - Rationale: Planned in v0.4.23 but not completed, foundational improvement

2. **Should test coverage target be 50%?**
   - ✅ **DECIDED**: Yes - Priority P1
   - Rationale: Meet v0.4.23 target, improve code quality

3. **Should MyPy errors be fixed?**
   - ✅ **DECIDED**: Yes - Priority P1
   - Rationale: Complete type safety, resolve remaining debt

4. **Should B008 type issues be fixed?**
   - ✅ **DECIDED**: Yes - Priority P2
   - Rationale: Resolve issues exposed by v0.4.23 refactor

## 🚀 Execution Plan

### Phase 1 Execution Strategy
1. Create backup branch: `git checkout -b backup/v0.4.23`
2. Create feature branch: `git checkout -b feature/v0.4.24-architecture-refactor`
3. Execute Phase 1a: Create 15 submodule __init__.py files
4. Execute Phase 1b: Update lazy export mappings
5. Execute Phase 1c: Update imports across codebase (use automated tools)
6. Execute Phase 1d: Remove lazy loading mechanism
7. Execute Phase 1e: Clean up main __init__.py
8. Test thoroughly after each sub-phase
9. Commit and push after each successful sub-phase

### Phase 2 Execution Strategy
1. Run coverage report to identify low-coverage modules
2. Prioritize critical paths and core utilities
3. Add tests incrementally
4. Run coverage report after each batch
5. Aim for 50% coverage minimum

### Phase 3 Execution Strategy
1. Run MyPy on coordinator-api to get error list
2. Categorize errors by type
3. Fix errors in order of complexity
4. Verify after each fix
5. Run full test suite to ensure no regressions

### Phase 4 Execution Strategy
1. Identify all 28 type issues
2. Categorize by severity
3. Fix critical issues first
4. Add defensive programming for non-critical issues
5. Verify with MyPy and tests

## 📊 Expected Results

### Architecture
- ✅ **aitbc/__init__.py**: Reduced from 248 lines to <100 lines
- ✅ **Module structure**: 15 logical submodules with clear separation
- ✅ **IDE support**: Improved autocomplete and navigation
- ✅ **Import coupling**: Reduced dependencies between modules
- ✅ **Lazy loading**: Removed, direct imports only

### Quality
- ✅ **Test coverage**: Improved from 29% to 50%+
- ✅ **Type safety**: 0 MyPy errors across all applications
- ✅ **Type accuracy**: 28 B008 type issues resolved
- ✅ **Code quality**: Better maintainability and IDE support

### Documentation
- ✅ **Module docs**: README.md for each submodule
- ✅ **API docs**: Updated import examples
- ✅ **Release notes**: Comprehensive documentation of changes
- ✅ **Migration guide**: Guide for updating imports

### Summary
v0.4.24 will complete the architecture refactoring planned in v0.4.23, improve test coverage to meet the 50% target, and resolve remaining type safety issues. This release addresses all remaining technical debt from v0.4.22 and v0.4.23.

**Release Manager**: Development Team
**Reviewers**: Development Team
**Target Release Date**: TBD
