# v0.10.4 — Agent Task Assignment

**Last Updated**: 2026-07-05
**Version**: 1.0 — Initial plan from post-v0.10.3 audit findings

**Release Theme**: Performance, Correctness & Cleanup — Migrate remaining float-based money handling to Decimal, eliminate N+1 queries, add missing DB indexes, fix race conditions in async services, remove ~1,000 lines of dead code, and consolidate duplicate infrastructure.

**Goal**: Production readiness from a performance and maintainability standpoint. Extends v0.10.3's financial correctness fix (exchange Decimal migration) to the rest of the stack (pool-hub billing, trading pricing/bid engines). Eliminates performance bottlenecks (N+1 queries, per-request HTTP clients, missing indexes). Removes ~1,000 lines of dead code and consolidates 3 HTTP client implementations, 2 JWT implementations, 5 retry implementations, and copy-pasted config validators.

> **Scope**: 24 tasks across 8 categories. All P0 (Decimal migration), P1 (performance + concurrency), P2 (security/correctness), and P3 (cleanup/consolidation) findings from the post-v0.10.3 audit.

> **Prerequisites**: [v0.10.3](../v0.10.3/change.log) (complete — critical bugs, race conditions, and resource leaks fixed).

> **Risk**: Medium-High. The Decimal migration requires a DB schema migration and touches ~1,500 lines. Performance changes require benchmarking. Mitigated by: (1) comprehensive test suite, (2) live testing on shop node, (3) rollback plan for schema migrations, (4) incremental task completion with verification at each step.

---

## Task Split Overview

| Agent | Capability | Tasks | Focus |
|-------|------------|-------|-------|
| **Agent A** | SWE 1.6 (fast mechanical tasks) | 10 items | Dead code deletion, port sweep, HTTP client consolidation, JWT/retry/config-validator extraction, datetime sweep |
| **Agent B** | GLM 5.2 (complex tasks) | 14 items | Decimal migration + DB schema migration, N+1 query elimination, asyncio.Lock race condition fixes, SQL whitelisting, cache TTL eviction, blocking I/O refactoring |

**Conflict boundary**: Agent A owns mechanical cleanup and consolidation (deletion, extraction, port updates). Agent B owns complex business logic, database semantics, async concurrency, and security patterns. No coordination required — tasks are independent.

**Rationale**: SWE 1.6 excels at fast, mechanical code changes (deletion, extraction, refactoring, port updates). GLM 5.2 handles complex tasks requiring deeper understanding of business logic, database migrations, async concurrency patterns, and security considerations.

---

## Agent A — Mechanical Cleanup & Consolidation (SWE 1.6)

**Scope**: Dead code deletion, infrastructure consolidation, mechanical sweeps. Simple, mechanical code changes that don't require deep business logic understanding.

**Working directory**: `/opt/aitbc/`

**Verification command**:
```bash
cd /opt/aitbc && ./venv/bin/python -m ruff check . && ./venv/bin/python -m pytest tests/unit -q -o addopts=""
```

### Tasks

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| A1 | Delete dead `cli/advanced_wallet.py` | 🟢 P3 | `cli/aitbc_cli/commands/advanced_wallet.py` | ⬜ |
| A2 | Delete dead `aitbc/database_service.py` + test | 🟢 P3 | `aitbc/database_service.py`, `tests/test_database_service.py` | ⬜ |
| A3 | Delete orphaned `test_coordinator_api_v1.py` + dead `payments_service.py` | 🟢 P3 | `tests/test_coordinator_api_v1.py`, `apps/coordinator-api/src/app/contexts/payments/services/payments_service.py` | ⬜ |
| A4 | Consolidate HTTP client implementations | 🟡 P2 | `aitbc/network/client.py`, `aitbc/http_client/client.py`, `cli/aitbc_cli/utils/http_client.py` | ⬜ |
| A5 | Extract shared JWT module to `aitbc/auth/` | 🟡 P2 | `aitbc/auth/` (new), `apps/coordinator-api/src/app/auth.py`, `apps/agent-coordinator/src/app/auth.py` | ⬜ |
| A6 | Consolidate retry implementations | 🟢 P3 | `aitbc/network/retry.py`, `aitbc/network/circuit_breaker.py` | ⬜ |
| A7 | Extract shared config validators to `aitbc/config/validators.py` | 🟡 P2 | `aitbc/config/validators.py` (new), `apps/coordinator-api/src/app/config.py`, `apps/agent-coordinator/src/app/config.py`, `apps/edge/src/aitbc_edge/config.py` | ⬜ |
| A8 | Sweep stale port defaults (8010/8011) | 🟢 P3 | `aitbc/agent_bridge/src/integration_layer.py`, `apps/pool-hub/.../settings.py`, `apps/wallet/src/app/settings.py` | ⬜ |
| A9 | `datetime.now(UTC)` sweep (~40 sites) | 🟡 P2 | Multiple — see detailed instructions | ⬜ |
| A10 | Remove module-level Torch/PyCUDA imports | 🟡 P2 | `apps/coordinator-api/src/app/contexts/...` | ⬜ |

