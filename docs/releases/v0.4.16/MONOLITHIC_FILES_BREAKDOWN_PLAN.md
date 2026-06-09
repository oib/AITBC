# Monolithic Files Breakdown Plan

## Overview
This document provides a detailed plan for breaking down 7 monolithic files (>700 lines) into smaller, focused modules following the single responsibility principle.

## Target Files

| File | Lines | Complexity | Priority |
|------|-------|------------|----------|
| `cli/aitbc_cli/commands/exchange.py` | 1,234 | High | 1 |
| `apps/exchange/simple_exchange_api.py` | 1,142 | High | 2 |
| `cli/aitbc_cli/commands/node.py` | 1,061 | High | 3 |
| `aitbc/caching.py` | 940 | Medium | 4 |
| `aitbc/network/http_client.py` | 746 | Low (deprecated) | 5 |
| `aitbc/database.py` | 719 | Medium | 6 |
| `apps/coordinator-api/src/app/main.py` | 796 | High | 7 |

**Total:** 6,638 lines across 7 files

## Strategy

### Principles
1. **Single Responsibility:** Each module should have one clear purpose
2. **Target Size:** <300 lines per file
3. **Logical Grouping:** Related functionality in same directory
4. **Backward Compatibility:** Keep old files as wrappers during migration
5. **Feature Flags:** Enable gradual rollout
6. **Comprehensive Testing:** Test each split independently

### Approach
1. **Analyze** each file to identify logical sections
2. **Design** new module structure
3. **Split** code into new modules
4. **Update** imports throughout codebase
5. **Test** each change independently
6. **Deploy** with feature flags
7. **Monitor** for issues
8. **Remove** old files after stable operation

## File-by-File Breakdown

### File 1: `cli/aitbc_cli/commands/exchange.py` (1,234 lines)

**Current Structure Analysis:**
- Exchange command CLI interface
- Multiple sub-commands (trade, order, wallet, etc.)
- Complex business logic mixed with CLI presentation

**Proposed Structure:**
```
cli/aitbc_cli/commands/exchange/
├── __init__.py              # Main command entry point (200 lines)
├── main.py                  # CLI command definitions (200 lines)
├── trade.py                 # Trade operations (300 lines)
├── order.py                 # Order management (300 lines)
├── wallet.py                # Wallet integration (200 lines)
└── utils.py                 # Helper functions (200 lines)
```

**Migration Steps:**
1. Create `exchange/` directory
2. Extract trade logic to `trade.py`
3. Extract order logic to `order.py`
4. Extract wallet logic to `wallet.py`
5. Extract helpers to `utils.py`
6. Create main CLI in `main.py`
7. Update `__init__.py` to export command
8. Update imports in parent `commands/__init__.py`
9. Test CLI commands
10. Remove old file

**Import Sites to Update:**
- `cli/aitbc_cli/commands/__init__.py`
- Any scripts importing `from aitbc_cli.commands.exchange import`

**Estimated Effort:** 3 days
**Risk Level:** Medium (CLI changes affect users)

---

### File 2: `apps/exchange/simple_exchange_api.py` (1,142 lines)

**Current Structure Analysis:**
- FastAPI application for exchange
- Multiple endpoints (orders, trades, auth, health)
- Mixed concerns (API, business logic, validation)

**Proposed Structure:**
```
apps/exchange/
├── api.py                   # Main FastAPI app (200 lines)
├── routes/
│   ├── __init__.py
│   ├── orders.py            # Order endpoints (300 lines)
│   ├── trades.py            # Trade endpoints (300 lines)
│   ├── auth.py              # Authentication (200 lines)
│   └── health.py            # Health checks (100 lines)
└── models.py                # Pydantic models (100 lines)
```

**Migration Steps:**
1. Create `routes/` directory
2. Extract order endpoints to `routes/orders.py`
3. Extract trade endpoints to `routes/trades.py`
4. Extract auth logic to `routes/auth.py`
5. Extract health checks to `routes/health.py`
6. Extract models to `models.py`
7. Create main app in `api.py`
8. Update imports
9. Test API endpoints
10. Remove old file

**Import Sites to Update:**
- Exchange service startup scripts
- Any services importing from `simple_exchange_api`

