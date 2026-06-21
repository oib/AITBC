# Agent A Tasks - v0.4.26

## High-Risk / Complex Refactoring Tasks

### P0: `aitbc/caching.py` (926 lines) — Highest Risk

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
1. Create `aitbc/cache/` subpackage directory
2. Move each class/function to its logical module:
   - `CacheEntry` dataclass → `core.py`
   - `LRUCache` class → `lru.py`
   - `TTLCache` class → `ttl.py`
   - `RedisCache` class → `redis_backend.py`
   - `BlockchainCache` class → `blockchain.py`
   - `@cached`, `@cached_lru`, `@cached_blockchain` decorators → `decorators.py`
   - `CacheInvalidator` class → `invalidation.py`
   - `CacheMetrics` + `get_cache_metrics`, `get_blockchain_cache`, `get_cache` → `metrics.py`
   - Key generators (`_generate_cache_key`, `generate_cache_key`) → `utils.py`
3. Update `aitbc/cache/__init__.py` to re-export everything for backward compatibility:
   ```python
   from .core import CacheEntry
   from .lru import LRUCache
   from .ttl import TTLCache
   from .redis_backend import RedisCache
   from .blockchain import BlockchainCache
   from .decorators import cached, cached_lru, cached_blockchain
   from .invalidation import CacheInvalidator
   from .metrics import CacheMetrics, get_cache_metrics, get_blockchain_cache, get_cache
   from .utils import _generate_cache_key, generate_cache_key
   ```
4. Replace `aitbc/caching.py` with a shim importing from `aitbc/cache/`:
   ```python
   # DEPRECATED: Use aitbc.cache instead
   from aitbc.cache import *
   import warnings
   warnings.warn("aitbc.caching is deprecated, use aitbc.cache", DeprecationWarning, stacklevel=2)
   ```
5. Deprecation cycle: keep shim for 1 release, then remove

**Classes/Functions to Migrate** (from `aitbc/caching.py`):
- `CacheEntry` dataclass (lines ~30-55)
- `BlockchainCache` class (lines ~57-200)
- `CacheMetrics` class (lines ~202-280)
- `LRUCache` class (lines ~282-360)
- `TTLCache` class (lines ~362-440)
- `cached` decorator (lines ~442-500)
- `cached_lru` decorator (lines ~502-550)
- `cached_blockchain` decorator (lines ~552-600)
- `CacheInvalidator` class (lines ~602-680)
- Module-level functions:
  - `get_cache_metrics()` (cached singleton)
  - `get_blockchain_cache()` (cached singleton)
  - `get_cache()` (generic cache)
  - `CacheInvalidator()` singleton
  - Key generators: `_generate_cache_key()`, `generate_cache_key()`

**Risk**: High — widely imported (`from aitbc import get_blockchain_cache`, `from aitbc.caching import LRUCache`). Requires careful backward-compat shim.

**Estimated effort**: 2-3 days

---

### P0: `aitbc/network/http_client.py` (654 lines) — Medium Risk

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
1. Split classes into separate modules:
   - `CircuitBreaker` class → `circuit_breaker.py`
   - `RateLimiter` class → `rate_limiter.py`
   - `RetryPolicy` class → `retry_policy.py`
   - `CacheLayer` class → `cache_layer.py`
   - `AITBCHTTPClient` + `AsyncAITBCHTTPClient` → `client.py`
2. Keep `http_client.py` as a shim importing from new modules
3. Update internal imports in apps/ to use new paths
4. Remove shim after 1 release

**Classes/Functions to Migrate** (from `aitbc/network/http_client.py`):
- `CircuitBreaker` class (lines ~30-120)
- `RateLimiter` class (lines ~122-200)
- `RetryPolicy` class (lines ~202-280)
- `CacheLayer` class (lines ~282-350)
- `AITBCHTTPClient` class (lines ~352-500)
- `AsyncAITBCHTTPClient` class (lines ~502-650)

**Risk**: Medium — imported by many apps but mostly as `from aitbc.network import AITBCHTTPClient` (already in `__init__.py`).

