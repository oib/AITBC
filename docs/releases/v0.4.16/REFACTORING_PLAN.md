# AITBC Codebase Refactoring Plan

## Overview

This document outlines a detailed plan for consolidating duplicate systems and breaking down monolithic files in the AITBC codebase. These are larger refactoring tasks that require careful planning and execution.

---

## Task 1: Consolidate Caching Systems

### Current State Analysis

**Existing Implementations:**
1. `aitbc/cache.py` (252 lines) - `AITBCCache` class with Redis backend
2. `aitbc/redis_cache.py` (280 lines) - `RedisCache` class with `get_cache()` function
3. `aitbc/caching.py` (940 lines) - `BlockchainCache`, `LRUCache`, `TTLCache`, `CacheInvalidator`
4. `aitbc/cache_decorators.py` (109 lines) - Three nearly identical decorators with different TTLs

**Import Usage (15+ locations):**
- `aitbc/config.py`: late import from `redis_cache`
- `aitbc/caching.py`: late imports from `redis_cache` (circular dependency)
- `aitbc/cache_decorators.py`: imports from `cache`
- `apps/blockchain-node/src/aitbc_chain/state/state_transition.py`: imports `RedisCache`
- `apps/blockchain-node/src/aitbc_chain/rpc/accounts.py`: imports `RedisCache`
- `apps/coordinator-api/src/app/utils/cache.py`: custom cache manager
- `apps/pool-hub/src/poolhub/redis_cache.py`: separate Redis cache implementation
- `apps/coordinator-api/src/app/contexts/language/`: uses `TranslationCache`

**Issues:**
- Circular dependencies between `cache.py`, `redis_cache.py`, and `caching.py`
- Inconsistent APIs (some use `get_cache()`, some instantiate classes directly)
- Duplicate functionality (4 cache backends, 15+ factory functions)
- No clear abstraction layer

### Proposed Architecture

```
aitbc/cache/
├── __init__.py          # Public API exports
├── base.py              # Abstract base class and interfaces
├── backends/
│   ├── __init__.py
│   ├── redis.py         # Redis backend (consolidated)
│   ├── memory.py        # In-memory LRU/TTL backends
│   └── null.py          # No-op backend for testing
├── decorators.py        # Unified decorators with TTL parameterization
└── utils.py             # Cache key generation, serialization helpers
```

**Public API:**
```python
from aitbc.cache import Cache, get_cache, cached, cache_with_ttl

# Usage
cache = get_cache(backend="redis", ttl=300)

@cached(ttl=600, key_prefix="blockchain")
def get_block(height: int) -> Block:
    ...

@cache_with_ttl(ttl=300)
def get_account(address: str) -> Account:
    ...
```

### Migration Strategy

**Phase 1: Create New Module (Week 1)**
1. Create `aitbc/cache/` directory structure
2. Implement `base.py` with abstract `CacheBackend` interface
3. Implement `backends/redis.py` consolidating `AITBCCache` and `RedisCache`
4. Implement `backends/memory.py` with `LRUCache` and `TTLCache`
5. Implement `backends/null.py` for testing
6. Implement `decorators.py` with parameterized `cache_with_ttl()`
7. Add deprecation warnings to old modules

**Phase 2: Update Imports (Week 2)**
1. Update `aitbc/__init__.py` to export new cache API
2. Update `aitbc/config.py` to use new cache
3. Update blockchain-node imports (2 files)
4. Update coordinator-api imports (5+ files)
5. Update pool-hub imports (3 files)
6. Run tests after each batch of changes

**Phase 3: Remove Old Code (Week 3)**
1. Remove late imports causing circular dependencies
2. Delete `aitbc/redis_cache.py` (after confirming no imports)
3. Delete `aitbc/cache.py` (after confirming no imports)
4. Consolidate `aitbc/caching.py` into new structure
5. Delete `aitbc/cache_decorators.py` (after confirming no imports)
6. Update documentation

**Phase 4: Testing & Validation (Week 4)**
1. Run full test suite
2. Performance benchmarking (ensure no regression)
3. Integration testing with real Redis
4. Update CI to test cache backends

### Risk Assessment

**High Risk:**
- Circular dependency resolution may break existing code
- Redis connection pooling changes may affect performance
- Cache key collisions if key generation changes

**Medium Risk:**
- Import path changes may break external dependencies
- Decorator signature changes may require code updates
- Memory cache size limits may affect behavior

**Mitigation:**
- Add deprecation warnings before removal
- Feature flag to switch between old/new implementations
- Comprehensive testing before removal
- Rollback plan (keep old code in branch)

### Testing Approach

**Unit Tests:**
- Test each cache backend independently
- Test cache key generation
- Test TTL expiration
- Test serialization/deserialization