**Estimated Effort:** 3 days
**Risk Level:** Medium (API changes affect integrations)

---

### File 3: `cli/aitbc_cli/commands/node.py` (1,061 lines)

**Current Structure Analysis:**
- Node management CLI commands
- Status, sync, config operations
- Mixed concerns (CLI, business logic, validation)

**Proposed Structure:**
```
cli/aitbc_cli/commands/node/
├── __init__.py              # Main command entry point (200 lines)
├── main.py                  # CLI command definitions (200 lines)
├── status.py                # Node status operations (200 lines)
├── sync.py                  # Sync operations (300 lines)
├── config.py                # Configuration management (200 lines)
└── utils.py                 # Helper functions (200 lines)
```

**Migration Steps:**
1. Create `node/` directory
2. Extract status logic to `status.py`
3. Extract sync logic to `sync.py`
4. Extract config logic to `config.py`
5. Extract helpers to `utils.py`
6. Create main CLI in `main.py`
7. Update `__init__.py` to export command
8. Update imports in parent `commands/__init__.py`
9. Test CLI commands
10. Remove old file

**Import Sites to Update:**
- `cli/aitbc_cli/commands/__init__.py`
- Any scripts importing `from aitbc_cli.commands.node import`

**Estimated Effort:** 3 days
**Risk Level:** Medium (CLI changes affect users)

---

### File 4: `aitbc/caching.py` (940 lines)

**Current Structure Analysis:**
- Blockchain cache implementation
- Multiple cache types (LRU, TTL, invalidator)
- Mixed concerns (cache backends, metrics, invalidation)

**Proposed Structure:**
```
aitbc/cache/blockchain/
├── __init__.py              # Public API exports
├── cache.py                 # Blockchain cache (300 lines)
├── lru.py                   # LRU cache (200 lines)
├── ttl.py                   # TTL cache (200 lines)
├── invalidator.py           # Cache invalidation (200 lines)
└── metrics.py               # Cache metrics (100 lines)
```

**Migration Steps:**
1. Create `cache/blockchain/` directory
2. Extract main cache to `cache.py`
3. Extract LRU logic to `lru.py`
4. Extract TTL logic to `ttl.py`
5. Extract invalidation to `invalidator.py`
6. Extract metrics to `metrics.py`
7. Update `__init__.py` to maintain API
8. Update imports throughout codebase
9. Test cache functionality
10. Remove old file

**Import Sites to Update:**
- Any files importing from `aitbc.caching`
- Likely: blockchain-node, coordinator-api

**Estimated Effort:** 2 days
**Risk Level:** Low (internal module, limited imports)

---

### File 5: `aitbc/network/http_client.py` (746 lines)

**Current Structure Analysis:**
- HTTP client implementation
- Already deprecated (Task 2 replacement exists)
- Can be simplified or removed

**Proposed Action:**
- **Skip** - This file is already deprecated from Task 2
- Old implementation kept for backward compatibility
- New implementation in `aitbc/http/` is preferred
- Can be removed after migration period

**Migration Steps:**
1. Monitor usage of old HTTP client
2. Encourage migration to new `aitbc.http`
3. Remove after 2-3 months of deprecation

**Estimated Effort:** 0 days (already handled in Task 2)
**Risk Level:** None (deprecated)

---

### File 6: `aitbc/database.py` (719 lines)

**Current Structure Analysis:**
- Database connection management
- Session management
- Query utilities
- Mixed concerns (connection, session, queries)

**Proposed Structure:**
```
aitbc/database/
├── __init__.py              # Public API exports
├── connection.py            # Connection management (200 lines)
├── session.py               # Session management (200 lines)
├── queries.py               # Query utilities (200 lines)
└── utils.py                 # Helper functions (100 lines)
```

**Migration Steps:**
1. Create `database/` directory
2. Extract connection logic to `connection.py`
3. Extract session logic to `session.py`
4. Extract query utilities to `queries.py`
5. Extract helpers to `utils.py`
6. Update `__init__.py` to maintain API
7. Update imports throughout codebase
8. Test database operations
9. Remove old file

**Import Sites to Update:**
- Any files importing from `aitbc.database`
- Likely: blockchain-node, coordinator-api, many services