**Estimated effort**: 1-2 days

---

### P1: `aitbc/crypto/security.py` (490 lines)

**Current state**: Encryption, hashing, key derivation, JWT handling, password validation, and secure random generation all in one file.

**Target architecture**:
```
aitbc/crypto/
  __init__.py          # Already exists
  encryption.py        # EncryptionSuite, symmetric encryption
  hashing.py           # Hashing utilities, HMAC
  keys.py              # Key derivation, generation
  jwt_handler.py       # JWT encode/decode/validate
  password.py          # Password validation, strength checks
```

**Migration steps**:
1. Split into logical modules (crypto/ already exists)
2. Update `__init__.py` exports:
   ```python
   from .encryption import EncryptionSuite
   from .hashing import hash_data, verify_hash, hmac_sign, hmac_verify
   from .keys import generate_key, derive_key
   from .jwt_handler import JWTHandler, encode_jwt, decode_jwt, validate_jwt
   from .password import validate_password, generate_password_hash, verify_password
   ```
2. Update `__init__.py` exports
3. Keep backward compat in `security.py` as shim:
   ```python
   # DEPRECATED: Use aitbc.crypto instead
   from aitbc.crypto import *
   import warnings
   warnings.warn("aitbc.crypto.security is deprecated, use aitbc.crypto", DeprecationWarning, stacklevel=2)
   ```

**Classes/Functions to Migrate** (from `aitbc/crypto/security.py`):
- `EncryptionSuite` class (lines ~30-150)
- Hashing functions: `hash_data`, `verify_hash`, `hmac_sign`, `hmac_verify` (lines ~152-200)
- Key functions: `generate_key`, `derive_key` (lines ~202-260)
- `JWTHandler` class + `encode_jwt`, `decode_jwt`, `validate_jwt` (lines ~262-380)
- Password functions: `validate_password`, `generate_password_hash`, `verify_password` (lines ~382-490)

**Risk**: Low — most imports go through `aitbc.crypto` which already has `__init__.py`.

**Estimated effort**: 1 day

---

## Common Requirements for All Agent A Tasks:

1. **Tests first**: Write tests for new modules before deprecating shims
   - Target: 80%+ coverage on new modules
   - Run existing tests to ensure no regressions

2. **Backward compatibility**: Keep shims for 1 release cycle
   - Add `DeprecationWarning` with `stacklevel=2`
   - Document migration path in shim docstrings

3. **Run full test suite** after each refactor:
   ```bash
   pytest tests/ --ignore=tests/test_coordinator_api*.py -x -q
   ```

5. **Update imports**: Use `search_files` and `patch` to update internal imports across codebase:
   ```bash
   # Find all imports to update
   search_files(pattern="from aitbc.caching import", target="content")
   search_files(pattern="from aitbc.network.http_client import", target="content")
   search_files(pattern="from aitbc.crypto.security import", target="content")
   ```

6. **Document changes** in `docs/releases/v0.4.26/change.log`:
   - Add section for each refactored module
   - Note breaking changes and migration path

---

## Execution Order:

1. **Start with `crypto/security.py`** (lowest risk, crypto/ subpackage already exists)
   - Already has `aitbc/crypto/` directory with `__init__.py`
   - Only 490 lines, clear separation of concerns
   - Good warmup for refactoring patterns

2. **Then `network/http_client.py`** (medium risk, well-tested)
   - 654 lines, clear class boundaries
   - Already has `aitbc/network/` directory with `__init__.py`
   - Has existing tests (`tests/test_http_client.py`)

3. **Finally `caching.py`** (highest risk, most complex)
   - 926 lines, many interdependencies
   - No existing `aitbc/cache/` directory
   - Most widely used across codebase
   - Requires most careful shim design

---

*Source: `/opt/aitbc/docs/releases/v0.4.26/REFACTORING_PLANS.md` (full)*
*Reference: `/opt/aitbc/docs/releases/v0.4.26/issue.md` (issue tracking)*
*Reference: `/opt/aitbc/docs/releases/v0.4.26/change.log` (change tracking)*
