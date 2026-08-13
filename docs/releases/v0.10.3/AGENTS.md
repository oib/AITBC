# v0.10.3 — Agent Task Assignment

**Last Updated**: 2026-07-05
**Version**: 2.0 — Refactored for agent capabilities

**Release Theme**: Bug Fix & Hardening — Fix critical runtime bugs, eliminate resource leaks, resolve race conditions, and correct configuration mismatches discovered during comprehensive codebase analysis.

**Goal**: Production readiness from a correctness and resource management standpoint. No new features — fix financial correctness bugs, resource leaks, concurrency issues, and configuration mismatches. 29 issues identified across shared core, CLI, and all application services.

> **Scope**: All critical and high-priority bugs from the codebase analysis. Medium and low issues are included as time permits.
>
> **Prerequisites**: [v0.10.2](../v0.10.2/change.log) (complete — all mock/placeholder implementations replaced).
>
> **Risk**: Medium. Financial correctness fixes require careful testing. Resource leak fixes are mechanical but require verification. Configuration changes may affect deployments. Mitigated by: (1) comprehensive test suite, (2) live testing on shop node, (3) rollback plan for schema migrations.

---

## Task Split Overview

| Agent | Capability | Tasks | Focus |
|-------|------------|-------|-------|
| **Agent A** | SWE 1.6 (fast mechanical tasks) | 14 items | Simple config changes, mechanical refactoring, deprecated module removal, simple logging additions |
| **Agent B** | GLM 5.2 (complex tasks) | 15 items | Financial correctness bugs, database migrations, async refactoring, transaction semantics, security patterns |

**Conflict boundary**: Agent A owns simple mechanical fixes across the codebase. Agent B owns complex business logic and architectural changes. No coordination required — tasks are independent.

**Rationale**: SWE 1.6 excels at fast, mechanical code changes (config updates, simple refactors, module removal). GLM 5.2 handles complex tasks requiring deeper understanding of business logic, database semantics, async patterns, and security considerations.

---

## Agent A — Mechanical Fixes (SWE 1.6)

**Scope**: Simple, mechanical code changes that don't require deep business logic understanding. Config updates, deprecated module removal, simple logging additions, straightforward refactoring patterns.

**Working directory**: `/opt/aitbc/`

**Verification command**:

```bash
cd /opt/aitbc && ./venv/bin/python -m ruff check . && ./venv/bin/python -m pytest tests/unit -q -o addopts=""
```

### Tasks

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| A1 | Remove deprecated shim modules | 🟢 P2 | `aitbc/cache.py`, `cache_decorators.py`, `redis_cache.py`, `network/http_client.py`, `crypto/security.py` | ✅ |
| A2 | Fix CLI coordinator_url AttributeError | 🔴 P0 | `cli/aitbc_cli/config.py`, `cli/aitbc_cli/commands/*.py` | ✅ |
| A3 | Fix CLI and service port mismatches | 🔴 P0 | `cli/aitbc_cli/config.py`, `apps/miner/production_miner.py`, `apps/edge/src/aitbc_edge/config.py` | ✅ |
| A4 | Remove hardcoded secret_key in agent-coordinator | 🟡 P1 | `apps/agent-coordinator/src/app/config.py` | ✅ |
| A5 | Remove hardcoded wallet passwords | 🟡 P1 | `apps/wallet/src/app/main.py` | ✅ |
| A6 | Fix hardcoded blockchain RPC URLs | 🟡 P1 | `apps/coordinator-api/src/app/settlement/hooks.py`, `apps/coordinator-api/src/app/contexts/governance/services/governance_service.py` | ✅ |
| A7 | Fix CLI pool-hub routing | 🟢 P2 | `cli/aitbc_cli/commands/pool_hub.py` | ✅ |
| A8 | Fix CLI mining routing | 🟢 P2 | `cli/aitbc_cli/commands/mining.py` | ✅ |
| A9 | Add database indexes for performance | 🟢 P2 | `apps/coordinator-api/src/app/contexts/infrastructure/domain/user.py`, `apps/exchange/models.py` | ✅ |
| A10 | Improve exception handling in agent_bridge | 🟢 P2 | `aitbc/agent_bridge/src/integration_layer.py` | ✅ |
| A11 | Add thread safety to SecretManager | 🟡 P1 | `aitbc/crypto/secrets.py` | ✅ |
| A12 | Fix unclosed HTTP clients in edge apps | 🟡 P1 | `apps/edge/src/aitbc_edge/clients/blockchain_rpc.py`, `apps/edge/src/aitbc_edge/clients/gpu_service.py` | ✅ |
| A13 | Fix unclosed HTTP client in CLI utils | 🟡 P1 | `cli/aitbc_cli/utils/http_client.py` | ✅ |
| A14 | Fix unclosed HTTP clients in bridge/trading (mechanical pattern) | 🔴 P0 | `aitbc/bridge/client.py`, `aitbc/trading/offer_client.py`, `aitbc/trading/subscription_client.py` | ✅ |

