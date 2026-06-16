# AITBC v0.4.23 Release Plan

**Date**: 2026-06-15
**Status**: � **IN PROGRESS**
**Scope**: Architecture Refactoring, Logging Standardization, Observability Enhancement, and CI/CD Improvements

## 🎯 Overview

AITBC v0.4.23 focuses on architectural improvements, logging standardization across all services, enhanced observability with correlation ID propagation, and CI/CD enhancements. Building on the success of v0.4.22 which achieved 100% MyPy compliance and zero linting errors, v0.4.23 targets maintainability, observability, and operational excellence.

**Planning phase — execution pending approval.**

## 📊 Current State (Post v0.4.22)

### Achievements from v0.4.22
- ✅ **MyPy compliance**: 0 errors across all 12 applications (100% type safety)
- ✅ **Strict MyPy mode**: 12/12 strict options enabled
- ✅ **Ruff linting**: Zero errors (1,689 issues resolved)
- ✅ **Test coverage**: 29% (up from 22.96%)
- ✅ **sys.path hacks**: ~319 instances removed
- ✅ **E402 import order**: ~1,123 violations fixed
- ✅ **Pre-commit hooks**: Implemented and active
- ✅ **Service configuration**: Drift fixed across 9 services

### Remaining Technical Debt
- ⚠️ **Monolithic aitbc/__init__.py**: 254 lines, 150+ lazy exports
- ⚠️ **Logging inconsistency**: Only 6/24 services use aitbc_logging
- ⚠️ **Correlation ID propagation**: Missing across service boundaries
- ⚠️ **Wrapper scripts**: 24 manual scripts, no template-based generation
- ⚠️ **Test coverage**: 29% below target (goal: 50% → 70% → 85%)
- ⚠️ **Type ignore tracking**: 2 files still have `# mypy: ignore-errors` (down from 73)
- ⚠️ **API documentation**: OpenAPI specs not published
- ⚠️ **Documentation validation**: MASTER_INDEX.md may reference non-existent files

## 🎯 Release Goals

### Primary Goals
1. **Architecture refactoring** - Split monolithic aitbc/__init__.py into submodules
2. **Logging standardization** - Migrate all services to aitbc.aitbc_logging
3. **Observability enhancement** - Add X-Request-ID propagation middleware
4. **CI/CD improvements** - Add integration test matrix and coverage gates

### Secondary Goals
1. **Wrapper script templating** - Generate service wrappers from template
2. **Security hardening** - Remove hardcoded ports, configurable CORS
3. **Documentation validation** - Add MASTER_INDEX.md validation step
4. **API documentation** - Publish OpenAPI specs

## 📋 Detailed Task Breakdown

### Phase 1: Architecture Refactoring - Split aitbc/__init__.py (Priority P0)

#### Current State
- **File**: `/opt/aitbc/aitbc/__init__.py` (254 lines)
- **Structure**: 48 direct imports + 150+ lazy exports via `__getattr__`
- **Problem**: Monolithic design causes import coupling, poor IDE support, difficult maintenance

#### Proposed Structure
```
aitbc/
├── __init__.py (minimal: version, core exports only)
├── logging/ (aitbc_logging.py → logging/)
│   ├── __init__.py (configure_logging, get_logger, setup_logger)
│   ├── structured.py (structured logging utilities)
│   └── middleware.py (logging middleware)
├── crypto/ (crypto.py, security.py → crypto/)
│   ├── __init__.py
│   ├── crypto.py (signatures, hashing, key derivation)
│   └── security.py (tokens, API keys, session management)
├── database/ (database.py, database_service.py → database/)
│   ├── __init__.py
│   ├── connection.py (DatabaseConnection, get_database_connection)
│   └── service.py (DatabaseService, SQLiteDatabaseService)
├── network/ (http_client.py, web3_utils.py → network/)
│   ├── __init__.py
│   ├── http_client.py (AITBCHTTPClient, AsyncAITBCHTTPClient)
│   └── web3_utils.py (Web3Client, create_web3_client)
├── config/ (hierarchical_config.py → config/)
│   ├── __init__.py
│   └── hierarchical_config.py (BaseAITBCConfig, AITBCConfig)
└── utils/ (existing utils/ directory, reorganized)
```

