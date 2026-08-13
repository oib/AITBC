# v0.10.8 — Agent Task Assignment

**Last Updated**: 2026-07-06
**Version**: 1.0 — Deferred items from v0.10.7

**Release Theme**: Config Consolidation & Dead Retry Helper Cleanup — Resolve the `aitbc/config.py` vs `aitbc/config/hierarchical_config.py` package shadowing issue, consolidate simple health endpoints, and delete 3 unused retry helper implementations (zero production importers).

**Goal**: Close out the 3 deferred items from v0.10.7 §B5 and §B7. These are small, low-risk tasks that were deferred to avoid scope creep in v0.10.7.

> **Scope**: 3 tasks. (1) Merge `config.py` into `hierarchical_config.py` and delete the shadowed file + importlib hack, (2) Add `create_simple_health_response()` helper and update 11 services, (3) Delete 3 dead retry helpers and update their tests.
>
> **Prerequisites**: [v0.10.7](../v0.10.7/change.log) (✅ complete — dead code elimination & duplicate consolidation).
>
> **Risk**: Low. Config consolidation has only 1 production importer. Health endpoint helper is additive. Retry helpers have zero production importers (dead code). Mitigated by: comprehensive test suite.

---

## Task Split Overview

| Agent | Capability | Tasks | Focus |
|-------|------------|-------|-------|
| **Agent A** | SWE 1.6 (fast mechanical tasks) | 1 item | Delete 3 dead retry helpers + update tests |
| **Agent B** | GLM 5.2 (complex tasks) | 2 items | Config consolidation (package shadowing fix) + health endpoint helper |

**Conflict boundary**: Agent A owns retry helper deletion. Agent B owns config consolidation and health endpoints. No overlap.

---

## Agent A — Dead Retry Helper Cleanup (SWE 1.6)

**Scope**: Delete 3 retry helper implementations that have zero production importers. Keep `RetryPolicy` (used in production by `SharedHttpClient`) and `retry_until_deadline` (different pattern, used in `aitbc/utils/`).

**Working directory**: `/opt/aitbc/`

**Verification command**:

```bash
cd /opt/aitbc && ./venv/bin/python -m ruff check . && ./venv/bin/python -m pytest tests/unit -q -o addopts=""
```

### Tasks

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| A1 | Delete 3 dead retry helpers + update tests | 🟡 P2 | `cli/utils/__init__.py`, `aitbc/decorators/decorators.py`, `aitbc/async_helpers/async_helpers.py` + test files | ✅ |

### Agent A — Detailed Instructions

#### A1: Delete 3 dead retry helpers + update tests

**Problem**: Three retry helper implementations have **zero production importers** — they are only referenced in test files. The canonical retry implementation is `RetryPolicy` in `aitbc/network/retry_policy.py` (5 importers, used by `SharedHttpClient`).

**Files to modify**:

| File | Function | Lines | Importers |
|------|----------|-------|-----------|
| `cli/utils/__init__.py` | `retry_with_backoff()` | ~40 (lines 265-305) | 0 production, 1 test |
| `aitbc/decorators/decorators.py` | `retry()` decorator | ~43 (lines 17-59) | 0 production, 6 test usages |
| `aitbc/async_helpers/async_helpers.py` | `retry_async()` | ~28 (lines 129-156) | 0 production, 9 test usages |

**Keep** (do NOT delete):

- `aitbc/network/retry_policy.py` — `RetryPolicy` class (5 production importers, used by `SharedHttpClient`)
- `aitbc/utils/time_utils.py:284` — `retry_until_deadline()` (different pattern: deadline-based, not count-based; used in `aitbc/utils/__init__.py`)

**Fix**:

1. Delete `retry_with_backoff()` from `cli/utils/__init__.py`.
2. Delete `retry()` decorator from `aitbc/decorators/decorators.py`. Keep the file if it has other decorators; remove only the `retry` function and its imports if now unused.
3. Delete `retry_async()` from `aitbc/async_helpers/async_helpers.py`. Keep the file if it has other helpers.
4. Update test files:
   - `tests/test_decorators.py` — remove tests for `retry` and `retry_with_backoff`
   - `tests/test_async_helpers.py` — remove tests for `retry_async`
   - `tests/core/test_async_helpers_module.py` — remove tests for `retry_async`
   - `tests/core/test_decorators_module.py` — remove tests for `retry` if present