### Agent A — Detailed Instructions

#### A1: Remove deprecated shim modules

**Files**:

- `aitbc/cache.py` (re-exports from caching)
- `aitbc/cache_decorators.py` (re-exports from caching)
- `aitbc/redis_cache.py` (re-exports from caching)
- `aitbc/network/http_client.py` (re-exports from network submodules)
- `aitbc/crypto/security.py` (re-exports from crypto submodules)

**Problem**: Deprecated shims clutter the codebase and may confuse developers.

**Fix**:

1. Search for all imports of these modules across the codebase:

   ```bash
   grep -r "from aitbc.cache\|from aitbc.cache_decorators\|from aitbc.redis_cache\|from aitbc.network.http_client\|from aitbc.crypto.security" . --include="*.py"
   ```

2. Update imports to use new locations:
   - `aitbc.cache` → `aitbc.caching`
   - `aitbc.cache_decorators` → `aitbc.caching.decorators`
   - `aitbc.redis_cache` → `aitbc.caching.redis_cache`
   - `aitbc.network.http_client` → `aitbc.network.client`
   - `aitbc.crypto.security` → `aitbc.crypto.security_hardening` (or specific submodule)
3. Delete the deprecated files
4. Run tests to verify no broken imports

**Verification**: `grep -r "from aitbc.cache\|from aitbc.cache_decorators\|from aitbc.redis_cache\|from aitbc.network.http_client\|from aitbc.crypto.security" . --include="*.py"` returns no results.

---

#### A2: Fix CLI coordinator_url AttributeError

**Files**:

- `cli/aitbc_cli/config.py` — add property
- `cli/aitbc_cli/commands/simulate.py` — lines 352, 379, 399
- `cli/aitbc_cli/commands/agent_sdk.py` — lines 61, 84, 702-764
- `cli/aitbc_cli/commands/edge.py` — lines 30, 47
- `cli/aitbc_cli/commands/ai.py` — 10 call sites

**Problem**: `CLIConfig` only has `agent_coordinator_url`, but commands reference `config.coordinator_url`.

**Fix**:

1. Add property to `CLIConfig` in `cli/aitbc_cli/config.py`:

   ```python
   @property
   def coordinator_url(self) -> str:
       """Deprecated alias for agent_coordinator_url"""
       return self.agent_coordinator_url
   ```

2. Update all call sites to use `agent_coordinator_url` directly (find-replace):
   - `config.coordinator_url` → `config.agent_coordinator_url`

**Verification**: Run CLI commands, verify no AttributeError.

---

#### A3: Fix CLI and service port mismatches

**Files**:

- `cli/aitbc_cli/config.py` — line 44 (edge_api_port)
- `apps/miner/production_miner.py` — line 15 (COORDINATOR_URL)
- `apps/edge/src/aitbc_edge/config.py` — line 41 (agent_coordinator_url)

**Problem**: Port defaults don't match actual service ports.

**Fix**:

1. Update `cli/aitbc_cli/config.py` line 44:

   ```python
   edge_api_port: int = Field(default=8111, description="Edge API port")
   ```

2. Update `apps/miner/production_miner.py` line 15:

   ```python
   COORDINATOR_URL = os.environ.get("COORDINATOR_URL", "http://127.0.0.1:8107")
   ```

3. Update `apps/edge/src/aitbc_edge/config.py` line 41:

   ```python
   agent_coordinator_url: str = "http://localhost:8107"
   ```

**Verification**: Test CLI edge commands connect to port 8111. Test miner connects to 8107.

---

#### A4: Remove hardcoded secret_key in agent-coordinator

**File**: `apps/agent-coordinator/src/app/config.py` — line 91

**Problem**: Default `secret_key="default_secret_key_change_in_production"` is insecure.

**Fix**:

1. Remove default, make field required:

   ```python
   secret_key: str = Field(..., description="JWT secret key (required)")
   ```

2. Add validation in production mode:

   ```python
   @model_validator(mode='after')
   def validate_secret_key(self):
       if self.environment == "production" and self.secret_key == "default_secret_key_change_in_production":
           raise ValueError("secret_key must be set in production")
       return self
   ```