#### Migration Strategy
1. **Phase 1a**: Create new submodule structure without breaking changes
   - Create submodules with `__init__.py` files
   - Copy existing code to new locations
   - Add re-exports in new `__init__.py` files
   - Keep old `__init__.py` with deprecation warnings

2. **Phase 1b**: Update imports across codebase
   - Search for `from aitbc import X` patterns
   - Update to `from aitbc.crypto import X` where appropriate
   - Keep backward-compatible imports in main `__init__.py`

3. **Phase 1c**: Remove lazy exports
   - Convert 150+ lazy exports to direct imports
   - Update `__all__` lists
   - Remove `__getattr__` implementation

4. **Phase 1d**: Clean up main __init__.py
   - Keep only core exports (version, constants, exceptions)
   - Remove deprecated imports after transition period
   - Final size target: <50 lines

#### Estimated Effort
- **Time**: 8-12 hours
- **Complexity**: High (affects entire codebase)
- **Risk**: Medium (backward compatibility maintained during transition)

### Phase 2: Logging Standardization (Priority P1)

#### Current State Analysis
**Services using aitbc_logging (6/24):**
- ✅ coordinator-api (src/app/main.py)
- ✅ gpu (src/gpu_service/main.py)
- ✅ governance (src/governance_service/main.py)
- ✅ trading (src/trading_service/main.py)
- ✅ marketplace (src/marketplace_service/main.py)
- ✅ api-gateway (src/api_gateway/main.py)

**Services NOT using aitbc_logging (18/24):**
- ❌ blockchain-node (uses custom logger in logger.py)
- ❌ hermes (uses custom logging)
- ❌ wallet (uses custom logging)
- ❌ edge (uses custom logging)
- ❌ agent-management (uses custom logging)
- ❌ agent-coordinator (uses custom logging)
- ❌ pool-hub (uses custom logging)
- ❌ blockchain-event-bridge (uses custom logging)
- ❌ ffpmeg-service (uses custom logging)
- ❌ whisper-service (uses custom logging)
- ❌ transcoder-service (uses custom logging)
- ❌ notification-service (uses custom logging)
- ❌ bounty-service (uses custom logging)
- ❌ staking-service (uses custom logging)
- ❌ certification-service (uses custom logging)
- ❌ analytics-service (uses custom logging)
- ❌ ai-analytics-service (uses custom logging)
- ❌ multimodal-service (uses custom logging)

#### Migration Tasks
1. **Audit current logging patterns**
   - Document each service's current logging setup
   - Identify custom logger implementations
   - Note any service-specific logging requirements

2. **Create migration guide**
   - Document aitbc_logging.py API
   - Provide migration examples
   - List breaking changes

3. **Migrate services in priority order**
   - **Priority 1**: blockchain-node, wallet, edge (core infrastructure)
   - **Priority 2**: agent-management, agent-coordinator, pool-hub (agent services)
   - **Priority 3**: Remaining services (supporting services)

4. **Update service main.py files**
   - Replace custom logger imports with `from aitbc import configure_logging, get_logger`
   - Call `configure_logging()` during startup
   - Replace logger initialization with `logger = get_logger(__name__)`

5. **Verify logging output**
   - Check structured JSON format
   - Verify log levels
   - Test log aggregation

#### Estimated Effort
- **Time**: 6-8 hours
- **Complexity**: Medium (18 services to migrate)
- **Risk**: Low (backward compatible, no breaking changes)

### Phase 3: Observability Enhancement - X-Request-ID Propagation (Priority P1)

#### Current State
- ❌ No correlation ID propagation across service boundaries
- ❌ Request tracing impossible across microservice calls
- ❌ Debugging distributed issues difficult

#### Implementation Plan

1. **Create correlation ID middleware**
   ```python
   # aitbc/middleware/correlation.py
   from fastapi import Request
   import uuid

   async def add_correlation_id(request: Request, call_next):
       correlation_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
       request.state.correlation_id = correlation_id
       response = await call_next(request)
       response.headers["X-Request-ID"] = correlation_id
       return response
   ```

2. **Add to aitbc_logging**
   - Include correlation_id in structured log output
   - Add correlation_id to all log records
   - Update log format to include correlation_id field