### Agent A — Detailed Instructions

#### A1: Delete dead `cli/advanced_wallet.py`

**Files**: `cli/aitbc_cli/commands/advanced_wallet.py` (314 lines)

**Verification**: Already confirmed 0 imports across the codebase:
```bash
grep -rn "advanced_wallet" --include="*.py" --include="*.toml" . | grep -v "advanced_wallet.py:"
# Expected: no output
```

**Fix**: Delete the file. Check `cli/aitbc_cli/commands/__init__.py` for any registration and remove if present.

#### A2: Delete dead `aitbc/database_service.py` + test

**Files**: `aitbc/database_service.py`, `tests/test_database_service.py`

**Verification**: Only `tests/test_database_service.py` imports it (its own test):
```bash
grep -rln "from aitbc.database_service\|from aitbc import database_service\|aitbc\.database_service" --include="*.py" .
# Expected: only tests/test_database_service.py
```

**Fix**: Delete both files.

#### A3: Delete orphaned test + dead payments service

**Files**:
- `tests/test_coordinator_api_v1.py` (330 lines, orphaned — no corresponding module)
- `apps/coordinator-api/src/app/contexts/payments/services/payments_service.py` (in-memory `PaymentsService`, 0 imports)

**Verification for payments_service.py**:
```bash
grep -rn "PaymentsService\|from.*payments_service\|import payments_service" --include="*.py" . | grep -v "payments_service.py:"
# Expected: no output (real service is PaymentService in payments.py, which IS DB-backed)
```

**Fix**: Delete both files. Verify `payments/services/__init__.py` does not export `PaymentsService`.

#### A4: Consolidate HTTP client implementations

**Files**:
- `aitbc/network/client.py` (608 lines, ~0 app usage — the feature-rich shared client that nobody uses)
- `aitbc/http_client/client.py` (request-ID aware)
- `cli/aitbc_cli/utils/http_client.py` (48+ users)

**Problem**: 3 HTTP client implementations exist. The CLI one has the most users. The `aitbc/network/client.py` one is nearly unused despite being the most feature-rich.

**Fix**:
1. Audit usage of each:
   ```bash
   grep -rln "from aitbc.network.client\|from aitbc.network import.*Client" --include="*.py" .
   grep -rln "from aitbc.http_client\|from aitbc.http_client.client" --include="*.py" .
   grep -rln "from aitbc_cli.utils.http_client\|from .http_client\|from ..utils.http_client" --include="*.py" .
   ```
2. Merge request-ID support from `aitbc/http_client/client.py` into `aitbc/network/` as the canonical client.
3. Update all `aitbc/http_client/` imports to point to `aitbc/network/`.
4. Update CLI `http_client.py` to re-export from `aitbc/network/` (or update all 48+ call sites — judge based on import count).
5. Delete `aitbc/network/client.py` if truly unused, or mark it as the canonical location and delete the others.

**Note**: This task has the highest coordination risk. If any app imports conflict, defer to keeping `aitbc/network/` as canonical and making others thin re-export shims (then delete shims in v0.10.5).