**Verification**: Test that service fails to start without secret_key in production mode.

---

#### A5: Remove hardcoded wallet passwords

**File**: `apps/wallet/src/app/main.py` — lines 42, 82

**Problem**: Hardcoded passwords `"Aitbc-Import-Pass1"`, `"Aitbc-Password-123"`.

**Fix**:

1. Remove defaults
2. Require passwords via environment variables:

   ```python
   WALLET_IMPORT_PASSWORD = os.environ.get("WALLET_IMPORT_PASSWORD")
   if not WALLET_IMPORT_PASSWORD:
       raise RuntimeError("WALLET_IMPORT_PASSWORD must be set")
   ```

3. Apply same pattern for wallet password

**Verification**: Test that wallet service fails without passwords.

---

#### A6: Fix hardcoded blockchain RPC URLs

**Files**:

- `apps/coordinator-api/src/app/settlement/hooks.py` — line 166
- `apps/coordinator-api/src/app/contexts/governance/services/governance_service.py` — line 283

**Problem**: Hardcoded `http://localhost:8202` instead of using `settings.blockchain_rpc_url`.

**Fix**:

1. In `settlement/hooks.py` line 166:

   ```python
   # Before
   url = "http://localhost:8202/rpc/chain"
   # After
   url = f"{settings.blockchain_rpc_url}/rpc/chain"
   ```

2. In `governance_service.py` line 283:

   ```python
   # Before
   url = "http://localhost:8202"
   # After
   url = settings.blockchain_rpc_url
   ```

**Verification**: Test that services use configured RPC URL.

---

#### A7: Fix CLI pool-hub routing

**File**: `cli/aitbc_cli/commands/pool_hub.py` — lines 23, 49

**Problem**: Commands call `/rpc/pool_hub/*` on blockchain node instead of pool-hub service.

**Fix**:

1. Change base URL to pool-hub service:

   ```python
   pool_hub_url = "http://localhost:8203"
   response = requests.post(f"{pool_hub_url}/api/pools/join", ...)
   ```

2. Update endpoint paths to match pool-hub API

**Verification**: Test CLI pool-hub commands work.

---

#### A8: Fix CLI mining routing

**File**: `cli/aitbc_cli/commands/mining.py` — lines 47, 73, 94, 112

**Problem**: Commands call `/rpc/mining/*` endpoints that may not exist.

**Fix**:

1. Verify blockchain-node RPC exposes these endpoints by checking `apps/blockchain-node/src/aitbc_chain/rpc/router.py`
2. If endpoints exist, no change needed
3. If not, update to correct paths or add error message:

   ```python
   try:
       response = requests.post(f"{node_url}/rpc/mining/submit", ...)
   except requests.exceptions.HTTPError as e:
       if e.response.status_code == 404:
           error("Mining RPC endpoint not found. Check blockchain-node RPC configuration.")
       raise
   ```

**Verification**: Test CLI mining commands work or show helpful error.

---

#### A9: Add database indexes for performance

**Files**:

- `apps/coordinator-api/src/app/contexts/infrastructure/domain/user.py` — lines 39, 59, 58
- `apps/exchange/models.py` — line 50

**Problem**: Frequently filtered columns lack indexes.

**Fix**:

1. In `user.py`, add `index=True` to columns:

   ```python
   balance = Column(Numeric(18, 8), index=True)
   amount = Column(Numeric(18, 8), index=True)
   status = Column(String, index=True)
   ```

2. In `exchange/models.py`, add index:

   ```python
   status = Column(String, index=True)
   ```

3. Create database migration for exchange (coordinator-api uses SQLModel metadata.create_all):

**Verification**: Run `EXPLAIN` on queries to verify index usage.

---

#### A10: Improve exception handling in agent_bridge

**File**: `aitbc/agent_bridge/src/integration_layer.py` — lines 43-44, 52-53, 61-62, 72-73

**Problem**: All service methods catch `Exception` and return generic error dict, losing stack traces.

**Fix**:

1. Add logger import at top of file:

   ```python
   import logging
   logger = logging.getLogger(__name__)
   ```

2. Update each exception handler to log full traceback:

   ```python
   except Exception as e:
       logger.exception("Service call failed: %s", service_name)
       return {"error": str(e), "status": "failed"}
   ```

**Verification**: Test that exceptions are logged with full traceback.

---

#### A11: Add thread safety to SecretManager

**File**: `aitbc/crypto/secrets.py` — lines 242-264

**Problem**: Background rotation thread mutates `self.secrets` without locking.

