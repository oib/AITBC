# AITBC v0.4.22 Release Plan

**Date**: Planning Phase  
**Status**: 📋 **PLANNING**  
**Scope**: Blockchain-node MyPy Type Safety Completion & Quality Improvements

## 🎯 Overview

AITBC v0.4.22 will focus on completing the MyPy type safety work for the blockchain-node application and implementing quality improvements across the codebase. Building on the success of v0.4.21 which achieved 100% MyPy compliance for 7 primary applications, v0.4.22 will:

1. **Complete blockchain-node MyPy fixes** (201 errors → 0 errors) ✅ **REQUIRED**
2. **Implement verification and quality assurance**
3. **Enable stricter MyPy options** ✅ **HIGH PRIORITY**
4. **Improve test coverage** to 30%+ ✅ **TARGET**
5. **Address linting and formatting issues**

## 📋 Decisions Made

- ✅ **Blockchain-node**: Required - complete all 201 errors to 0
- ✅ **Strict MyPy**: High priority - enable immediately after blockchain-node
- ✅ **Test coverage**: Target 30% (up from 22.96%)

## 📊 Current State

### MyPy Status
- ✅ **7 primary applications**: 0 errors (100% complete)
- ⚠️ **blockchain-node**: 201 errors remaining (down from 212)
- **Total errors**: 201 (down from 2,861 originally)

### Test Coverage
- **Current**: 22.96%
- **Gate**: 20%
- **Status**: Passing but room for improvement

## 🎯 Release Goals

### Primary Goals
1. **Complete blockchain-node MyPy compliance** - Reduce 201 errors to 0
2. **Verification & QA** - Ensure no regressions from v0.4.21 fixes
3. **Quality improvements** - Linting, formatting, test coverage

### Secondary Goals
1. **Enable stricter MyPy options** - Additional type safety checks
2. **Improve documentation** - Update AGENTS.md with v0.4.22 changes
3. **Performance optimization** - If time permits

## 📋 Detailed Task Breakdown

### Phase 1: Blockchain-node MyPy Fixes (Priority 1)

#### Error Categories to Address
1. **External library stubs** (5 errors)
   - opentelemetry imports (4 errors)
   - broadcaster import (1 error)
   - Action: Add type: ignore[import-not-found] or install stubs

2. **Type annotations** (10+ errors)
   - Missing variable type annotations
   - Missing function parameter annotations
   - Action: Add proper type annotations

3. **SQLAlchemy issues** (10+ errors)
   - TextClause usage patterns
   - Session.exec overload issues
   - Action: Add type: ignore comments or refactor

4. **Attribute errors** (20+ errors)
   - Missing attributes on classes
   - Incorrect attribute access
   - Action: Fix attribute definitions or add type: ignore

5. **Operator errors** (5+ errors)
   - Decimal/float type mismatches
   - Action: Add type conversions or type: ignore

6. **Unused type: ignore** (10+ errors)
   - Remove unnecessary type: ignore comments
   - Action: Clean up

#### Estimated Effort
- **Time**: 4-6 hours
- **Complexity**: Medium-High (architectural issues)

### Phase 2: Verification & Quality Assurance (Priority 2)

#### Verification Tasks
1. **Run full test suite**
   ```bash
   ./venv/bin/python -m pytest
   ```

2. **Check all applications still pass MyPy**
   ```bash
   for app in wallet agent-management edge hermes pool-hub agent-coordinator coordinator-api; do
     find apps/$app/src -name "*.py" -path "*/src/*" | xargs ./venv/bin/python -m mypy --show-error-codes
   done
   ```

3. **Run linting checks**
   ```bash
   ./venv/bin/python -m ruff check .
   ```

4. **Run formatting checks**
   ```bash
   ./venv/bin/python -m ruff format --check .
   ```

#### Estimated Effort
- **Time**: 1-2 hours
- **Complexity**: Low

### Phase 3: Enable Stricter MyPy Options (Priority 3)

#### Additional Strict Options to Consider
1. `--disallow-any-generics` - Disallow generic types without type parameters
2. `--disallow-untyped-calls` - Disallow calling functions without type hints
3. `--disallow-untyped-defs` - Disallow function definitions without type hints
4. `--warn-redundant-casts` - Warn about unnecessary type casts
5. `--warn-unused-ignores` - Warn about unused type: ignore comments