**Integration Tests:**
- Test with real Redis instance
- Test cache invalidation
- Test concurrent access
- Test cache warming

**Performance Tests:**
- Benchmark old vs new implementations
- Measure memory usage
- Measure Redis connection pooling
- Measure cache hit/miss ratios

### Rollback Plan

1. Keep old cache modules in `aitbc/cache_legacy/` during migration
2. Feature flag to switch between implementations
3. If issues arise, revert to legacy implementation
4. Remove legacy code after 2 weeks of stable operation

### Timeline Estimate

- **Phase 1:** 1 week (create new module)
- **Phase 2:** 1 week (update imports)
- **Phase 3:** 1 week (remove old code)
- **Phase 4:** 1 week (testing & validation)
- **Total:** 4 weeks

---

## Task 2: Consolidate HTTP Client Implementations

### Current State Analysis

**Existing Implementations:**
1. `aitbc/network/http_client.py` (746 lines) - `AITBCHTTPClient` and `AsyncAITBCHTTPClient` using requests
2. `cli/aitbc_cli/utils/http_client.py` - `AITBCHTTPClient` using httpx
3. `cli/aitbc/__init__.py` - Another `AITBCHTTPClient` using requests
4. `apps/coordinator-api/src/app/utils/cache.py` - Custom HTTP client

**Import Usage (50+ locations):**
- CLI commands: `account.py`, `bridge.py`, `gpu_marketplace.py`, `market.py`, `simulate.py`, `transactions.py`, etc.
- CLI utils: `blockchain.py`, `chain_id.py`, `wallet_daemon_client.py`
- Tests: `test_http_client.py`, `test_exception_handling.py`, `test_import_surface.py`
- Coordinator API: various services

**Issues:**
- Same class name, different implementations
- Inconsistent interfaces (sync vs async)
- Different underlying libraries (requests vs httpx)
- No single source of truth
- Import confusion

### Proposed Architecture

```
aitbc/http/
├── __init__.py          # Public API exports
├── client.py            # Unified HTTP client with sync/async variants
├── backends/
│   ├── __init__.py
│   ├── requests.py      # Requests backend (sync)
│   ├── httpx.py         # Httpx backend (async)
│   └── aiohttp.py       # Aiohttp backend (async, optional)
├── exceptions.py        # Unified HTTP exceptions
└── utils.py             # Retry logic, timeout handling
```

**Public API:**
```python
from aitbc.http import HTTPClient, AsyncHTTPClient, NetworkError, ValidationError

# Sync client
client = HTTPClient(base_url="http://localhost:8202", timeout=30)
response = client.get("/rpc/account", params={"address": addr})

# Async client
async_client = AsyncHTTPClient(base_url="http://localhost:8202", timeout=30)
response = await async_client.get("/rpc/account", params={"address": addr})
```

### Migration Strategy

**Phase 1: Create New Module (Week 1)**
1. Create `aitbc/http/` directory structure
2. Implement `client.py` with unified interface
3. Implement `backends/requests.py` for sync client
4. Implement `backends/httpx.py` for async client
5. Implement `exceptions.py` with unified exception types
6. Add deprecation warnings to old clients

**Phase 2: Update CLI Imports (Week 2)**
1. Update `cli/aitbc/__init__.py` to export new HTTP client
2. Update `cli/aitbc_cli/utils/http_client.py` to use new implementation
3. Update all CLI command imports (15+ files)
4. Run CLI tests after each batch of changes

**Phase 3: Update Coordinator API (Week 3)**
1. Update coordinator-api imports (10+ files)
2. Update coordinator-api services
3. Run coordinator-api tests

**Phase 4: Remove Old Code (Week 4)**
1. Remove `cli/aitbc/__init__.py` HTTP client
2. Remove `cli/aitbc_cli/utils/http_client.py`
3. Consolidate `aitbc/network/http_client.py` into new structure
4. Update documentation

**Phase 5: Testing & Validation (Week 5)**
1. Run full test suite
2. Integration testing with real services
3. Performance benchmarking
4. Update CI to test HTTP clients

### Risk Assessment

**High Risk:**
- Breaking changes to CLI commands
- Async client changes may break coordinator-api
- Network timeout handling differences

**Medium Risk:**
- Import path changes may break external scripts
- Exception type changes may break error handling
- Retry logic differences may affect behavior

**Mitigation:**
- Add deprecation warnings before removal
- Feature flag to switch between implementations
- Comprehensive testing before removal
- Rollback plan (keep old code in branch)

### Testing Approach

**Unit Tests:**
- Test sync client with various HTTP methods
- Test async client with various HTTP methods
- Test timeout handling
- Test retry logic
- Test exception handling