**Fix**:

1. Add import at top:

   ```python
   import threading
   ```

2. In `__init__`, add lock:

   ```python
   self._lock = threading.Lock()
   ```

3. Protect all `self.secrets` access in the class:

   ```python
   with self._lock:
       self.secrets[key] = value
   ```

4. Update `cleanup_expired_secrets()` to use lock

**Verification**: Run existing tests (no new test needed for this simple change).

---

#### A12: Fix unclosed HTTP clients in edge apps

**Files**:

- `apps/edge/src/aitbc_edge/clients/blockchain_rpc.py` — lines 14-15
- `apps/edge/src/aitbc_edge/clients/gpu_service.py` — lines 14-15

**Problem**: AsyncClient created in `__init__` but not closed.

**Fix** (same pattern for both files):

1. Add async context manager protocol:

   ```python
   async def __aenter__(self):
       return self

   async def __aexit__(self, exc_type, exc_val, exc_tb):
       if self._client:
           await self._client.aclose()
   ```

2. Add `__del__` with warning:

   ```python
   def __del__(self):
       if hasattr(self, '_client') and self._client is not None:
           import warnings
           warnings.warn(f"{self.__class__.__name__} was not properly closed")
   ```

**Verification**: Test edge service shutdown closes clients properly.

---

#### A13: Fix unclosed HTTP client in CLI utils

**File**: `cli/aitbc_cli/utils/http_client.py` — line 20

**Problem**: `httpx.Client` created in `__init__` but never closed.

**Fix**:

1. Add context manager protocol:

   ```python
   def __enter__(self):
       return self

   def __exit__(self, exc_type, exc_val, exc_tb):
       self.close()
   ```

2. Add `__del__` with warning:

   ```python
   def __del__(self):
       if hasattr(self, '_client') and self._client is not None:
           import warnings
           warnings.warn(f"{self.__class__.__name__} was not properly closed")
   ```

**Verification**: Run CLI commands, verify no connection warnings.

---

#### A14: Fix unclosed HTTP clients in bridge/trading (mechanical pattern)

**Files**:

- `aitbc/bridge/client.py` — lines 60-66
- `aitbc/trading/offer_client.py` — lines 60-63
- `aitbc/trading/subscription_client.py` — line 416

**Problem**: `_ensure_client()` creates `httpx.AsyncClient` without guaranteed cleanup.

**Fix** (same pattern for all three files):

1. Make `_ensure_client()` private by renaming to `_ensure_client_internal()`
2. Add public async context manager methods:

   ```python
   async def __aenter__(self):
       await self._ensure_client_internal()
       return self

   async def __aexit__(self, exc_type, exc_val, exc_tb):
       await self.close()
   ```

3. Add `__del__` with warning:

   ```python
   def __del__(self):
       if hasattr(self, '_client') and self._client is not None:
           import warnings
           warnings.warn(f"{self.__class__.__name__} was not properly closed")
   ```

4. Update docstring to document context manager requirement

**Verification**: Run unit tests for these modules.

---

## Agent B — Complex Tasks (GLM 5.2)

**Scope**: Complex tasks requiring deeper understanding of business logic, database semantics, async patterns, transaction handling, and security considerations. Financial correctness bugs, database migrations, and architectural refactoring.

**Working directory**: `/opt/aitbc/`

**Verification command**:

```bash
cd /opt/aitbc && ./venv/bin/python -m mypy --show-error-codes apps/exchange/ apps/coordinator-api/ apps/blockchain-node/src/aitbc_chain/ aitbc/network/ aitbc/database/ aitbc/bridge/ && ./venv/bin/python -m ruff check apps/exchange/ apps/coordinator-api/ apps/blockchain-node/ aitbc/network/ aitbc/database/ aitbc/bridge/ && ./venv/bin/python -m pytest tests/unit apps/exchange/tests/ -q -o addopts=""
```