**Estimated Effort:** 2 days
**Risk Level:** Medium (database changes affect many services)

---

### File 7: `apps/coordinator-api/src/app/main.py` (796 lines)

**Current Structure Analysis:**
- FastAPI application setup
- Middleware configuration
- Router registration
- Lifecycle events
- Mixed concerns (app setup, middleware, routers, lifecycle)

**Proposed Structure:**
```
apps/coordinator-api/src/app/
├── main.py                  # FastAPI app setup (200 lines)
├── middleware.py            # Middleware configuration (200 lines)
├── routers.py               # Router registration (200 lines)
├── lifespan.py              # Startup/shutdown (100 lines)
└── config.py                # Configuration (100 lines)
```

**Migration Steps:**
1. Extract middleware to `middleware.py`
2. Extract router registration to `routers.py`
3. Extract lifecycle to `lifespan.py`
4. Extract config to `config.py`
5. Simplify `main.py` to orchestrate
6. Update imports
7. Test API startup
8. Test all endpoints
9. Remove old code from `main.py`

**Import Sites to Update:**
- Coordinator API startup scripts
- Any tests importing from `main.py`

**Estimated Effort:** 2 days
**Risk Level:** High (API startup changes)

---

## Execution Plan

### Phase 1: Preparation (Week 1)
**Goal:** Set up infrastructure and analyze files

**Tasks:**
1. Create feature flags for each file
2. Set up comprehensive test suite
3. Analyze import dependencies for each file
4. Create rollback branches
5. Document current behavior

**Deliverables:**
- Feature flag system
- Test suite baseline
- Dependency analysis report
- Rollback branches

### Phase 2: Low-Risk Files (Week 2)
**Goal:** Break down low-risk files first

**Files:**
- `aitbc/caching.py` (2 days)
- `aitbc/database.py` (2 days)
- Buffer time (1 day)

**Tasks:**
1. Split `aitbc/caching.py`
2. Test cache functionality
3. Split `aitbc/database.py`
4. Test database operations
5. Monitor for issues

**Deliverables:**
- Split cache module
- Split database module
- Test results
- Monitoring data

### Phase 3: Medium-Risk Files (Week 3)
**Goal:** Break down medium-risk files

**Files:**
- `cli/aitbc_cli/commands/node.py` (3 days)
- Buffer time (2 days)

**Tasks:**
1. Split `node.py`
2. Test CLI commands
3. Deploy with feature flag
4. Monitor for issues
5. Rollback if needed

**Deliverables:**
- Split node module
- Test results
- Deployment with feature flag
- Monitoring data

### Phase 4: High-Risk Files (Week 4)
**Goal:** Break down high-risk files

**Files:**
- `cli/aitbc_cli/commands/exchange.py` (3 days)
- Buffer time (2 days)

**Tasks:**
1. Split `exchange.py`
2. Test CLI commands
3. Deploy with feature flag
4. Monitor for issues
5. Rollback if needed

**Deliverables:**
- Split exchange module
- Test results
- Deployment with feature flag
- Monitoring data

### Phase 5: API Files (Week 5)
**Goal:** Break down API files

**Files:**
- `apps/exchange/simple_exchange_api.py` (3 days)
- `apps/coordinator-api/src/app/main.py` (2 days)
- Buffer time (2 days)

**Tasks:**
1. Split `simple_exchange_api.py`
2. Test API endpoints
3. Split `coordinator-api/main.py`
4. Test API startup
5. Deploy with feature flags
6. Monitor for issues
7. Rollback if needed

**Deliverables:**
- Split exchange API
- Split coordinator API
- Test results
- Deployment with feature flags
- Monitoring data

### Phase 6: Cleanup (Week 6)
**Goal:** Remove old files and finalize

**Tasks:**
1. Remove old files (after 2 weeks stable)
2. Update documentation
3. Remove feature flags
4. Final testing
5. Deploy to production

**Deliverables:**
- Clean codebase
- Updated documentation
- Final test results
- Production deployment

## Risk Management

### Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Breaking changes | Medium | High | Feature flags, rollback |
| Import errors | High | Medium | Comprehensive testing |
| Performance regression | Low | Medium | Benchmarking |
| User confusion | Medium | Low | Documentation, deprecation |

### Mitigation Strategies

**Feature Flags:**
- Enable/disable new implementations
- Gradual rollout (10% → 50% → 100%)
- Quick rollback if issues arise

**Comprehensive Testing:**
- Unit tests for each new module
- Integration tests for import changes
- End-to-end tests for CLI/API
- Performance benchmarks

**Rollback Plan:**
- Keep old files during migration
- Git branches for each file
- Feature flags for quick disable
- 2-week monitoring period

**Documentation:**
- Update import guides
- Document new structure
- Add migration examples
- Update API docs

## Testing Strategy

### Unit Tests
- Test each new module independently
- Test all exported functions/classes
- Test edge cases and error handling
- Mock external dependencies

### Integration Tests
- Test import chains
- Test CLI commands
- Test API endpoints
- Test database operations
- Test cache operations

### Regression Tests
- Compare behavior before/after split
- Performance benchmarking
- Memory usage comparison
- Error rate monitoring

### End-to-End Tests
- Full CLI workflow tests
- Full API workflow tests
- Database integration tests
- Cache integration tests

## Success Criteria

### File-Level Criteria
- [ ] All files <300 lines
- [ ] Clear module structure
- [ ] Single responsibility per module
- [ ] No circular dependencies
- [ ] Comprehensive tests

### Project-Level Criteria
- [ ] All imports updated
- [ ] Tests pass
- [ ] No performance regression
- [ ] Documentation updated
- [ ] No breaking changes

### Deployment Criteria
- [ ] Feature flags working
- [ ] Monitoring in place
- [ ] Rollback plan tested
- [ ] Team trained on new structure

## Timeline

**Total Estimated Effort:** 6 weeks

**Breakdown:**
- Week 1: Preparation
- Week 2: Low-risk files (caching, database)
- Week 3: Medium-risk files (node.py)
- Week 4: High-risk files (exchange.py)
- Week 5: API files (exchange API, coordinator API)
- Week 6: Cleanup and finalization

**Parallel Execution:**
- Can split files 2-3 at a time if team size allows
- Estimated 3-4 weeks with parallel execution

## Resources Required

### Development
- 2-3 senior developers
- Code review time
- Testing infrastructure

### Testing
- Test environment with all dependencies
- CI/CD pipeline updates
- Performance testing tools

### Documentation
- Technical writer
- Documentation review time
- User guide updates

### Operations
- Feature flag infrastructure
- Monitoring setup
- Rollback procedures

## Rollback Plan

### Per-File Rollback
1. Keep old file during migration
2. Feature flag to switch between old/new
3. Monitor for 1 week
4. If issues: disable feature flag
5. Remove new code
6. Investigate and fix
7. Retry migration

### Global Rollback
1. Git revert to pre-migration branch
2. Disable all feature flags
3. Restore old files
4. Investigate issues
5. Fix and retry

## Monitoring

### Metrics to Track
- Test pass rate
- Performance benchmarks
- Error rates
- Import success rate
- Feature flag usage

### Alert Thresholds
- Test pass rate < 95%
- Performance regression > 10%
- Error rate increase > 5%
- Import failure rate > 1%

## Dependencies

### External Dependencies
- None (pure refactoring)

### Internal Dependencies
- Task 1 (cache consolidation) - must be complete
- Task 2 (HTTP client consolidation) - must be complete
- Test infrastructure - must be available

## Approval Process

1. Create detailed design for each file
2. Review with team
3. Get approval from technical lead
4. Create implementation branch
5. Implement in phases
6. Code review after each phase
7. Deploy to staging
8. Monitor for 1 week
9. Deploy to production
10. Monitor for 2 weeks
11. Remove old files

## Conclusion

This plan provides a structured approach to breaking down 7 monolithic files into smaller, focused modules. The phased approach with feature flags and comprehensive testing minimizes risk while improving code maintainability.

**Estimated Effort:** 6 weeks (3-4 weeks with parallel execution)
**Risk Level:** Medium (mitigated by feature flags and testing)
**Expected Benefits:** Improved maintainability, better testability, easier onboarding