**Integration Tests:**
- Test with real blockchain RPC
- Test with real coordinator API
- Test concurrent requests
- Test connection pooling

**Performance Tests:**
- Benchmark old vs new implementations
- Measure request latency
- Measure connection overhead
- Measure memory usage

### Rollback Plan

1. Keep old HTTP clients in `aitbc/http_legacy/` during migration
2. Feature flag to switch between implementations
3. If issues arise, revert to legacy implementation
4. Remove legacy code after 2 weeks of stable operation

### Timeline Estimate

- **Phase 1:** 1 week (create new module)
- **Phase 2:** 1 week (update CLI imports)
- **Phase 3:** 1 week (update coordinator-api)
- **Phase 4:** 1 week (remove old code)
- **Phase 5:** 1 week (testing & validation)
- **Total:** 5 weeks

---

## Task 3: Break Down Monolithic Files

### Current State Analysis

**Monolithic Files (>700 lines):**
1. `cli/aitbc_cli/commands/exchange.py` (1,234 lines)
2. `apps/exchange/simple_exchange_api.py` (1,142 lines)
3. `cli/aitbc_cli/commands/node.py` (1,061 lines)
4. `aitbc/caching.py` (940 lines)
5. `aitbc/network/http_client.py` (746 lines)
6. `aitbc/database.py` (719 lines)
7. `apps/coordinator-api/src/app/main.py` (796 lines)

**Total:** 6,638 lines across 7 files

### Proposed Structure

#### 1. `cli/aitbc_cli/commands/exchange.py` (1,234 lines)

**Split into:**
```
cli/aitbc_cli/commands/exchange/
├── __init__.py
├── main.py              # Main command handler (200 lines)
├── order.py             # Order management (300 lines)
├── trade.py             # Trade execution (300 lines)
├── wallet.py            # Wallet integration (200 lines)
└── utils.py             # Helper functions (200 lines)
```

#### 2. `apps/exchange/simple_exchange_api.py` (1,142 lines)

**Split into:**
```
apps/exchange/
├── api.py               # Main FastAPI app (200 lines)
├── routes/
│   ├── __init__.py
│   ├── orders.py        # Order endpoints (300 lines)
│   ├── trades.py        # Trade endpoints (300 lines)
│   ├── auth.py          # Authentication (200 lines)
│   └── health.py        # Health checks (100 lines)
└── models.py            # Pydantic models (100 lines)
```

#### 3. `cli/aitbc_cli/commands/node.py` (1,061 lines)

**Split into:**
```
cli/aitbc_cli/commands/node/
├── __init__.py
├── main.py              # Main command handler (200 lines)
├── status.py            # Node status (200 lines)
├── sync.py              # Sync operations (300 lines)
├── config.py            # Configuration (200 lines)
└── utils.py             # Helper functions (200 lines)
```

#### 4. `aitbc/caching.py` (940 lines)

**Split into:**
```
aitbc/cache/
├── __init__.py
├── blockchain.py        # Blockchain cache (300 lines)
├── lru.py               # LRU cache (200 lines)
├── ttl.py               # TTL cache (200 lines)
├── invalidator.py       # Cache invalidation (200 lines)
└── metrics.py           # Cache metrics (100 lines)
```

#### 5. `aitbc/network/http_client.py` (746 lines)

**Split into:**
```
aitbc/http/
├── __init__.py
├── client.py            # Main client (300 lines)
├── sync.py              # Sync implementation (200 lines)
├── async.py             # Async implementation (200 lines)
└── utils.py             # Helper functions (100 lines)
```

#### 6. `aitbc/database.py` (719 lines)

**Split into:**
```
aitbc/database/
├── __init__.py
├── connection.py        # Connection management (200 lines)
├── session.py           # Session management (200 lines)
├── models.py            # Base models (200 lines)
└── utils.py             # Helper functions (100 lines)
```

#### 7. `apps/coordinator-api/src/app/main.py` (796 lines)

**Split into:**
```
apps/coordinator-api/src/app/
├── main.py              # FastAPI app setup (200 lines)
├── middleware.py        # Middleware configuration (200 lines)
├── routers.py           # Router registration (200 lines)
├── lifespan.py          # Startup/shutdown (100 lines)
└── config.py            # Configuration (100 lines)
```

### Migration Strategy

**Phase 1: Create New Structure (Week 1)**
1. Create new directory structures
2. Split files into logical modules
3. Update imports within each module
4. Add `__init__.py` files with proper exports
5. Run syntax checks

**Phase 2: Update External Imports (Week 2)**
1. Update imports for exchange command
2. Update imports for exchange API
3. Update imports for node command
4. Update imports for caching
5. Update imports for HTTP client
6. Update imports for database
7. Update imports for coordinator-api
8. Run tests after each batch of changes