### Tasks — Agent B — Complex Tasks (GLM 5.2)

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| B1 | Fix exchange order matching race condition | 🔴 P0 | `apps/exchange/exchange_api.py`, `apps/exchange/simple_exchange/handlers/exchange.py` | ✅ |
| B2 | Migrate exchange Float columns to Numeric | 🔴 P0 | `apps/exchange/models.py`, alembic migration, `apps/exchange/simple_exchange/db.py` | ✅ |
| B3 | Fix exchange database session leak | 🔴 P0 | `apps/exchange/database.py`, `apps/exchange/simple_exchange/handlers/exchange.py`, `marketplace.py` | ✅ |
| B4 | Fix exchange session token predictability | 🔴 P0 | `apps/exchange/exchange_api.py` | ✅ (exchange_api.py only — simple_exchange uses API-key auth, not session tokens) |
| B5 | Replace sync requests with httpx.AsyncClient in AsyncAITBCHTTPClient | 🟡 P1 | `aitbc/network/client.py` | ✅ |
| B6 | Replace sync httpx.Client with async in bridge/oracle.py | 🟡 P1 | `aitbc/bridge/oracle.py` | ✅ |
| B7 | Fix database connection leak in SQLiteDatabaseService | 🟡 P1 | `aitbc/database/service.py` | ✅ |
| B8 | Add error handling to fire-and-forget tasks in blockchain-node | 🟡 P1 | `apps/blockchain-node/src/aitbc_chain/` (18 files) | ✅ |
| B9 | Add error handling to fire-and-forget tasks in edge | 🟡 P1 | `apps/edge/src/aitbc_edge/main.py` | ✅ |
| B10 | Add error handling to fire-and-forget tasks in agent-coordinator | 🟡 P1 | `apps/agent-coordinator/src/app/` (4 files) | ✅ |
| B11 | Add error handling to fire-and-forget tasks in coordinator-api | 🟡 P1 | `apps/coordinator-api/src/app/` (13 files) | ✅ |
| B12 | Fix missing rollback in coordinator-api submit_job | 🟡 P1 | `apps/coordinator-api/src/app/contexts/infrastructure/routers/client.py` | ✅ |
| B13 | Add Pydantic validation + chain_id whitelist to bridge RPC | 🟡 P1 | `apps/blockchain-node/src/aitbc_chain/rpc/routers/bridge.py` | ✅ |
| B14 | Add N+1 query fix for GPU orders | 🟢 P2 | `apps/coordinator-api/src/app/contexts/marketplace/routers/marketplace_gpu.py` | ✅ |
| B15 | Fix mempool eviction policy bug | 🟢 P2 | `apps/blockchain-node/src/aitbc_chain/mempool.py` | ✅ |

### Agent B — Detailed Instructions

#### B1: Fix exchange order matching race condition

**File**: `apps/exchange/exchange_api.py` — lines 228-286

**Problem**: `try_match_order()` queries and updates orders without row locking. Concurrent requests can match the same orders twice, causing double-spending.

**Fix**:

1. Add `.with_for_update()` to matching order query to lock rows:

   ```python
   matching_orders = (
       db.query(Order)
       .filter(and_(Order.order_type == "SELL", Order.status == "OPEN", Order.price <= order.price))
       .order_by(Order.price)
       .with_for_update()
       .all()
   )
   ```

2. Wrap entire matching logic in try/except with rollback:

   ```python
   try:
       # ... matching logic ...
       db.commit()
   except Exception as e:
       db.rollback()
       logger.exception("Order matching failed")
       raise
   ```

3. Change `trade_hash` from timestamp to uuid4 to prevent collisions:

   ```python
   import uuid
   trade_hash = f"trade_{uuid.uuid4()}"
   ```

**Verification**: Write unit test that spawns two concurrent orders matching the same counterparty and verifies no double-match. Run with pytest-asyncio.

---

#### B2: Migrate exchange Float columns to Numeric

**Files**:

- `apps/exchange/models.py` — lines 45-49, 76-78, 103-106
- Create alembic migration script

**Problem**: Float arithmetic on balances causes accounting drift due to floating-point precision errors.

**Fix**:

1. Update model definitions in `models.py`:

   ```python
   from sqlalchemy import Numeric
   amount = Column(Numeric(18, 8), nullable=False)
   price = Column(Numeric(18, 8), nullable=False)
   total = Column(Numeric(18, 8), nullable=False)
   filled = Column(Numeric(18, 8), default=0.0)
   remaining = Column(Numeric(18, 8), nullable=False)
   # ... same for Trade and Balance models
   ```

2. Create alembic migration:

   ```bash
   cd apps/exchange
   alembic revision -autogenerate -m "migrate float to numeric"
   ```

3. Edit migration to use `ALTER TYPE` with `USING` clause to preserve data:

   ```python
   op.alter_column('orders', 'amount', type_=Numeric(18, 8), postgresql_using='amount::numeric(18,8)')
   # ... repeat for all columns
   ```

4. Update Python code to use `Decimal`:

   ```python
   from decimal import Decimal
   order.amount = Decimal("10.5")
   ```

**Verification**: Run migration, verify data preserved with SQL queries, run exchange tests.

