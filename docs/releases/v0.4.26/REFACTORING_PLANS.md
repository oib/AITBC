# Monolithic File Refactoring Plans

This document outlines planned refactoring for files in `aitbc/` exceeding 400 lines. Files over 500 lines are considered high-priority; those between 400-500 lines are medium-priority.

## Priority Matrix

| Priority | Lines | File | Status |
|----------|-------|------|--------|
| P0 | 926 | `aitbc/caching.py` | Planned |
| P0 | 654 | `aitbc/network/http_client.py` | Planned |
| P1 | 490 | `aitbc/crypto/security.py` | Planned |
| P1 | 475 | `aitbc/security_hardening.py` | Planned |
| P1 | 454 | `aitbc/agent_registry/src/registration.py` | Planned |
| P2 | 414 | `aitbc/training_setup/environment.py` | Planned |
| P2 | 406 | `aitbc/testing/testing.py` | Planned |
| P2 | 398 | `aitbc/queues/queue_manager.py` | Planned |

---

## P0: aitbc/caching.py (926 lines)

**Current state**: Single file containing all caching logic — in-memory LRU, TTL, Redis-backed cache, blockchain-specific cache, decorators, invalidation, and metrics.

**Target architecture**:
```
aitbc/cache/
  __init__.py          # Re-exports for backward compatibility
  core.py              # CacheEntry, base cache protocols
  lru.py               # LRUCache implementation
  ttl.py               # TTLCache implementation
  redis_backend.py     # RedisCache + connection handling
  blockchain.py        # BlockchainCache (specialized)
  decorators.py        # @cached, @cached_lru, @cached_blockchain
  invalidation.py      # CacheInvalidator + event handlers
  metrics.py           # CacheMetrics, get_cache_metrics()
  utils.py             # Key generators, singleton accessors
```

**Migration steps**:
1. Create `aitbc/cache/` subpackage
2. Move each class/function to its logical module
3. Update `aitbc/cache/__init__.py` to re-export everything
4. Replace `aitbc/caching.py` with a shim that imports from `aitbc/cache/`
5. Deprecation cycle: keep shim for 1 release, then remove

**Risk**: High — widely imported (`from aitbc import get_blockchain_cache`, `from aitbc.caching import LRUCache`). Requires careful backward-compat shim.

**Estimated effort**: 2-3 days

---

## P0: aitbc/network/http_client.py (654 lines)

**Current state**: Single file with HTTP client, circuit breaker, rate limiter, retry logic, caching layer, and both sync/async variants.

**Target architecture**:
```
aitbc/network/
  __init__.py           # Re-exports
  client.py             # AITBCHTTPClient + AsyncAITBCHTTPClient
  circuit_breaker.py    # CircuitBreaker state machine
  rate_limiter.py       # RateLimiter token bucket
  retry_policy.py       # Retry logic + backoff strategies
  cache_layer.py        # HTTP response caching
```

**Migration steps**:
1. Split classes into separate modules
2. Keep `http_client.py` as a shim importing from new modules
3. Update internal imports in apps/ to use new paths
4. Remove shim after 1 release

**Risk**: Medium — imported by many apps but mostly as `from aitbc.network import AITBCHTTPClient` (already in `__init__.py`).

**Estimated effort**: 1-2 days

---

## P1: aitbc/crypto/security.py (490 lines)

**Current state**: Encryption, hashing, key derivation, JWT handling, password validation, and secure random generation all in one file.

**Target architecture**:
```
aitbc/crypto/
  __init__.py          # Already exists
  encryption.py        # EncryptionSuite, symmetric encryption
  hashing.py           # Hashing utilities, HMAC
  keys.py              # Key derivation, generation
  jwt_handler.py       # JWT encode/decode/validate
  password.py            # Password validation, strength checks
```

**Migration steps**:
1. Split into logical modules (crypto/ already exists)
2. Update `__init__.py` exports
3. Keep backward compat in `security.py` as shim

**Risk**: Low — most imports go through `aitbc.crypto` which already has `__init__.py`.

**Estimated effort**: 1 day

---

## P1: aitbc/security_hardening.py (475 lines)

**Current state**: Security headers, CSP, HSTS, XSS protection, content sniffing, frame options, all in one module.

**Target architecture**:
```
aitbc/security/
  __init__.py           # Already exists (middleware)
  headers.py            # SecurityHeadersMiddleware
  csp.py                # Content-Security-Policy builder
  hsts.py               # HSTS configuration
  xss.py                # XSS protection
```

**Note**: Could also be merged into `aitbc/middleware/` since security hardening is middleware-related.

**Migration steps**:
1. Move security header logic to `aitbc/security/` or `aitbc/middleware/`
2. Update `__init__.py` exports
3. Deprecate old module

**Risk**: Low — mostly used internally by middleware.

**Estimated effort**: 1 day

---

## P1: aitbc/agent_registry/src/registration.py (454 lines)

**Current state**: Agent registration, discovery, health tracking, and metadata management all in one file.

**Target architecture**:
```
aitbc/agent_registry/src/
  registration.py       # Core registration (shrunk)
  discovery.py          # Agent discovery logic
  health.py             # Health tracking
  metadata.py           # Metadata validation/storage
```

**Migration steps**:
1. Extract discovery, health, and metadata into separate modules
2. Keep `registration.py` focused on registration API

**Risk**: Low — internal to agent_registry package.

**Estimated effort**: 1 day

---

## P2: aitbc/training_setup/environment.py (414 lines)

**Current state**: Training environment configuration, validation, hardware detection, dependency checking, and dataset management.

**Target architecture**:
```
aitbc/training_setup/
  __init__.py           # Already exists
  environment.py        # Shrunk to core env config
  hardware.py           # GPU/CPU detection, memory checks
  dependencies.py       # Package version validation
  datasets.py           # Dataset path/setup management
```

**Risk**: Low — internal to training_setup package.

**Estimated effort**: 0.5-1 day

---

## P2: aitbc/testing/testing.py (406 lines)

**Current state**: Test fixtures, mock generators, assertion helpers, and test utilities all in one file.

**Target architecture**:
```
aitbc/testing/
  __init__.py           # Already exists
  fixtures.py           # Pytest fixtures
  mocks.py              # Mock generators
  assertions.py         # Custom assertion helpers
  factories.py          # Test data factories
```

**Risk**: Low — internal to testing package.

**Estimated effort**: 0.5-1 day

---

## P2: aitbc/queues/queue_manager.py (398 lines)

**Current state**: Task queue, job scheduler, worker pool, priority queue, debounce/throttle decorators all in one file.

**Target architecture**:
```
aitbc/queues/
  __init__.py           # Already exists
  queue.py              # TaskQueue, JobPriority
  scheduler.py          # JobScheduler
  workers.py            # WorkerPool
  decorators.py         # debounce, throttle
```

**Risk**: Low — internal to queues package.

**Estimated effort**: 0.5-1 day

---

## Summary

| Effort | Files |
|--------|-------|
| High (2-3 days) | `caching.py` |
| Medium (1-2 days) | `http_client.py` |
| Low (0.5-1 day each) | `security.py`, `security_hardening.py`, `registration.py`, `environment.py`, `testing.py`, `queue_manager.py` |

**Total estimated effort**: ~7-10 days

**Recommended order**:
1. Start with low-risk internal packages (`testing.py`, `queues/queue_manager.py`)
2. Then `security.py` and `security_hardening.py`
3. Then `http_client.py` (medium risk)
4. Finally `caching.py` (highest risk, most complex)

---
*Last updated: 2026-06-18*