**Verification**:

```bash
# Verify no broken imports after deletion
grep -rn "retry_with_backoff\|from aitbc.decorators.*retry\|from aitbc.async_helpers.*retry_async" --include="*.py" . | grep -v __pycache__ | grep -v "test_" | grep -v "retry_policy" | grep -v "retry_until_deadline"
# Expected: no output (all production refs are to RetryPolicy or retry_until_deadline)

# Run tests
./venv/bin/python -m pytest tests/unit -q -o addopts=""
```

---

## Agent B — Config Consolidation & Health Endpoints (GLM 5.2)

**Scope**: (1) Resolve the `aitbc/config.py` vs `aitbc/config/hierarchical_config.py` package shadowing issue by merging into a single implementation. (2) Add `create_simple_health_response()` helper to `aitbc/health_checks.py` and update 11 services with simple copy-pasted health handlers.

**Working directory**: `/opt/aitbc/`

**Verification command**:

```bash
cd /opt/aitbc && ./venv/bin/python -m mypy --show-error-codes aitbc/ && ./venv/bin/python -m ruff check . && ./venv/bin/python -m pytest tests/unit -q -o addopts=""
cd /opt/aitbc/apps/coordinator-api && PYTHONPATH=src ../../venv/bin/python -m pytest tests -q -o addopts=""
```

### Tasks — Agent B — Config Consolidation & Health Endpoints (GLM 5.2)

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| B1 | Consolidate config.py into hierarchical_config.py (eliminate package shadowing) | 🟡 P2 | `aitbc/config.py`, `aitbc/config/hierarchical_config.py`, `aitbc/config/__init__.py` + 1 production importer + 5 test importers | ✅ |
| B2 | Add `create_simple_health_response()` helper + update 11 services | 🟡 P2 | `aitbc/health_checks.py` + 11 service `main.py` files | ✅ |

### Agent B — Detailed Instructions

#### B1: Consolidate config.py into hierarchical_config.py

**Problem**: `aitbc/config.py` (105 lines) is shadowed by the `aitbc/config/` package directory. Python imports the package, not the file. The `__init__.py` uses importlib hackery (lines 25-38) to load the shadowed file as `aitbc._legacy_config` and re-export its classes. This is fragile and confusing.

**Current state**:

- `aitbc/config.py` (105 lines) — `BaseAITBCConfig` (Pydantic BaseSettings), `AITBCConfig` (subclass). Has a broken import on line 89 (`from .redis_cache import get_cache` — should be `from .caching.redis_cache import get_cache`).
- `aitbc/config/hierarchical_config.py` (350 lines) — `HierarchicalConfig` (file loader), `ValidatedAITBCConfig` (Pydantic BaseSettings with more validators), `load_config()`, `create_config_template()`.
- `aitbc/config/__init__.py` (47 lines) — importlib hack to load shadowed `config.py`, exports both sets of classes.

**Importers** (all use `from aitbc.config import ...` — the package, not the file):

| File | Line | What it imports |
|------|------|-----------------|
| `apps/coordinator-api/src/app/config.py` | 13 | `BaseAITBCConfig` |
| `tests/test_imports.py` | 51 | `AITBCConfig`, `BaseAITBCConfig`, `HierarchicalConfig`, `ValidatedAITBCConfig`, `create_config_template`, `load_config` |
| `tests/unit/test_core.py` | 90 | `HierarchicalConfig` |
| `tests/test_hierarchical_config.py` | 6 | `HierarchicalConfig` |
| `tests/test_config.py` | 5 | `AITBCConfig`, `BaseAITBCConfig` |
| `tests/test_exception_handling.py` | 202 | `BaseAITBCConfig` |

**Overlap**: ~80% field overlap between `BaseAITBCConfig` and `ValidatedAITBCConfig`. The latter has better validation but is missing 9 fields from the former.