#### A5: Extract shared JWT module to `aitbc/auth/`

**Files**:
- `aitbc/auth/` (new module)
- `apps/coordinator-api/src/app/auth.py` (basic JWT)
- `apps/agent-coordinator/src/app/auth.py` (JWT with refresh/bcrypt)

**Problem**: 2 JWT implementations with overlapping but inconsistent features.

**Fix**:
1. Read both implementations to identify the union of features.
2. Create `aitbc/auth/jwt.py` with the canonical implementation (token creation, verification, refresh, bcrypt password hashing).
3. Create `aitbc/auth/__init__.py` with public exports.
4. Update both apps to import from `aitbc/auth/`.
5. Delete the app-local implementations (or make them thin re-exports for backward compat).

#### A6: Consolidate retry implementations

**Files**: `aitbc/network/retry.py`, `aitbc/network/circuit_breaker.py`

**Problem**: 5 retry implementations and 2 circuit breakers exist across the codebase.

**Fix**:
1. Find all retry/circuit breaker implementations:
   ```bash
   grep -rn "def.*retry\|class.*Retry\|class.*CircuitBreaker\|@retry" --include="*.py" . | grep -v test
   ```
2. Standardize on `aitbc/network/retry.py` and `aitbc/network/circuit_breaker.py`.
3. Update all call sites to use the canonical implementations.
4. Delete duplicate implementations.

**Note**: Per AGENTS.md coordination protocol, `aitbc/network/circuit_breaker.py` is a shared file. Agent A goes first for `aitbc/` shared files. Add `# WIP: Agent A` comment while editing.

#### A7: Extract shared config validators to `aitbc/config/validators.py`

**Files**:
- `aitbc/config/validators.py` (new)
- `apps/coordinator-api/src/app/config.py`
- `apps/agent-coordinator/src/app/config.py`
- `apps/edge/src/aitbc_edge/config.py`

**Problem**: Copy-pasted config validators (secret validation, CORS validation, bool parsing) across 3+ apps. The v0.10.3 A5 gap (missing `jwt_secret` validator in coordinator-api) existed because of this duplication.

**Fix**:
1. Identify shared validation patterns:
   ```bash
   grep -rn "field_validator\|@validator" --include="*.py" apps/coordinator-api/src/app/config.py apps/agent-coordinator/src/app/config.py apps/edge/src/aitbc_edge/config.py
   ```
2. Create `aitbc/config/validators.py` with reusable validator functions:
   - `validate_secret(field_name, min_length=32)` — rejects default/short secrets in production
   - `validate_cors_origins()` — validates CORS origin list
   - `parse_bool_env()` — parses boolean env vars
3. Create `aitbc/config/__init__.py` with public exports.
4. Update all apps to use the shared validators.
5. Remove duplicate validators from app configs.

#### A8: Sweep stale port defaults (8010/8011)

**Files**:
- `aitbc/agent_bridge/src/integration_layer.py:21`
- `apps/pool-hub/.../settings.py`
- `apps/wallet/src/app/settings.py`
- Any CORS allowlists referencing 8010/8011

**Problem**: v0.10.3 established a port registry, but some references to old ports (8010/8011) remain.

**Fix**:
1. Find all stale port references:
   ```bash
   grep -rn "8010\|8011" --include="*.py" . | grep -v test | grep -v ".pyc"
   ```
2. Update each to the correct port from the registry in `AGENTS.md`.
3. Verify no service actually runs on 8010/8011.

#### A9: `datetime.now(UTC)` sweep (~40 sites)

**Files**: Multiple — surveillance, analytics, cache.py, wallet chain manager, marketplace RPC, and others.

**Problem**: ~40 sites use naive `datetime.now()` or deprecated `datetime.utcnow()` in expiry/alert logic, which can cause timezone bugs.

**Fix**:
1. Find all naive/deprecated datetime calls:
   ```bash
   grep -rn "datetime\.now()\|datetime\.utcnow()\|\.utcnow()" --include="*.py" . | grep -v test | grep -v ".pyc"
   ```