3. **Add HTTP client propagation**
   - Update AITBCHTTPClient to include X-Request-ID header
   - Update AsyncAITBCHTTPClient to include X-Request-ID header
   - Add correlation_id to outgoing requests

4. **Deploy to all services**
   - Add middleware to FastAPI apps
   - Update HTTP client usage
   - Test end-to-end propagation

#### Estimated Effort
- **Time**: 4-6 hours
- **Complexity**: Medium (affects all services)
- **Risk**: Low (non-breaking addition)

### Phase 4: CI/CD Improvements - Integration Test Matrix (Priority P2)

#### Current State
- **Test coverage**: 29% (below target)
- **Test paths**: Single testpath in pyproject.toml
- **Coverage gate**: 20% (minimum threshold)
- **Test categories**: Defined but not enforced

#### Proposed Improvements

1. **Split test matrix**
   ```toml
   [tool.pytest.ini_options]
   testpaths = [
       "tests/unit",           # Fast unit tests
       "tests/integration",    # Service integration tests
       "tests/e2e",            # End-to-end workflows
       "tests/security",       # Security tests
   ]
   markers = [
       "slow: marks tests as slow",
       "integration: marks tests as integration tests",
       "unit: marks tests as unit tests",
       "e2e: marks tests as end-to-end tests",
       "security: marks tests as security tests",
   ]
   ```

2. **Add coverage gates**
   ```toml
   # Stage 1: 50% coverage
   # Stage 2: 70% coverage
   # Stage 3: 85% coverage
   addopts = "--cov-fail-under=50"
   ```

3. **Add integration tests for cross-service flows**
   - coordinator → blockchain → hermes
   - wallet → marketplace → settlement
   - agent-management → agent-coordinator → execution

4. **Create CI pipeline stages**
   - Stage 1: Unit tests (fast, must pass)
   - Stage 2: Integration tests (slower, must pass)
   - Stage 3: E2E tests (slowest, can be optional for PRs)
   - Stage 4: Security tests (on merge to main)

#### Estimated Effort
- **Time**: 8-10 hours
- **Complexity**: Medium (requires test infrastructure)
- **Risk**: Low (additive changes)

### Phase 5: Wrapper Script Templating (Priority P2)

#### Current State
- **Wrapper scripts**: 24 manual scripts in scripts/
- **Problem**: Drift, inconsistency, manual maintenance
- **Examples**: aitbc-monitoring-wrapper.py, aitbc-plugin-wrapper.py

#### Proposed Solution

1. **Create Jinja2 template**
   ```jinja2
   #!/usr/bin/env python3
   """{{ service_name }} service wrapper"""
   import os
   import sys
   from pathlib import Path

   # Add AITBC to path
   sys.path.insert(0, "{{ repo_dir }}")
   sys.path.insert(0, "{{ service_dir }}")

   from aitbc import DATA_DIR, REPO_DIR, configure_logging, get_logger

   # Configure logging
   configure_logging(
       log_level="{{ log_level|default('INFO') }}",
       log_dir="{{ log_dir|default(DATA_DIR / 'logs') }}",
       service_name="{{ service_name }}",
   )

   logger = get_logger(__name__)
   logger.info("Starting {{ service_name }} service")

   # Execute service
   exec_cmd = [
       "{{ python_path|default(sys.executable) }}",
       "-m",
       "{{ module_name }}",
   ]

   os.execvp(exec_cmd[0], exec_cmd)
   ```

2. **Create generation script**
   ```python
   # scripts/generate_wrappers.py
   import jinja2
   from pathlib import Path

   SERVICES = [
       {"name": "coordinator-api", "module": "coordinator_api.main", "dir": "apps/coordinator-api"},
       {"name": "blockchain-node", "module": "aitbc_chain.main", "dir": "apps/blockchain-node"},
       # ... all 24 services
   ]

   def generate_wrapper(service_config):
       # Render template
       # Write to scripts/services/{service_name}-wrapper.py
       # Make executable
   ```

3. **Migrate existing wrappers**
   - Replace manual scripts with generated versions
   - Test each wrapper
   - Update systemd service files if needed

4. **Add to pre-commit**
   - Regenerate wrappers on service config changes
   - Validate wrapper syntax