---

#### B3: Fix exchange database session leak

**File**: `apps/exchange/database.py` — lines 49-55

**Problem**: `get_db_session()` returns session with `finally: pass`, never closing connections.

**Fix**:

1. Delete the `get_db_session()` function entirely
2. Search for all usages:

   ```bash
   grep -r "get_db_session" apps/exchange/
   ```

3. Update all endpoints to use the existing `get_db()` generator:

   ```python
   # Before
   db: Session = Depends(get_db_session)

   # After
   db: Session = Depends(get_db)
   ```

**Verification**: Run exchange tests, verify no connection warnings in logs.

---

#### B4: Fix exchange session token predictability

**File**: `apps/exchange/exchange_api.py` — lines 301-302

**Problem**: Tokens are `sha256(f"{user_id}:{timestamp}")` — guessable within seconds. Stored in in-memory dict (lost on restart, breaks multi-worker).

**Fix**:

1. Change token generation:

   ```python
   import secrets
   token = secrets.token_urlsafe(32)
   ```

2. Replace in-memory dict with Redis:

   ```python
   import redis
   import json

   redis_client = redis.from_url(settings.redis_url)
   session_data = {
       "user_id": user.id,
       "created_at": int(time.time()),
       "expires_at": int(time.time()) + 86400,
   }
   redis_client.setex(f"session:{token}", 86400, json.dumps(session_data))
   ```

3. Add config option for Redis URL with fallback to in-memory for dev:

   ```python
   class ExchangeSettings(BaseSettings):
       redis_url: str = Field(default="redis://localhost:6379/0")
       session_backend: str = Field(default="redis", description="redis or memory")
   ```

**Verification**: Test token generation is cryptographically random. Test Redis session storage. Test fallback to in-memory for dev.

---

#### B5: Replace sync requests with httpx.AsyncClient in AsyncAITBCHTTPClient

**File**: `aitbc/network/client.py` — lines 412-416, 474, 532, 585

**Problem**: `AsyncAITBCHTTPClient` wraps sync `requests` in `run_in_executor`, blocking thread pool threads and defeating async benefits.

**Fix**:

1. Replace `requests` import with `httpx`
2. Change all methods to async/await:

   ```python
   async def get(self, path: str, **kwargs) -> Response:
       async with httpx.AsyncClient() as client:
           response = await client.get(f"{self.base_url}{path}", **kwargs)
           return response

   async def post(self, path: str, **kwargs) -> Response:
       async with httpx.AsyncClient() as client:
           response = await client.post(f"{self.base_url}{path}", **kwargs)
           return response
   ```

3. Remove `run_in_executor` wrapper from all methods
4. Search for all call sites across the codebase:

   ```bash
   grep -r "AsyncAITBCHTTPClient" apps/ --include="*.py"
   ```

5. Update all call sites to await the methods

**Verification**: Ensure all call sites use await. Run unit tests. Verify no blocking calls in async context.

---

#### B6: Replace sync httpx.Client with async in bridge/oracle.py

**File**: `aitbc/bridge/oracle.py` — lines 293, 310

**Problem**: `ExternalOracleClient` uses synchronous `httpx.Client`, blocking the event loop if called from async code.

**Fix**: Converted `OracleClient` ABC, `InProcessVerifier`, `ExternalOracleClient`, and `OracleFallbackPolicy` to async. `verify_proof`, `check_finality`, `verify_with_fallback`, and `check_finality_with_fallback` are now `async def`. `_post_json` uses `httpx.AsyncClient`. The `is_healthy()` health check remains synchronous because it runs in a background thread via `OracleFallbackPolicy.start_health_check()`.

**Verification**: `pytest tests/unit/test_bridge_verification.py tests/unit/test_v074_deferred.py` — 77 passed.

---

#### B7: Fix database connection leak in SQLiteDatabaseService

**File**: `aitbc/database/service.py` — lines 60-69

**Problem**: `_get_connection()` creates connections and appends to list without auto-cleanup, causing connection leaks.

**Fix**:

1. Implement connection pooling using SQLAlchemy's built-in pooling:

   ```python
   from sqlalchemy.pool import StaticPool

   engine = create_engine(
       DATABASE_URL,
       connect_args={"check_same_thread": False},
       poolclass=StaticPool,
       pool_size=5,
       max_overflow=10,
   )
   ```

2. Add `__del__` to close all connections:

   ```python
   def __del__(self):
       self.close()
   ```

3. Add context manager protocol:

   ```python
   async def __aenter__(self):
       return self

   async def __aexit__(self, exc_type, exc_val, exc_tb):
       self.close()
   ```