**Fix**:

**Step 1**: Add missing fields to `ValidatedAITBCConfig` in `aitbc/config/hierarchical_config.py`:

```python
database_max_overflow: int = Field(default=20, description="Maximum overflow connections")
database_pool_recycle: int = Field(default=3600, description="Connection recycle time in seconds")
database_pool_pre_ping: bool = Field(default=True, description="Test connections before using")
database_echo: bool = Field(default=False, description="Enable SQL query logging")
redis_url: str | None = Field(default=None, description="Redis connection URL")
redis_timeout: int = Field(default=5, description="Redis timeout in seconds")
rate_limit_requests: int = Field(default=60, description="Rate limit requests per window")
rate_limit_window_seconds: int = Field(default=60, description="Rate limit window in seconds")
allow_origins: list[str] = Field(default_factory=list, description="CORS allowed origins")
```

**Step 2**: Add missing methods to `ValidatedAITBCConfig`:

- `validate_secrets()` — copy from `BaseAITBCConfig`
- `validate_secret_length()` field_validator — copy from `BaseAITBCConfig`
- `get_redis_cache()` — copy from `BaseAITBCConfig` but fix the import path (`from aitbc.caching.redis_cache import get_cache`)

**Step 3**: Add `AITBCConfig` subclass to `hierarchical_config.py` (matching the one in `config.py`):

```python
class AITBCConfig(ValidatedAITBCConfig):
    """Main AITBC configuration."""
    app_name: str = Field(default="aitbc")
    port: int = Field(default=8000)
```

**Step 4**: Simplify `aitbc/config/__init__.py` — remove importlib hackery:

```python
from .hierarchical_config import (
    AITBCConfig,
    HierarchicalConfig,
    ValidatedAITBCConfig,
    create_config_template,
    load_config,
)

# Backward compatibility aliases
BaseAITBCConfig = ValidatedAITBCConfig

__all__ = [
    "AITBCConfig",
    "BaseAITBCConfig",
    "HierarchicalConfig",
    "ValidatedAITBCConfig",
    "create_config_template",
    "load_config",
]
```

**Step 5**: Delete `aitbc/config.py` (the shadowed file, 105 lines).

**Step 6**: Verify all importers still work — no changes needed to importers since they all use `from aitbc.config import ...` which resolves to the package.

**Verification**:

```bash
cd /opt/aitbc && ./venv/bin/python -m mypy --show-error-codes aitbc/ && ./venv/bin/python -m pytest tests/unit -q -o addopts=""
cd /opt/aitbc/apps/coordinator-api && PYTHONPATH=src ../../venv/bin/python -m pytest tests -q -o addopts=""
```

**Estimated impact**: Delete 105 lines (config.py) + ~13 lines (importlib hack). Add ~30 lines (missing fields/methods). Net reduction: ~88 lines.

---

#### B2: Add `create_simple_health_response()` helper + update 11 services

**Problem**: 11 services have copy-pasted simple health endpoint handlers that return `{"status": "healthy", "service": "<name>"}` with minor variations. The existing `HealthChecker` class in `aitbc/health_checks.py` is overkill for services that just need a static health response.

**Current patterns** (11 services):

| Service | File | Pattern |
|---------|------|---------|
| edge-api | `apps/edge/src/aitbc_edge/main.py:92` | `{"status": "healthy", "service": "edge-api", "version": "0.1.0"}` |
| marketplace | `apps/marketplace/src/marketplace_service/main.py:68` | `HealthResponse(status="healthy", service="marketplace-service")` |
| api-gateway | `apps/api-gateway/src/api_gateway/main.py:158` | `{"status": "healthy", "service": "api-gateway"}` |
| trading | `apps/trading/src/trading_service/main.py:114` | `HealthResponse(status="healthy", service="trading")` |
| gpu | `apps/gpu/src/gpu_service/main.py:131` | `HealthResponse(status="healthy", service="gpu-service")` |
| governance | `apps/governance/src/governance_service/main.py:61` | `HealthResponse(status="healthy", service="governance-service")` |
| coordinator-api | `apps/coordinator-api/src/app/core/app.py:29` | `{"status": "healthy", "service": "coordinator-api"}` |
| blockchain-explorer | `apps/blockchain-explorer/main.py:34` | includes node_status check |
| blockchain-event-bridge | `apps/blockchain-event-bridge/src/blockchain_event_bridge/main.py:45` | includes bridge_running check |
| ffmpeg | `apps/ffmpeg/main.py:47` | checks ffmpeg availability |
| whisper | `apps/whisper/main.py:45` | checks model readiness |