#### Estimated Effort
- **Time**: 6-8 hours
- **Complexity**: Medium (template infrastructure)
- **Risk**: Low (backward compatible)

### Phase 6: Security Hardening (Priority P2)

#### Current Issues

1. **Hardcoded ports in wrapper scripts**
   - health-check.sh: hardcoded ports
   - Multiple wrapper scripts: hardcoded ports
   - **Solution**: Use aitbc.constants

2. **CORS origins in coordinator-api**
   - Current: localhost only
   - **Solution**: Make configurable per environment via AITBC_CORS_ORIGINS

3. **Rate limit configs as strings**
   - Current: String-based configuration
   - **Solution**: Use structured config with validation

#### Implementation Tasks

1. **Audit hardcoded values**
   - Search for port numbers in scripts/
   - Search for localhost references
   - Document all findings

2. **Create constants module**
   ```python
   # aitbc/constants.py (extend existing)
   DEFAULT_CORS_ORIGINS = ["http://localhost:3000", "http://localhost:8080"]
   PRODUCTION_CORS_ORIGINS = ["https://aitbc.io"]
   ```

3. **Update configuration**
   - Add CORS_ORIGINS to hierarchical config
   - Add environment variable support
   - Add validation

4. **Update scripts**
   - Replace hardcoded ports with constants
   - Replace localhost with configurable values
   - Test in different environments

#### Estimated Effort
- **Time**: 4-6 hours
- **Complexity**: Low (straightforward replacements)
- **Risk**: Low (configuration changes)

### Phase 7: Documentation Validation (Priority P3)

#### Current Issues
- MASTER_INDEX.md may reference non-existent files
- No automated validation of documentation links
- OpenAPI specs not published

#### Implementation Tasks

1. **Create documentation validation script**
   ```python
   # scripts/validate_docs.py
   import re
   from pathlib import Path

   def validate_master_index():
       # Parse MASTER_INDEX.md
       # Check all referenced files exist
       # Report missing files
       # Exit with error if files missing
   ```

2. **Add to pre-commit**
   - Run documentation validation on commit
   - Prevent broken documentation links

3. **Publish OpenAPI specs**
   - Extract OpenAPI specs from FastAPI apps
   - Generate static documentation
   - Publish to docs/api/

4. **Update MASTER_INDEX.md**
   - Add API documentation section
   - Add validation step to documentation workflow

#### Estimated Effort
- **Time**: 4-6 hours
- **Complexity**: Low (scripting)
- **Risk**: Low (non-breaking)

### Phase 8: Type Checking Tracking (Priority P3)

#### Current State
- **Files with # mypy: ignore-errors**: 2 (down from 73 in v0.4.17)
- **Location**:
  - apps/blockchain-node/src/aitbc_chain/rpc/router.py
  - apps/blockchain-node/src/aitbc_chain/rpc/gpu_resources.py

#### Implementation Tasks

1. **Create TYPE_CHECKING.md**
   ```markdown
   # Type Checking Status

   ## Files with Type Ignores

   ### blockchain-node/src/aitbc_chain/rpc/router.py
   - **Reason**: Complex conditional imports and dynamic module loading
   - **Target date**: v0.4.24
   - **Action**: Refactor to use dependency injection

   ### blockchain-node/src/aitbc_chain/rpc/gpu_resources.py
   - **Reason**: Pending investigation
   - **Target date**: v0.4.24
   - **Action**: Investigate and fix

   ## Progress
   - v0.4.17: 73 files with ignores
   - v0.4.20: 37 files with ignores
   - v0.4.22: 2 files with ignores
   - v0.4.23: Target 0 files
   ```

2. **Fix remaining 2 files**
   - Investigate router.py type errors
   - Investigate gpu_resources.py type errors
   - Apply fixes or document justified ignores

3. **Add to CI**
   - Fail CI if new # mypy: ignore-errors added without documentation
   - Track type checking debt

#### Estimated Effort
- **Time**: 2-4 hours
- **Complexity**: Low (2 files only)
- **Risk**: Low (documentation + fixes)

## 🎯 Success Criteria