#### Approach
- Enable one option at a time
- Fix resulting errors
- Verify no regressions
- Proceed to next option

#### Estimated Effort
- **Time**: 2-4 hours
- **Complexity**: Medium

### Phase 4: Improve Test Coverage (Priority 4)

#### Coverage Targets
- **Current**: 22.96%
- **Target**: 30%+
- **Focus areas**: Recently fixed MyPy errors

#### Approach
- Identify low-coverage modules
- Add tests for critical paths
- Focus on recently refactored code

#### Estimated Effort
- **Time**: 3-5 hours
- **Complexity**: Medium

### Phase 5: Documentation Updates (Priority 5)

#### Documentation Tasks
1. Update AGENTS.md with v0.4.22 achievements
2. Update this release notes file with actual results
3. Update CHANGELOG if it exists
4. Update any relevant README files

#### Estimated Effort
- **Time**: 30 minutes
- **Complexity**: Low

## 🎯 Success Criteria

### Minimum Viable v0.4.22
- [x] blockchain-node MyPy errors reduced from 201 to 0 ✅ **REQUIRED**
- [ ] All 7 primary applications still pass MyPy (0 errors)
- [ ] No regressions in test suite
- [ ] Documentation updated

### Stretch Goals
- [x] Test coverage improved to 30%+ ✅ **TARGET**
- [x] Additional strict MyPy options enabled ✅ **HIGH PRIORITY**
- [ ] All linting issues resolved

## 📅 Timeline Estimate

| Phase | Estimated Time | Priority | Status |
|-------|---------------|----------|--------|
| Phase 1: Blockchain-node fixes | 4-6 hours | High | Pending |
| Phase 2: Verification & QA | 1-2 hours | High | Pending |
| Phase 3: Stricter MyPy options | 2-4 hours | High | Pending |
| Phase 4: Test coverage (30% target) | 3-5 hours | Medium | Pending |
| Phase 5: Documentation | 30 minutes | Low | Pending |
| **Total** | **10.5-17.5 hours** | - | - |

### Execution Order
1. **Phase 1**: Complete blockchain-node MyPy fixes (required)
2. **Phase 2**: Verification & QA (ensure no regressions)
3. **Phase 3**: Enable stricter MyPy options (high priority)
4. **Phase 4**: Improve test coverage to 30% (target)
5. **Phase 5**: Update documentation

## 🔧 Technical Considerations

### Blockchain-node Challenges
- External library dependencies (opentelemetry, broadcaster)
- Complex architectural patterns
- SQLAlchemy usage patterns
- May require justified per-file ignores for external library limitations

### Risk Mitigation
- If blockchain-node proves too complex, focus on primary applications
- Consider making blockchain-node optional in v0.4.22
- Document any remaining issues for future releases

## 📝 Decisions Made

### ✅ Resolved Questions

1. **Should blockchain-node be required for v0.4.22?**
   - ✅ **DECIDED**: Required - complete all 201 errors to 0
   - Rationale: Achieve 100% MyPy compliance across all 8 applications

2. **What is the priority for stricter MyPy options?**
   - ✅ **DECIDED**: High priority - enable immediately after blockchain-node
   - Rationale: Maximize type safety while momentum is high

3. **Test coverage target?**
   - ✅ **DECIDED**: Target 30% (up from 22.96%)
   - Rationale: Meaningful improvement without excessive time investment

## 🚀 Execution Plan

### Immediate Next Steps
1. ✅ **Planning complete** - All decisions made
2. **Begin Phase 1**: Start blockchain-node MyPy fixes
3. **Follow execution order**: Phases 1-5 in sequence
4. **Track progress**: Update this document as phases complete

### Phase 1 Execution Strategy
- Focus on error categories from easiest to hardest
- Start with external library stubs (type: ignore comments)
- Move to type annotations
- Address SQLAlchemy and attribute errors last
- Use subagents for parallel processing where possible

---

**Release Manager**: TBD  
**Reviewers**: Development Team  
**Target Release Date**: TBD