**Verification**: Test that connections are closed on service shutdown. Monitor connection count.

---

#### B8-B11: Add error handling to fire-and-forget tasks

**Files**: 78+ bare `asyncio.create_task()` calls converted across 40+ files in:

- `apps/blockchain-node/src/aitbc_chain/` (18 files: app, chain_sync, combined_main, consensus/pbft, consensus/poa, contracts/upgrades, cross_chain/settlement_coordinator, gossip/broker, lease_tracker, network/*, p2p_network, subscription_client)
- `apps/agent-coordinator/src/app/` (4 files: protocols/communication, monitoring/alerting, workflow/orchestrator, routing/agent_discovery)
- `apps/coordinator-api/src/app/` (13 files: analytics, agent_coordination, blockchain, cross_chain, infrastructure, marketplace, security, multimodal, settlement, trading)
- `apps/trading/src/trading_service/` (4 files: main, gossip_client, offer_subscription_service, offer_notification_service)
- `apps/pool-hub/src/poolhub/services/` (2 files: sla_collector, billing_integration)
- `apps/agent-management/src/app/services/` (5 files: agent_service, agent_orchestrator, agent_performance_service, agent_service_marketplace, agent_communication)
- `apps/blockchain-event-bridge/src/blockchain_event_bridge/bridge.py`
- `apps/wallet/src/app/main.py`
- `aitbc/` (5 files: alerting, trading/subscription_client, network/subscription_manager, queues/scheduler, queues/worker)

**Problem**: `asyncio.create_task()` calls have no exception handling. Errors are silently lost, making debugging difficult.

**Fix**: Replaced all bare `asyncio.create_task(coro)` with `create_task_with_logging(coro, name="...")` from `aitbc.async_tasks`. The helper attaches a done-callback that logs exceptions with full traceback. Only immediately-awaited patterns in `aitbc/queues/decorators.py` and `aitbc/async_helpers/async_helpers.py` were intentionally left as-is.

**Verification**: `ruff check .` passes. `pytest tests/unit -q` — 870 passed, 0 failed.

---

#### B12: Fix missing rollback in coordinator-api submit_job

**File**: `apps/coordinator-api/src/app/contexts/infrastructure/routers/client.py` — lines 36-52

**Problem**: Payment creation failure doesn't rollback job insert, leaving orphaned jobs in database.

**Fix**:

```python
try:
    job = create_job(...)
    db.add(job)
    db.commit()

    payment = create_payment(...)
    db.add(payment)
    db.commit()
except Exception as e:
    db.rollback()
    logger.exception("Payment creation failed, rolling back job")
    payment.status = "skipped"
    db.add(payment)
    db.commit()
    raise
```

**Verification**: Test that payment failure rolls back job. Verify no orphaned jobs in database.

---

#### B13: Add Pydantic validation to bridge RPC endpoints

**File**: `apps/blockchain-node/src/aitbc_chain/rpc/routers/bridge.py`

**Problem**: Endpoints accept raw `dict` request bodies without validation. `chain_id` has no whitelist validation.

**Fix**:

1. Pydantic models were added in the initial B13 commit for all 7 request bodies (lock, confirm, unlock, batch, validator register, block header).
2. Added `_validate_chain_id()` helper to the bridge router that calls the existing `validate_chain_id()` from `rpc/utils.py` (checks against `settings.supported_chains`).
3. Applied validation to all 7 endpoints that accept a `chain_id`:
   - POST /bridge/lock (validates `target_chain` + optional `source_chain`)
   - GET /bridge/pending (validates optional `chain_id` query param)
   - GET /bridge/balance/{chain_id}
   - POST /bridge/validators/register (validates `chain_id` in body)
   - GET /bridge/validators/{chain_id}
   - POST /bridge/block-headers (validates `chain_id` in body)
   - GET /bridge/block-headers/{chain_id}/{height}
4. Updated 5 test files with `autouse` fixtures patching `supported_chains` to allow test chain IDs.

**Verification**: `pytest tests/test_bridge_suite.py tests/test_v070_bridge_basics.py tests/test_v071_bridge_security.py tests/test_v072_bridge_verification.py tests/test_v0516_regression.py` — 131 passed, 4 skipped.

---

#### B14: Add N+1 query fix for GPU orders

**File**: `apps/coordinator-api/src/app/contexts/marketplace/routers/marketplace_gpu.py` — line 609

**Problem**: GPU orders list fetches each `GPURegistry` individually in a loop per booking, causing N+1 queries.

**Fix**:

1. Use SQLAlchemy's `selectinload` to fetch related GPUs in a single query:

   ```python
   from sqlalchemy.orm import selectinload

   bookings = (
       db.query(GPUBooking)
       .options(selectinload(GPUBooking.gpu))
       .filter(...)
       .all()
   )
   ```

2. Remove the individual `session.get(GPURegistry, b.gpu_id)` calls in the loop

**Verification**: Run query with logging enabled to verify single query. Measure performance improvement.

---

#### B15: Fix mempool eviction policy bug

**File**: `apps/blockchain-node/src/aitbc_chain/mempool.py` — lines 160-167

**Problem**: Eviction uses `-received_at` tie-breaker, evicting newest low-fee transactions instead of oldest.

**Fix**:

1. Change eviction key from `(fee, -received_at)` to `(fee, received_at)`:

   ```python
   # Before
   eviction_key = (tx.fee, -tx.received_at)

   # After
   eviction_key = (tx.fee, tx.received_at)
   ```

2. This ensures oldest lowest-fee transactions are evicted first

**Verification**: Write unit test to verify eviction order. Test with multiple transactions having same fee.

---

## Coordination Notes

No coordination required between Agent A and Agent B in this release. All tasks are independent:

- Agent A's mechanical fixes are isolated to specific files
- Agent B's complex tasks are in different domains
- No shared file conflicts

Both agents can work in parallel.

---

## Verification Checklist

After all tasks complete, run this verification checklist:

- [ ] All unit tests pass (1887 tests)
- [ ] `ruff check .` clean
- [ ] `mypy aitbc/ apps/` clean
- [ ] Exchange schema migration runs without errors
- [ ] Exchange order matching passes concurrent test
- [ ] CLI commands run without AttributeError
- [ ] No "Too many open files" errors under load
- [ ] Fire-and-forget task exceptions are logged
- [ ] Services fail-fast without hardcoded secrets
- [ ] Bridge RPC validation rejects invalid input
- [ ] Database queries use indexes (verify with EXPLAIN)
- [ ] N+1 query fix verified (single query for GPU orders)
- [ ] Mempool eviction order is correct (oldest first)

---

## Post-Release Tasks

After v0.10.3 is complete, the following items are suggested for future releases (see [suggestions.md](suggestions.md)):

1. **Performance optimizations** — Incremental state root computation, parallel transaction validation by default
2. **Observability** — Add comprehensive metrics for critical operations
3. **Documentation** — Complete deployment guides and runbooks
4. **Security audit** — External security review of bridge and consensus code

---

## Backport: simple_exchange B1/B2/B3 (2026-07-05)

**Problem discovered during scenario drafting**: The B1–B4 fixes were applied to `apps/exchange/exchange_api.py` (FastAPI + SQLAlchemy), but the running systemd service (`aitbc-exchange.service`) starts `apps/exchange/simple_exchange/server.py` (stdlib `http.server` + raw `sqlite3`). The fixes protected dead code — the live service still had float-for-money columns, no transaction atomicity for order matching, and unguarded DB connections.

**Backport applied**:

| Fix | What changed | Files |
|-----|-------------|-------|
| **B2 (float→Decimal)** | Schema columns changed from `REAL` to `TEXT` (Decimal-as-string). All monetary arithmetic uses `Decimal`. Automatic migration of existing REAL columns via table rebuild in `init_db()`. | `simple_exchange/db.py`, `simple_exchange/handlers/exchange.py`, `simple_exchange/handlers/marketplace.py` |
| **B1 (race condition)** | Order insert + matching now run in a single `BEGIN IMMEDIATE` transaction, acquiring the SQLite write lock before reading open orders. Prevents concurrent double-matching. | `simple_exchange/handlers/exchange.py` (`handle_place_order`, `_match_orders_in_txn`) |
| **B3 (connection leak)** | All `sqlite3.connect()` calls wrapped in `try/finally` to guarantee cleanup on exceptions. | `simple_exchange/handlers/exchange.py`, `simple_exchange/handlers/marketplace.py` |
| **B4 (token predictability)** | N/A — `simple_exchange` uses static API-key auth (`X-Api-Key` header), not session tokens. No change needed. | — |

**Tests**: 14 new tests in `apps/exchange/tests/test_simple_exchange_b1_b2_b3.py`. All 41 exchange tests pass (27 existing + 14 new).

**Scenarios**: Scenario 33 ([Exchange Financial Correctness](../../scenarios/33_exchange_financial_correctness.md)) updated to reflect the backport.