### Minimum Viable v0.4.23
- [ ] aitbc/__init__.py split into submodules (backward compatible)
- [ ] All services migrated to aitbc_logging (18 services)
- [ ] X-Request-ID propagation middleware implemented
- [ ] Integration test matrix created
- [ ] Wrapper script template created

### Stretch Goals
- [ ] All 24 wrapper scripts generated from template
- [ ] Security hardening complete (hardcoded ports removed)
- [ ] Documentation validation script implemented
- [ ] OpenAPI specs published
- [ ] Type checking tracking document created
- [ ] All # mypy: ignore-errors removed (0 files)
- [ ] Test coverage improved to 50%+

## 📅 Timeline Estimate

| Phase | Estimated Time | Priority | Status |
|-------|---------------|----------|--------|
| Phase 1: Architecture refactoring | 8-12 hours | P0 | 📋 Pending |
| Phase 2: Logging standardization | 6-8 hours | P1 | 📋 Pending |
| Phase 3: X-Request-ID propagation | 4-6 hours | P1 | 📋 Pending |
| Phase 4: CI/CD improvements | 8-10 hours | P2 | 📋 Pending |
| Phase 5: Wrapper script templating | 6-8 hours | P2 | 📋 Pending |
| Phase 6: Security hardening | 4-6 hours | P2 | 📋 Pending |
| Phase 7: Documentation validation | 4-6 hours | P3 | 📋 Pending |
| Phase 8: Type checking tracking | 2-4 hours | P3 | 📋 Pending |
| **Phase 9: B008 Lint Refactor** | **12-16 hours** | **P2** | **📋 Pending** |
| **Total** | **54-76 hours** | - | 📋 **Planning** |

### Execution Order
1. **Phase 1**: Architecture refactoring (foundational, affects everything)
2. **Phase 2**: Logging standardization (observability foundation)
3. **Phase 3**: X-Request-ID propagation (builds on logging)
4. **Phase 4**: CI/CD improvements (quality infrastructure)
5. **Phase 5**: Wrapper script templating (operational excellence)
6. **Phase 6**: Security hardening (security improvements)
7. **Phase 7**: Documentation validation (documentation quality)
8. **Phase 8**: Type checking tracking (type safety completion)
9. **Phase 9**: B008 Lint Refactor (linting quality completion)

## 🔧 Technical Considerations

### Architecture Refactoring Risks
- **Breaking changes**: Maintain backward compatibility during transition
- **Import updates**: Use automated refactoring tools where possible
- **Testing**: Comprehensive testing after each migration step

### Logging Standardization Risks
- **Service-specific requirements**: Some services may need custom logging
- **Performance**: Ensure structured logging doesn't impact performance
- **Backward compatibility**: Ensure log aggregation systems handle new format

### Observability Enhancement Risks
- **Propagation failures**: Handle missing correlation IDs gracefully
- **Performance overhead**: Minimize overhead of correlation ID tracking
- **Storage**: Ensure log storage can handle additional fields

### Phase 9: B008 Lint Refactor (Priority P2)

#### Current State
- **B008 violations**: 1,105 instances across ~200+ files
- **Pattern**: `param: Type = Depends(...)` instead of `param: Annotated[Type, Depends(...)]`
- **Rule**: flake8-bugbear B008 - "Do not perform function calls in argument defaults"

#### Technical Challenge
Python's parameter default ordering prevents simple parameter-by-parameter fixes:
- Removing default from `param: Type = Depends(...)` creates parameter WITHOUT default
- Cannot be followed by parameters WITH defaults (syntax error)
- All `Depends` parameters in a function must be fixed SIMULTANEOUSLY
- Requires analyzing all function signatures for default ordering validity

#### Implementation Plan

1. **Phase 9a: LibCST Transformer Development**
   - Build AST-based transformer at `Parameters` node level (not individual `Param`)
   - Identify all functions with B008 violations
   - Group parameters by function, process all `Depends` params together
   - Validate default ordering before applying changes
   - Handle edge cases: `*args`, `**kwargs`, keyword-only params

2. **Phase 9b: Safety Validation**
   - Dry-run on entire codebase
   - Identify functions that CANNOT be safely fixed (parameter ordering conflicts)
   - Mark unsafe functions for manual review or `# noqa: B008`
   - Target: >95% auto-fix rate