2. Replace each with `datetime.now(UTC)` (import `from datetime import UTC`).
3. For `datetime.utcnow()`, replace with `datetime.now(UTC)`.
4. Verify no timezone-naive comparisons remain in expiry logic.

#### A10: Remove module-level Torch/PyCUDA imports

**Files**: `apps/coordinator-api/src/app/contexts/...` (find exact locations)

**Problem**: Torch/PyCUDA imported at module level adds 1-2s startup time and breaks non-GPU deployments.

**Fix**:
1. Find module-level imports:
   ```bash
   grep -rn "^import torch\|^import pycuda\|^from torch\|^from pycuda" --include="*.py" apps/coordinator-api/
   ```
2. Move imports inside functions that need them (lazy import pattern).
3. Verify startup time improvement.

---

## Agent B — Complex Fixes (GLM 5.2)

**Scope**: Decimal migration, N+1 query elimination, asyncio.Lock race condition fixes, SQL whitelisting, cache TTL eviction, blocking I/O refactoring. Complex tasks requiring deep understanding of business logic, database semantics, and async patterns.

**Working directory**: `/opt/aitbc/`

**Verification command**:
```bash
cd /opt/aitbc && ./venv/bin/python -m mypy --show-error-codes aitbc/ && ./venv/bin/python -m pytest tests/unit -q -o addopts=""
cd /opt/aitbc/apps/coordinator-api && PYTHONPATH=src ../../venv/bin/python -m pytest tests -q -o addopts=""
```

### Tasks

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| B1 | Migrate `UsageRecord` model to Numeric columns + Alembic migration | 🔴 P0 | `apps/coordinator-api/src/app/models/multitenant.py`, `apps/coordinator-api/alembic/versions/` | ⬜ |
| B2 | Migrate pool-hub `billing_integration.py` to Decimal end-to-end | 🔴 P0 | `apps/pool-hub/src/poolhub/services/billing_integration.py` | ⬜ |
| B3 | Migrate trading `dynamic_pricing.py` to Decimal | 🔴 P0 | `apps/coordinator-api/src/app/contexts/trading/services/trading_marketplace/dynamic_pricing.py` | ⬜ |
| B4 | Migrate trading `bid_strategy.py` to Decimal | 🔴 P0 | `apps/coordinator-api/src/app/contexts/trading/services/trading_marketplace/bid_strategy.py` | ⬜ |
| B5 | Fix pool-hub SLA collector N+1 (3N+1 → O(1)) | 🟠 P1 | `apps/pool-hub/src/poolhub/services/sla_collector.py` | ⬜ |
| B6 | Fix pool-hub billing sync N+1 | 🟠 P1 | `apps/pool-hub/src/poolhub/services/billing_integration.py` | ⬜ |
| B7 | Add missing DB indexes (pool-hub + marketplace) | 🟠 P1 | `apps/pool-hub/src/poolhub/models.py`, `apps/marketplace/.../marketplace.py`, Alembic migration | ⬜ |
| B8 | Replace per-request `httpx.AsyncClient()` with shared instances (~10 sites) | 🟠 P1 | `apps/wallet/src/app/main.py`, `apps/trading/...`, `apps/edge/...`, `apps/coordinator-api/.../dao_governance_service.py`, `apps/marketplace/...` | ⬜ |
| B9 | Fix blocking `requests.post()` in async alerting | 🟠 P1 | `apps/agent-coordinator/src/app/monitoring/alerting.py` | ⬜ |
| B10 | Add `asyncio.Lock` to `cross_chain/reputation.py` race conditions | 🟠 P1 | `apps/coordinator-api/src/app/contexts/trading/services/cross_chain/reputation.py` | ⬜ |
| B11 | Add `asyncio.Lock` to `load_balancer.py` race conditions | 🟠 P1 | `apps/agent-coordinator/src/app/.../load_balancer.py` | ⬜ |
| B12 | Add `asyncio.Lock` to `distributed_framework.py` race conditions | 🟠 P1 | `apps/coordinator-api/src/app/contexts/infrastructure/services/distributed_framework.py` | ⬜ |
| B13 | Add `asyncio.Lock` to `dynamic_pricing.py` cache race conditions | 🟠 P1 | `apps/coordinator-api/src/app/contexts/trading/services/trading_marketplace/dynamic_pricing.py` | ⬜ |
| B14 | SQL identifier whitelisting (3 sites) | 🟡 P2 | `apps/exchange/simple_exchange/db.py`, `apps/blockchain-node/.../database.py`, `apps/wallet/.../multichain_ledger.py` | ⬜ |