**Phase 3: Remove Old Files (Week 3)**
1. Delete old monolithic files
2. Update documentation
3. Update any remaining import references

**Phase 4: Testing & Validation (Week 4)**
1. Run full test suite
2. Integration testing
3. Performance testing
4. Update CI

### Risk Assessment

**High Risk:**
- Import path changes may break external dependencies
- Circular dependencies may emerge during splitting
- Test coverage may be insufficient for split modules

**Medium Risk:**
- Module structure may not be optimal
- Functionality may be inadvertently changed during split
- Documentation may become outdated

**Mitigation:**
- Keep old files during migration
- Comprehensive testing before deletion
- Code review for each split
- Update documentation immediately

### Testing Approach

**Unit Tests:**
- Test each new module independently
- Test imports between modules
- Test exported functions/classes

**Integration Tests:**
- Test CLI commands with split modules
- Test API endpoints with split modules
- Test database operations with split modules

**Regression Tests:**
- Compare behavior before/after split
- Performance benchmarking
- Memory usage comparison

### Rollback Plan

1. Keep old files in `*_legacy/` directories during migration
2. Feature flag to switch between implementations
3. If issues arise, revert to legacy implementation
4. Remove legacy code after 2 weeks of stable operation

### Timeline Estimate

- **Phase 1:** 1 week (create new structure)
- **Phase 2:** 1 week (update external imports)
- **Phase 3:** 1 week (remove old files)
- **Phase 4:** 1 week (testing & validation)
- **Total:** 4 weeks

---

## Overall Timeline

**Sequential Execution:**
- Task 1 (Caching): 4 weeks
- Task 2 (HTTP Client): 5 weeks
- Task 3 (Monolithic Files): 4 weeks
- **Total:** 13 weeks

**Parallel Execution (Recommended):**
- Task 1 (Caching): 4 weeks
- Task 2 (HTTP Client): 5 weeks (can overlap with Task 1 after Phase 1)
- Task 3 (Monolithic Files): 4 weeks (can overlap with Task 1 after Phase 1)
- **Total:** 8-10 weeks

## Success Criteria

### Task 1: Caching
- [ ] Single cache abstraction layer
- [ ] No circular dependencies
- [ ] All imports updated
- [ ] Tests pass
- [ ] Performance maintained or improved
- [ ] Documentation updated

### Task 2: HTTP Client
- [ ] Single HTTP client with sync/async variants
- [ ] Consistent interface across codebase
- [ ] All imports updated
- [ ] Tests pass
- [ ] Performance maintained or improved
- [ ] Documentation updated

### Task 3: Monolithic Files
- [ ] All files <300 lines
- [ ] Clear module structure
- [ ] All imports updated
- [ ] Tests pass
- [ ] No functionality changes
- [ ] Documentation updated

## Rollback Strategy

For each task:
1. Create feature branch before starting
2. Keep old code in `*_legacy/` directories
3. Add feature flags to switch implementations
4. Monitor for 2 weeks after deployment
5. Remove legacy code only after stable operation

## Monitoring & Validation

**Metrics to Track:**
- Test pass rate
- Performance benchmarks
- Error rates
- Cache hit/miss ratios (for Task 1)
- HTTP request latency (for Task 2)
- Memory usage

**Alert Thresholds:**
- Test pass rate < 95%
- Performance regression > 10%
- Error rate increase > 5%

## Dependencies

**External Dependencies:**
- None (pure refactoring)

**Internal Dependencies:**
- Task 1 should be completed before Task 3 (caching file is monolithic)
- Task 2 can be done in parallel with Task 1 after Phase 1
- Task 3 can be done in parallel with Task 1 after Phase 1

## Resources Required

**Development:**
- 1-2 senior developers
- Code review time
- Testing infrastructure

**Testing:**
- Test environment with Redis
- Test environment with blockchain RPC
- Test environment with coordinator API

**Documentation:**
- Technical writer
- Documentation review time

## Approval Process

1. Create detailed design document for each task
2. Review with team
3. Get approval from technical lead
4. Create implementation branch
5. Implement in phases
6. Code review after each phase
7. Deploy to staging
8. Monitor for 1 week
9. Deploy to production
10. Monitor for 2 weeks
11. Remove legacy code

## Conclusion

This refactoring plan provides a structured approach to consolidating duplicate systems and breaking down monolithic files. The phased approach with rollback options minimizes risk while improving code maintainability and reducing technical debt.

**Estimated Effort:** 8-10 weeks with parallel execution
**Risk Level:** Medium (mitigated by phased approach and rollback options)
**Expected Benefits:** Improved maintainability, reduced technical debt, better testability