3. **Phase 9c: Batch Application**
   - Apply validated transformations
   - Run `ruff check --select=B008` to verify zero violations
   - Add `Annotated` imports where needed

4. **Phase 9d: CI Integration**
   - Add B008 to flake8-bugbear select rules
   - Prevent regression with pre-commit hook

#### Estimated Effort
- **Time**: 12-16 hours
- **Complexity**: High (AST manipulation, parameter ordering constraints)
- **Risk**: Medium (requires careful validation, but non-breaking changes)

## 📝 Decisions Made

### ✅ Resolved Questions

1. **Should aitbc/__init__.py be split in v0.4.23?**
   - ✅ **DECIDED**: Yes - Priority P0
   - Rationale: Foundational improvement, enables better IDE support and maintainability

2. **Should all services migrate to aitbc_logging?**
   - ✅ **DECIDED**: Yes - Priority P1
   - Rationale: Unified observability, easier debugging, better log aggregation

3. **Should X-Request-ID propagation be added?**
   - ✅ **DECIDED**: Yes - Priority P1
   - Rationale: Critical for distributed tracing and debugging

4. **Should wrapper scripts be templated?**
   - ✅ **DECIDED**: Yes - Priority P2
   - Rationale: Reduces operational drift, improves maintainability

5. **Should test coverage gates be enforced?**
   - ✅ **DECIDED**: Yes - Priority P2
   - Rationale: Improves code quality, prevents regression

## 🚀 Execution Plan

### Immediate Next Steps
1. **Planning complete** - All decisions made
2. **Await approval** - Stakeholder review of plan
3. **Phase 1 execution** - Architecture refactoring (8-12 hours)
4. **Phase 2 execution** - Logging standardization (6-8 hours)
5. **Phase 3 execution** - X-Request-ID propagation (4-6 hours)
6. **Phase 4 execution** - CI/CD improvements (8-10 hours)
7. **Phase 5 execution** - Wrapper script templating (6-8 hours)
8. **Phase 6 execution** - Security hardening (4-6 hours)
9. **Phase 7 execution** - Documentation validation (4-6 hours)
10. **Phase 8 execution** - Type checking tracking (2-4 hours)
11. **Phase 9 execution** - B008 Lint Refactor (12-16 hours)
12. **Release complete** - All phases finished

### Phase 1 Execution Strategy
- Create new submodule structure without breaking changes
- Use automated refactoring for import updates
- Maintain backward compatibility during transition
- Test thoroughly after each migration step

---

## 📊 Expected Results

### Architecture
- ✅ **aitbc/__init__.py**: Reduced from 254 lines to <50 lines
- ✅ **Module structure**: Clear separation of concerns
- ✅ **IDE support**: Improved autocomplete and navigation
- ✅ **Import coupling**: Reduced dependencies between modules

### Observability
- ✅ **Logging**: All 24 services using aitbc_logging
- ✅ **Correlation IDs**: End-to-end request tracing
- ✅ **Structured logs**: Consistent JSON format across services
- ✅ **Debugging**: Easier distributed troubleshooting

### Quality
- ✅ **Test coverage**: Improved from 29% to 50%+
- ✅ **Test matrix**: Unit, integration, e2e, security separated
- ✅ **Coverage gates**: Enforced at 50% → 70% → 85%
- ✅ **Type safety**: 0 files with # mypy: ignore-errors

### Operations
- ✅ **Wrapper scripts**: Generated from template, consistent
- ✅ **Security**: Hardcoded values removed, configurable
- ✅ **Documentation**: Validated, no broken links
- ✅ **API docs**: OpenAPI specs published

### Summary
v0.4.23 targets architectural improvements, observability enhancement, and operational excellence:
- Split monolithic aitbc/__init__.py into submodules
- Migrate all 24 services to aitbc_logging
- Add X-Request-ID propagation for distributed tracing
- Implement integration test matrix with coverage gates
- Generate wrapper scripts from template
- Remove hardcoded security values
- Validate documentation links
- Complete type safety (0 type ignores)
- **Eliminate B008 lint violations (1,105 → 0) via LibCST refactor**

**Release Manager**: Development Team
**Reviewers**: Development Team
**Target Release Date**: 2026-06-22 (1 week planning + execution)