### Agent B — Detailed Instructions

#### B1: Migrate `UsageRecord` model to Numeric columns + Alembic migration

**Files**:
- `apps/coordinator-api/src/app/models/multitenant.py` (lines 148-155)
- `apps/coordinator-api/alembic/versions/` (new migration)

**Problem**: `UsageRecord.quantity/unit_price/total_cost` are `Float` columns, causing accounting drift.

**Fix**:
1. Change column types in the model:
   ```python
   # Before
   quantity: float = Field(nullable=False)
   unit_price: float = Field(nullable=False)
   total_cost: float = Field(nullable=False)
   # After
   quantity: Decimal = Field(max_digits=18, decimal_places=8, nullable=False)
   unit_price: Decimal = Field(max_digits=18, decimal_places=8, nullable=False)
   total_cost: Decimal = Field(max_digits=18, decimal_places=8, nullable=False)
   ```
2. Use `sqlalchemy.Numeric(18, 8)` (SQLModel maps `Decimal` to `Numeric` automatically).
3. Create Alembic migration:
   ```bash
   cd apps/coordinator-api && ../../venv/bin/python -m alembic revision --autogenerate -m "migrate_usage_records_to_numeric"
   ```
4. Edit migration to use `if_not_exists=True` and include a downgrade path.
5. Test migration on a copy of the production DB.

**Note**: Per AGENTS.md, `create_all` only adds indexes to fresh DBs. For existing DBs, the Alembic migration is required.

#### B2: Migrate pool-hub `billing_integration.py` to Decimal end-to-end

**Files**: `apps/pool-hub/src/poolhub/services/billing_integration.py`

**Problem**: `record_usage()` converts `Decimal` to `float` for the HTTP payload (lines 64-66):
```python
"quantity": float(quantity),
"unit_price": float(unit_price),
"total_amount": float(total_cost),
```

**Fix**:
1. Remove `float()` conversions — serialize `Decimal` as string for JSON transport.
2. Update `_collect_miner_usage()` return type from `dict[str, float]` to `dict[str, Decimal]`.
3. Update `compute_hours` calculation to use `Decimal` throughout.
4. Verify the coordinator-api billing endpoint accepts string-encoded Decimals (update endpoint if needed).
5. Test with the billing test suite.

**Depends on**: B1 (the receiving model must accept Decimal first).

#### B3: Migrate trading `dynamic_pricing.py` to Decimal

**Files**: `apps/coordinator-api/src/app/contexts/trading/services/trading_marketplace/dynamic_pricing.py` (969 lines)

**Problem**: All pricing data structures use `float` — `base_price`, multipliers, confidence scores, risk adjustments (lines 66-119).

**Fix**:
1. Change all `float` type annotations to `Decimal` in dataclasses (`PricingFactors`, `PricingResult`, `MarketConditions`, etc.).
2. Update all arithmetic to use `Decimal` — note that `Decimal` does not support `**` operator for non-integer exponents; use `.sqrt()` or explicit power functions.
3. Update default values from `1.0` to `Decimal("1.0")`, `0.5` to `Decimal("0.5")`, etc.
4. Update JSON serialization to convert `Decimal` to `str` for API responses.
5. Test with the trading test suite.

**Note**: This is the largest single task (~969 lines). Consider doing it in passes: (1) data structures, (2) arithmetic, (3) serialization, (4) tests.

#### B4: Migrate trading `bid_strategy.py` to Decimal

**Files**: `apps/coordinator-api/src/app/contexts/trading/services/trading_marketplace/bid_strategy.py` (560 lines)

**Problem**: All bid computation uses `float` — `base_price`, urgency/market/competition multipliers, `bid_price` (lines 51-96).