**Note**: The 30+ coordinator-api context routers have specialized health checks (database, GPU, CUDA, algorithms) — do NOT consolidate those.

**Fix**:

**Step 1**: Add `create_simple_health_response()` to `aitbc/health_checks.py`:

```python
def create_simple_health_response(
    service_name: str,
    version: str | None = None,
    **extra_fields: Any,
) -> dict[str, Any]:
    """Create a simple health response dict.

    Args:
        service_name: Name of the service.
        version: Optional version string.
        **extra_fields: Additional fields to include in the response.

    Returns:
        Dict with status, service, and any extra fields.
    """
    response: dict[str, Any] = {"status": "healthy", "service": service_name}
    if version:
        response["version"] = version
    if extra_fields:
        response.update(extra_fields)
    return response
```

**Step 2**: Update the 7 services with the simplest pattern (static response):

- edge-api, api-gateway, trading, gpu, governance, marketplace, coordinator-api (core/app.py)

Replace their inline health handlers with:

```python
from aitbc.health_checks import create_simple_health_response

@app.get("/health")
async def health() -> dict[str, Any]:
    return create_simple_health_response("service-name", version="0.1.0")
```

**Step 3**: For the 4 services with dynamic checks (blockchain-explorer, blockchain-event-bridge, ffmpeg, whisper), use `create_simple_health_response()` as the base and add their specific checks via `extra_fields`:

```python
@app.get("/health")
async def health() -> dict[str, Any]:
    return create_simple_health_response("blockchain-event-bridge", bridge_running=bridge.is_running)
```

**Step 4**: Export `create_simple_health_response` from `aitbc/health_checks.py` `__all__`.

**Verification**:

```bash
cd /opt/aitbc && ./venv/bin/python -m pytest tests/unit -q -o addopts=""
# Verify health endpoints still return expected fields
./venv/bin/python -c "from aitbc.health_checks import create_simple_health_response; print(create_simple_health_response('test', version='1.0'))"
```

**Estimated impact**: Add ~15 lines (helper function). Update 11 services (~2 lines each saved). Net reduction: ~7 lines. The value is in eliminating the copy-paste pattern, not line count.

---

## Coordination Notes

### No coordination required

Agent A and Agent B tasks are independent:

- Agent A deletes dead retry helpers (no business logic impact, zero production importers)
- Agent B consolidates config (1 production importer) and adds health helper (additive)

### Shared files to watch

None — no overlap between tasks.

---

## Verification Checklist

After completing all tasks:

- [ ] 3 dead retry helpers deleted (`retry_with_backoff`, `retry` decorator, `retry_async`)
- [ ] `RetryPolicy` and `retry_until_deadline` kept (production-used)
- [ ] `aitbc/config.py` deleted (shadowed file eliminated)
- [ ] `ValidatedAITBCConfig` has all fields from `BaseAITBCConfig`
- [ ] `aitbc/config/__init__.py` importlib hackery removed
- [ ] `BaseAITBCConfig` is a backward-compat alias for `ValidatedAITBCConfig`
- [ ] `create_simple_health_response()` helper added to `aitbc/health_checks.py`
- [ ] 11 services updated to use shared health helper
- [ ] All tests pass (`./venv/bin/python -m pytest tests/unit -q -o addopts=""`)
- [ ] Coordinator-api tests pass (`cd apps/coordinator-api && PYTHONPATH=src ../../venv/bin/python -m pytest tests -q -o addopts=""`)
- [ ] Type check passes (`./venv/bin/python -m mypy --show-error-codes aitbc/`)
- [ ] Lint passes (`./venv/bin/python -m ruff check .`)