**Fix**: Same pattern as B3. Change type annotations, update arithmetic, update defaults, update serialization.

**Depends on**: B3 (shares the `MarketConditions` data structure).

#### B5: Fix pool-hub SLA collector N+1 (3N+1 → O(1))

**Files**: `apps/pool-hub/src/poolhub/services/sla_collector.py` (lines 146-177)

**Problem**: 3 queries per miner per collection cycle (3N+1 total).

**Fix**:
1. Read the current implementation to understand the 3 per-miner queries.
2. Replace with batched queries using JOINs or subqueries.
3. Target: O(1) round trips regardless of miner count.
4. Test with the SLA test suite.

#### B6: Fix pool-hub billing sync N+1

**Files**: `apps/pool-hub/src/poolhub/services/billing_integration.py` (lines 109-137)

**Problem**: `sync_all_miners_usage()` executes 1 query per miner in a loop.

**Fix**:
1. Replace the per-miner loop with a single batched query that aggregates usage across all miners.
2. Group results by `miner_id` in Python.
3. Test with the billing test suite.

#### B7: Add missing DB indexes (pool-hub + marketplace)

**Files**:
- `apps/pool-hub/src/poolhub/models.py` — `MatchResult.miner_id`, `MatchResult.created_at`, `Feedback.miner_id`, `SLAMetric.miner_id`, `SLAViolation.created_at`
- `apps/marketplace/.../marketplace.py` — `provider_address`, `status`, `region`
- Alembic migration for existing DBs

**Fix**:
1. Add `index=True` to each Field definition:
   ```python
   miner_id: str = Field(index=True, ...)
   created_at: datetime = Field(index=True, ...)
   ```
2. For composite indexes, add `__table_args__` with `sqlalchemy.Index(...)`.
3. Create Alembic migration with `if_not_exists=True`:
   ```bash
   cd apps/coordinator-api && ../../venv/bin/python -m alembic revision -m "add_poolhub_marketplace_indexes"
   ```
4. Test query performance before/after.

#### B8: Replace per-request `httpx.AsyncClient()` with shared instances

**Files**: ~10 sites:
- `apps/wallet/src/app/main.py`
- `apps/trading/src/.../main.py`
- `apps/trading/src/.../clients/blockchain.py` (3×)
- `apps/edge/src/aitbc_edge/...` (heartbeat loop)
- `apps/coordinator-api/src/app/contexts/governance/services/dao_governance_service.py`
- `apps/marketplace/src/.../escrow.py`

**Problem**: Each site creates a new `httpx.AsyncClient()` per request, paying TCP+TLS handshake overhead.

**Fix**:
1. Find all per-request client creation:
   ```bash
   grep -rn "httpx\.AsyncClient()" --include="*.py" apps/ | grep -v test
   ```
2. For each service, create a shared client in the service's lifespan/startup and close it on shutdown.
3. Use the `SharedHttpClient` pattern from v0.10.3 (or the consolidated client from A4 if complete).
4. Test that clients are properly closed on shutdown.

#### B9: Fix blocking `requests.post()` in async alerting

**Files**: `apps/agent-coordinator/src/app/monitoring/alerting.py` (lines 314, 325)

**Problem**: Slack/webhook alert delivery uses sync `requests.post()`, blocking the event loop.

**Fix**:
1. Replace `requests.post()` with `httpx.AsyncClient.post()`.
2. Use a shared `httpx.AsyncClient` managed by the service lifespan.
3. Add proper error handling and timeouts.
4. Test alert delivery.

#### B10: Add `asyncio.Lock` to `cross_chain/reputation.py` race conditions

**Files**: `apps/coordinator-api/src/app/contexts/trading/services/cross_chain/reputation.py`

**Problem**: Check-then-act patterns on reputation/stakes dicts across `await` boundaries (~13 sites).

**Fix**:
1. Add `self._lock = asyncio.Lock()` to the service `__init__`.
2. Wrap all check-then-act sequences in `async with self._lock:`.
3. Identify the 13 sites by searching for `await` between dict reads and writes:
   ```bash
   grep -n "await\|self\._reputation\|self\._stakes" apps/coordinator-api/src/app/contexts/trading/services/cross_chain/reputation.py
   ```
4. Test with concurrent access.

#### B11: Add `asyncio.Lock` to `load_balancer.py` race conditions

**Files**: `apps/agent-coordinator/src/app/.../load_balancer.py`

**Problem**: Task assignment metrics mutated across `await` boundaries.

**Fix**: Same pattern as B10.

#### B12: Add `asyncio.Lock` to `distributed_framework.py` race conditions

**Files**: `apps/coordinator-api/src/app/contexts/infrastructure/services/distributed_framework.py`

**Problem**: Worker/task registries mutated across `await` boundaries.

**Fix**: Same pattern as B10.

#### B13: Add `asyncio.Lock` to `dynamic_pricing.py` cache race conditions

**Files**: `apps/coordinator-api/src/app/contexts/trading/services/trading_marketplace/dynamic_pricing.py`

**Problem**: Pricing history/strategy caches mutated across `await` boundaries.

**Fix**: Same pattern as B10. **Note**: This file is also modified by B3 (Decimal migration). Do B13 after B3 to avoid merge conflicts, or coordinate with the same agent doing B3.

#### B14: SQL identifier whitelisting (3 sites)

**Files**:
- `apps/exchange/simple_exchange/db.py` (lines 97-140 — table names in migration helper)
- `apps/blockchain-node/src/aitbc_chain/database.py` (lines 97, 241 — PRAGMA key/ALTER TABLE)
- `apps/wallet/src/app/multichain_ledger.py` (line 308 — `chain_id` in table name)

**Problem**: F-string interpolation of identifiers in `execute()`. Low exploitability (internal values) but fragile and a security smell.

**Fix**:
1. For each site, replace f-string interpolation with identifier whitelisting:
   ```python
   ALLOWED_TABLES = {"table_a", "table_b", ...}
   if table_name not in ALLOWED_TABLES:
       raise ValueError(f"Invalid table name: {table_name}")
   # Use sqlalchemy.text() with bound parameters for values,
   # and validated identifiers for table/column names.
   ```
2. For `chain_id` in wallet, validate against a regex or allowed chain list before interpolation.
3. Test that valid identifiers still work and invalid ones are rejected.

---

## Coordination

### Shared Files

Per the AGENTS.md coordination protocol, the following shared files may be touched by both agents:

| File | Agent A | Agent B | Sequencing |
|------|---------|---------|------------|
| `aitbc/network/circuit_breaker.py` | A6 (consolidation) | — | Agent A first |
| `aitbc/network/client.py` | A4 (consolidation) | B8 (uses shared client) | Agent A first, then B8 |
| `apps/coordinator-api/src/app/contexts/trading/services/trading_marketplace/dynamic_pricing.py` | — | B3 (Decimal) + B13 (Lock) | Agent B does both sequentially |

### Dependencies

- B2 depends on B1 (model must accept Decimal before sender sends Decimal)
- B4 depends on B3 (shares `MarketConditions` data structure)
- B8 depends on A4 (uses consolidated HTTP client) — or use existing `SharedHttpClient` if A4 not complete
- B13 should be done after B3 (same file)

### Verification Checkpoints

1. **After B1+B2**: Run billing tests — verify Decimal precision end-to-end
2. **After B3+B4**: Run trading tests — verify pricing/bid Decimal precision
3. **After B5+B6+B7**: Benchmark pool-hub queries — verify N+1 eliminated
4. **After B10-B13**: Run concurrent access tests — verify no race conditions
5. **After A1-A3**: Verify no imports break — `grep` for any remaining references
6. **After A4-A7**: Run full test suite — verify consolidation didn't break anything
7. **Final**: Live testing on shop node for all 24 tasks

---

## Post-Release

After v0.10.4 is complete:
1. Update `docs/releases/v0.10.4/change.log` with actual completion status
2. Update root `AGENTS.md` with v0.10.4 in the release sequence
3. Update `docs/releases/STATUS.md` with v0.10.4 summary
4. Begin v1.0.0 planning (production readiness)
