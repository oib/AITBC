# v0.5.11 — Agent Task Assignment

**Release Theme**: Type safety hardening — systematic MyPy error elimination across the `aitbc/` shared core library, duplicate route audit, and systemd symlink repair.

**Goal**: Achieve 0 MyPy errors across all non-excluded files in `aitbc/`, fix all Ruff lint issues, migrate deprecated `TypeAlias` syntax, remove duplicate route registrations in coordinator-api, and repair the broken `aitbc-recovery` systemd symlink.

---

## Task Split Overview

| Agent | Domain | Tasks | Files Touched |
|-------|--------|-------|---------------|
| **Agent A** | Type safety & shared core (`aitbc/`) | 14 items | 20+ files in `aitbc/` |
| **Agent B** | Bug fixes, infrastructure & apps | 13 items | 10+ files in `apps/`, `cli/`, `aitbc/constants.py`, systemd |

**Conflict boundary**: Agent A owns all files under `aitbc/` except `aitbc/constants.py` and `aitbc/log_utils/`. Agent B owns `aitbc/constants.py`, `aitbc/log_utils/`, all `apps/` files, `cli/` files, and systemd config. Both agents must not edit the same file.

---

## Agent A — Type Safety & Shared Core

**Scope**: All MyPy type fixes in the `aitbc/` shared core library, `TypeAlias` migration, and stale `type: ignore` cleanup.

**Working directory**: `/opt/aitbc/aitbc/`

**Verification command**:
```bash
cd /opt/aitbc && ./venv/bin/python -m mypy --show-error-codes aitbc/ && ./venv/bin/python -m ruff check aitbc/
```

### Tasks

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| A1 | Fix MyPy errors in `aitbc/queues/` — implicit Optional, call-overload, unreachable | High | `queues/decorators.py`, `queues/worker.py`, `queues/task.py`, `queues/scheduler.py` | ✅ DONE |
| A2 | Fix `AITBCHTTPClient` response typing in `blockchain_service.py` — `.json()` on dict | High | `blockchain/blockchain_service.py` | ✅ DONE |
| A3 | Fix MyPy errors in `aitbc/database/` — `connection.py` and `replica.py` | High | `database/connection.py`, `database/replica.py` | ✅ DONE |
| A4 | Fix MyPy errors in `distributed_tracing.py` — import stubs, `TracerProvider` | High | `distributed_tracing.py` | ✅ DONE |
| A5 | Fix MyPy errors in `agent_bridge/src/integration_layer.py` — `union-attr`, `no-any-return` | High | `agent_bridge/src/integration_layer.py` | ✅ DONE |
| A6 | Fix MyPy errors in `api_utils.py` — implicit Optional | High | `api_utils.py` | ✅ DONE |
| A7 | Fix MyPy errors in `tracing.py` — import stubs, `attr-defined` | High | `tracing.py` | ✅ DONE |
| A8 | Fix MyPy errors in `agent_trading` + `agent_compliance` — `unused-ignore`, `no-any-return` | High | `agent_trading/src/trading_agent.py`, `agent_compliance/src/compliance_agent.py` | ✅ DONE |
| A9 | Fix MyPy errors in `ethereum_rpc.py`, `access_control.py`, `price_oracle.py` | High | `ethereum_rpc.py`, `access_control.py`, `oracles/price_oracle.py` | ✅ DONE |
| A10 | Fix MyPy errors in `agent_registry/src/discovery.py` — implicit Optional | High | `agent_registry/src/discovery.py` | ✅ DONE |
| A11 | Fix MyPy errors in `config/__init__.py` + `hierarchical_config.py` | High | `config/__init__.py`, `config/hierarchical_config.py` | ✅ DONE |
| A12 | Fix MyPy errors in `agent_registry/tests/` — `import-not-found` | High | `agent_registry/tests/test_unit_agent_registry.py`, `agent_registry/tests/test_integration_agent_registry.py`, `agent_registry/tests/test_edge_cases_agent_registry.py` | ✅ DONE |
| A13 | Fix MyPy errors in `agent_protocols/`, `events/`, `circuit_breaker/`, `stage_runner/`, `registration.py` | High | `agent_protocols/src/task_manager.py`, `agent_protocols/src/message_protocol.py`, `events/events.py`, `network/circuit_breaker.py`, `training_setup/stage_runner.py`, `agent_registry/src/registration.py` | ✅ DONE |
| A14 | Migrate deprecated `TypeAlias` syntax in `config/__init__.py` (UP040) | Medium | `config/__init__.py` | ✅ DONE |
| A15 | Clean up stale `type: ignore` comments flagged by `--warn-unused-ignores` | Medium | `agent_registry/tests/*.py` | ✅ DONE |

### Agent A — Bug Fix (in shared core)

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| A16 | **Bug:** `debounce` decorator propagated `CancelledError` to superseded callers | Medium | `queues/decorators.py` | ✅ DONE |

### Agent A — Detailed Instructions

#### A1: Queue system type fixes
- Type `last_called: list[float]` and `timer: list[asyncio.Task[Any] | None]` in `decorators.py`
- Remove unreachable `assert` in `decorators.py`
- Fix implicit Optional: `kwargs: dict[str, Any] | None = None` in `worker.py`, `task.py`, `scheduler.py`

#### A2: Blockchain service response typing
- `AITBCHTTPClient.get()` and `.post()` return `dict[str, Any]` (already parsed JSON). Remove all redundant `.json()` calls.
- Cast `tx_hash` to `str` to fix `no-any-return`.

#### A3: Database connection type fixes
- Type `self._connection: sqlite3.Connection | None` in `connection.py`. Use local variable with `assert` in `connect()`. Remove unused `type: ignore`.
- Type `self.primary_engine: Any`, annotate `self.replica_engines: list[Any]`, add return types to `get_read_engine`, `get_write_engine`, `get_session`, `_setup_monitoring` in `replica.py`.

#### A4: Distributed tracing import fixes
- Add `type: ignore[import-not-found]` for Jaeger and HTTPX OpenTelemetry instrumentor imports.
- Type `_tracer` and `_provider` as `Any`. Add return types to `get_tracer`, `start_span`, `end_span`.
- Remove redundant `type: ignore[union-attr]`.

#### A5: Agent bridge integration layer
- Type `self.session: aiohttp.ClientSession | None`.
- Add `assert self.session is not None` guards before all `self.session.get()`/`.post()` calls.
- Wrap `response.json()` with `dict()` to satisfy `no-any-return`.

#### A6: API utilities
- Fix implicit Optional defaults in `build_cors_headers` (`allowed_origins`, `allowed_methods`, `allowed_headers`) and `sanitize_response` (`sensitive_fields`).

#### A7: Tracing module
- Add `type: ignore[import-not-found]` for HTTPX instrumentor import.
- Change `_tracer` and `_tracer_provider` from `object | None` to `Any`.
- Change `get_tracer()` return type to `Any`.

#### A8: Agent trading and compliance
- Fix `type: ignore` code from `import-not-found` to `import-untyped`.
- Cast `bool()` on `stop()` return and `dict()` on `get_status()` return.

#### A9: Ethereum RPC, access control, price oracle
- `ethereum_rpc.py`: Type `self._w3: Any = None`, add `-> Any` return type to `_get_web3()`.
- `access_control.py`: Add `type: ignore[arg-type]` for `jwt.encode()` and `jwt.decode()`.
- `price_oracle.py`: Cast `json.load()` result to `dict[str, Any]`, add `cast` import.

#### A10: Agent registry discovery
- Fix implicit Optional in `find_agents_by_capability` and `find_agents_by_type` (`filters: dict[str, Any] | None = None`).
- Update `_matches_filters` signature. Add `Any` import.

#### A11: Config module
- Migrate deprecated `TypeAlias` syntax to `type` annotations (UP040). Remove `TypeAlias` from imports.
- Clean up unused `type: ignore` codes. Add `type: ignore[import-untyped]` for `yaml` import in `hierarchical_config.py`.

#### A12: Agent registry tests
- Add `type: ignore[import-not-found]` on the **first** `import app` / `from app import ...` in each test file.
- Remove `type: ignore` from all subsequent `import app` statements in the same file.

#### A13: Additional type fixes
- `task_manager.py`: Type `Task.completed_at: datetime | None`, `Task.result: dict[str, Any] | None`, `Task.error: str | None`.
- `message_protocol.py`: Type `self.messages: list[dict[str, Any]]` and `self.received_messages: list[dict[str, Any]]`.
- `events.py`: Fix `Event.timestamp: datetime | None = None`.
- `circuit_breaker.py`: Type `self.open_time: datetime | None = None`.
- `stage_runner.py`: Add `dict[str, Any]` annotation for `results` dict.
- `registration.py`: Fix implicit Optional for `metadata: dict[str, Any] | None = None`.

#### A14: TypeAlias migration
- Part of A11 — migrate `TypeAlias` to `type` statement syntax in `config/__init__.py`.

#### A15: Stale type: ignore cleanup
- Change `type: ignore[import]` to `type: ignore[import-not-found]` on first import in each test file.
- Remove `type: ignore` from subsequent `import app` in same file.
- Verify `type: ignore` in `aitbc_logging.py`, `log_utils/logging.py`, `caching/blockchain_cache.py`, `network/web3_utils.py` are still needed.

#### A16: Debounce CancelledError bug
- In `queues/decorators.py`, wrap `await task` in `try/except asyncio.CancelledError` that returns `None` for superseded calls.
- Verify: superseded caller returns `None`, latest caller returns its value.

---

## Agent B — Bug Fixes, Infrastructure & Apps

**Scope**: Bug fixes in `apps/`, CLI path corrections, logging consolidation, environment configuration, systemd repair, and duplicate route audit.

**Working directory**: `/opt/aitbc/` (cross-cutting)

**Verification commands**:
```bash
cd /opt/aitbc && ./venv/bin/python -m ruff check . && ./venv/bin/python -m mypy --show-error-codes apps/coordinator-api/src apps/blockchain-node/src
```

### Tasks

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| B1 | Fix Ruff errors (audit entire repo) | Medium | — | ✅ DONE (none found) |
| B2 | Audit duplicate route registrations in coordinator-api | Medium | `apps/coordinator-api/src/app/main.py` | ✅ DONE |
| B3 | Fix circuit breaker unreachable code + state manager unreachable statements | Low | `network/circuit_breaker.py` (coordination with Agent A) | ✅ DONE |
| B4 | Fix `aitbc-recovery` broken systemd symlink | Low | `/etc/systemd/system/aitbc-recovery.service` | ✅ DONE |
| B5 | **Bug:** Broken `AgentServiceBridge` import in trading + compliance agents | High | `aitbc/agent_trading/src/trading_agent.py`, `aitbc/agent_compliance/src/compliance_agent.py` | ✅ DONE |
| B6 | **Bug:** Biased/bursty read-replica routing using `hash(time.time())` | Medium | `aitbc/database/replica.py` | ✅ DONE |
| B7 | **Bug:** PoA block proposer recorded `nonce - 1` for confirmed transactions | High | `apps/blockchain-node/src/aitbc_chain/consensus/poa.py` | ✅ DONE |
| B8 | **Bug:** CLI workflow commands used non-existent API paths | High | `cli/aitbc_cli/commands/workflow.py` | ✅ DONE |
| B9 | Consolidate duplicate logging modules (`log_utils/logging.py` → re-export) | Medium | `aitbc/log_utils/logging.py`, `aitbc/log_utils/__init__.py` | ✅ DONE |
| B10 | Make `REPO_DIR` environment-sourced via `AITBC_REPO_DIR` env var | Medium | `aitbc/constants.py` | ✅ DONE |
| B11 | Add `session.rollback()` in PoA tx processing exception handler | Medium | `apps/blockchain-node/src/aitbc_chain/consensus/poa.py` | ✅ DONE |

### Agent B — Detailed Instructions

#### B1: Ruff audit
- Run `ruff check .` across the entire repo. Fix any errors found.
- Expected result: 0 errors (verified — none found).

#### B2: Duplicate route registration audit
- **Problem**: `agent_router` was included twice in `apps/coordinator-api/src/app/main.py`:
  - Line 313: `app.include_router(agent_router, prefix="/v1")` → routes at `/v1/workflows`, `/v1/executions`
  - Line 378: `app.include_router(agent_router, prefix="/v1/agents")` → routes at `/v1/agents/workflows`, `/v1/agents/executions`
- **Fix**: Remove the redundant inclusion at line 313. Keep only the `/v1/agents` prefix.
- **Verify**: App starts with 378 routes and 0 duplicates.

#### B3: Circuit breaker unreachable code
- Fix unreachable code in `aitbc/network/circuit_breaker.py` (type `open_time: datetime | None`).
- **Note**: Coordinate with Agent A's A13 task on `circuit_breaker.py` — Agent A handles the type annotation, Agent B handles the unreachable code logic. Agent A goes first.

#### B4: aitbc-recovery systemd symlink
- **Problem**: Service file at `/opt/aitbc/scripts/utils/aitbc-recovery.service` not symlinked into `/etc/systemd/system/`.
- **Fix**: `ln -s /opt/aitbc/scripts/utils/aitbc-recovery.service /etc/systemd/system/aitbc-recovery.service && systemctl daemon-reload`
- **Verify**: `systemctl status aitbc-recovery` shows `Loaded: loaded (...; linked; preset: enabled)`.

#### B5: Broken AgentServiceBridge import
- **Problem**: `trading_agent.py` and `compliance_agent.py` imported from `apps.agent_services.agent_bridge.src.integration_layer` which does not exist. The `type: ignore[import-untyped]` was masking the runtime breakage.
- **Fix**: Change import to `from aitbc.agent_bridge.src.integration_layer import AgentServiceBridge`. Remove the `type: ignore`.
- **Verify**: Both modules import cleanly. Bridge method names (`start_agent`, `stop_agent`, `get_agent_status`, `execute_agent_task`) match call sites.
- **Note**: Coordinate with Agent A's A8 task — Agent A handles the `type: ignore` code fix, Agent B handles the import path fix. Agent B goes first to fix the path, then Agent A adjusts the ignore.

#### B6: Biased read-replica routing
- **Problem**: `ReadReplicaManager.get_read_engine()` used `hash(time.time()) % 100 >= self.read_weight`. `hash()` of a float is not uniform; consecutive calls in tight loops return identical values causing bursty routing.
- **Fix**: Replace with `random.randint(0, 99) >= self.read_weight`. Add `import random`.
- **Note**: Coordinate with Agent A's A3 task on `replica.py` — Agent A handles type annotations, Agent B handles the routing logic. Agent A goes first.

#### B7: PoA nonce off-by-one
- **Problem**: In `poa.py`, `Transaction` created with `nonce=sender_account.nonce - 1`. ORM object not refreshed after raw SQL `UPDATE account SET nonce = nonce + 1`, so it double-subtracts.
- **Fix**: Change to `nonce=tx_data_for_transition["nonce"]` — the exact nonce validated and used for the state transition.

#### B8: CLI workflow API paths
- **Problem**: `cli/aitbc_cli/commands/workflow.py` called `/v1/workflows/execute`, `/v1/workflows/{name}/status`, `/v1/workflows/{name}/stop`. Agent router is at `/v1/agents` prefix.
- **Fix**: Update to:
  - `run`: `POST /v1/agents/workflows/{workflow_id}/execute` with `AgentExecutionRequest` payload
  - `status`: `GET /v1/agents/executions/{execution_id}/status`
  - `stop`: `POST /v1/agents/workflows/{workflow_id}/cancel?execution_id=...`

#### B9: Consolidate logging modules
- **Problem**: `aitbc_logging.py` (432+ importers) and `log_utils/logging.py` (1 importer) had near-identical copies.
- **Fix**: Replace `log_utils/logging.py` with a thin re-export shim from `aitbc_logging.py`. `BlockchainTextFormatter` becomes alias for `JournalFormatter`. Update `log_utils/__init__.py` to export `JournalFormatter` and `configure_uvicorn_logging`.

#### B10: REPO_DIR environment sourcing
- **Problem**: `aitbc/constants.py` hardcoded `REPO_DIR = Path("/opt/aitbc")`.
- **Fix**: Change to `REPO_DIR = Path(os.environ.get("AITBC_REPO_DIR", "/opt/aitbc"))`. Defaults to `/opt/aitbc` for backward compatibility.

#### B11: PoA session rollback
- **Problem**: In `poa.py`'s `_propose_block()`, per-tx exception handler logged error and continued without rolling back partial state changes.
- **Fix**: Add `session.rollback()` before `continue` in the exception handler.
- **Note**: Same file as B7. Both fixes should be applied together to `poa.py`.

---

## Coordination Protocol

### File Ownership

| File | Owner | Notes |
|------|-------|-------|
| `aitbc/queues/*` | Agent A | Type fixes + debounce bug |
| `aitbc/database/replica.py` | Agent A (types) → Agent B (routing) | Sequential: A first, then B |
| `aitbc/agent_trading/src/trading_agent.py` | Agent B (import path) → Agent A (type ignore) | Sequential: B first, then A |
| `aitbc/agent_compliance/src/compliance_agent.py` | Agent B (import path) → Agent A (type ignore) | Sequential: B first, then A |
| `aitbc/network/circuit_breaker.py` | Agent A (type annotation) → Agent B (unreachable code) | Sequential: A first, then B |
| `apps/blockchain-node/src/aitbc_chain/consensus/poa.py` | Agent B | Both B7 and B11 — apply together |
| `aitbc/log_utils/*` | Agent B | Logging consolidation |
| `aitbc/constants.py` | Agent B | REPO_DIR env var |
| `apps/coordinator-api/src/app/main.py` | Agent B | Route audit |
| `cli/aitbc_cli/commands/workflow.py` | Agent B | CLI path fix |

### Execution Order

1. **Phase 1** (parallel): Agent A tasks A1–A13, A14, A15 | Agent B tasks B1, B2, B4, B8, B9, B10
2. **Phase 2** (sequential, Agent A first): A3 (replica.py types) → B6 (replica.py routing fix)
3. **Phase 3** (sequential, Agent A first): A13 (circuit_breaker.py types) → B3 (circuit_breaker.py unreachable code)
4. **Phase 4** (sequential, Agent B first): B5 (import path fix) → A8 (type ignore adjustment)
5. **Phase 5** (parallel): A16 (debounce bug) | B7 + B11 (PoA fixes, same file)

### Verification Checklist

After all tasks complete, verify:

- [ ] `mypy aitbc/` → 0 errors
- [ ] `mypy` with `--warn-unused-ignores` (bypassing excludes) → 0 errors
- [ ] `ruff check aitbc/` → All checks passed
- [ ] `ruff check .` → All checks passed
- [ ] coordinator-api route audit → 378 routes, 0 duplicates
- [ ] `aitbc-recovery.service` → Loaded: loaded (linked; preset: enabled)
- [ ] `trading_agent.py` and `compliance_agent.py` import cleanly at runtime
- [ ] CLI workflow commands use correct `/v1/agents/workflows/*` paths
- [ ] `log_utils/logging.py` re-exports from `aitbc_logging.py`
- [ ] `REPO_DIR` sources from `AITBC_REPO_DIR` env var

---

## Known Issues / Suggestions (Not in Scope)

These were identified during the audit but left for future releases:

- **`stage_runner.validate_conditions()` is a no-op stub** — always returns `passed: True`. Needs real implementation.
- **`ReadReplicaManager.get_session()` rebuilds sessionmaker on every call** — cache per engine at init.
- **`EventBus.publish_sync()` uses `asyncio.run()`** — raises `RuntimeError` in running event loop. Detect and schedule instead.
- **`AgentMessageClient.receive_messages()` uses O(n) list membership** — track delivered IDs in a `set`.
- **`type: ignore` on imports can mask runtime breakage** — add CI step that imports every top-level module.

> **Note**: The first four items above were resolved in commit `38a0c70cc` ("Phase 1 quick wins — event bus, replica session, message dedup, miner creds") after this section was written. They are retained here for release-history continuity.

---

## Next Release — v0.5.12 (Agent B Plan)

**Release theme**: Duplication elimination & large-file decomposition in `apps/` and `cli/`.

**Status of prior phases** (verified on disk 2026-06-24):
- Phase 1 (quick wins): ✅ DONE — committed in `38a0c70cc`
- Phase 2 (test split): ✅ DONE — `tests/integration/test_agent_coordinator.py` (3,177 lines) split into 9 domain files (`test_auth.py`, `test_agents.py`, `test_ai.py`, `test_consensus.py`, `test_messages.py`, `test_monitoring.py`, `test_tasks.py`, `test_integration_scenarios.py`, `conftest.py`); original deleted.
- Phase 3 (dedup + indexes): **IN PROGRESS** — database indexes ✅ DONE (uncommitted, this session); config/db duplication + large-file decomposition remain.
- Phase 4 (coordinator-api bounded context): not started.

**Agent B working directory**: `/opt/aitbc/` (cross-cutting: `apps/`, `cli/`).

**Verification**:
```bash
cd /opt/aitbc && ./venv/bin/python -m ruff check apps/ cli/ && ./venv/bin/python -m mypy --show-error-codes apps/coordinator-api/src apps/blockchain-node/src
```

### Tasks

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| B12 | Commit the database index additions (35 single-col + 11 composite) + Alembic migration from this session | High | `apps/coordinator-api/src/app/domain/*.py`, `apps/coordinator-api/src/app/contexts/agent_identity/domain/agent_identity.py`, `apps/coordinator-api/alembic/versions/add_query_performance_indexes.py` | ⏳ PENDING (work done, needs commit) |
| B13 | Consolidate duplicated `DatabaseConfig` — agent-management/coordinator-api/edge should subclass `shared-core`'s `ServiceSettings`/`DatabaseConfig` instead of redefining | High | `apps/agent-management/src/app/core/config.py`, `apps/coordinator-api/src/app/config.py`, `apps/edge/src/aitbc_edge/config.py` | ⏳ PENDING |
| B14 | Remove duplicate CLI `dual_mode_wallet_adapter.py` — `cli/utils/` copy is stale; keep `cli/aitbc_cli/utils/` version, delete the other | Medium | `cli/utils/dual_mode_wallet_adapter.py` | ⏳ PENDING |
| B15 | Decompose `apps/blockchain-explorer/main.py` (1,442 lines) — split routes into a `routers/` package, keep `main.py` as app factory | Medium | `apps/blockchain-explorer/main.py`, new `apps/blockchain-explorer/routers/*.py` | ⏳ PENDING |
| B16 | Decompose `apps/exchange/simple_exchange_api.py` (1,209 lines, stdlib `http.server`) — extract handlers + db layer | Medium | `apps/exchange/simple_exchange_api.py` | ⏳ PENDING |
| B17 | Audit duplicate `database.py` files — `apps/exchange/database.py` vs `apps/exchange/api/database.py` (genuinely different layers, likely rename for clarity); `apps/edge/src/aitbc_edge/routers/database.py` vs `schemas/database.py` (router vs schemas — not dup, no action) | Low | `apps/exchange/database.py`, `apps/exchange/api/database.py` | ⏳ PENDING |
| B18 | Verify all systemd symlinks present (recovery ✅, backup, monitoring, etc.) and that service files exist at symlink targets | Low | `/etc/systemd/system/aitbc*.service` | ⏳ PENDING |

> Task numbering continues from B11 (the last v0.5.11 Agent B task) to preserve a single contiguous Agent B task history across releases.

### Detailed Instructions

#### B12: Commit index work
- Stage the 10 modified domain files + the new migration `add_query_performance_indexes.py`.
- Commit message: `perf(db): add query performance indexes to coordinator-api domain models`.
- Do NOT touch `tests/integration/` (Agent A's test-split work is uncommitted there).
- **Audit basis**: indexes were chosen by cross-referencing actual SQL query patterns (`.where(Model.col == ...)` and `order_by(Model.col)`) in the storage/router/service layers — not blanket indexing. Verified all 46 expected indexes generate via `SQLModel.metadata.create_all` on in-memory SQLite.

#### B13: DatabaseConfig consolidation
- **Problem**: `DatabaseConfig` with `effective_url` is copy-pasted in `apps/shared-core/src/app/core/config.py` (canonical, 55 lines), `apps/agent-management/src/app/core/config.py` (65 lines), `apps/coordinator-api/src/app/config.py` (242 lines), `apps/edge/src/aitbc_edge/config.py` (42 lines). Each drifts (different default DB filenames, different postgres URLs).
- **Fix**: In each non-canonical config, import `DatabaseConfig`/`ServiceSettings` from shared-core and subclass with service-specific overrides only. Keep per-service default DB filename via a subclass override of `effective_url` or a `db_filename` field.
- **Verify**: `mypy` + `ruff` clean on the 3 modified files; each service still imports its settings correctly.

#### B14: CLI duplicate wallet adapter
- **Problem**: `cli/utils/dual_mode_wallet_adapter.py` (626 lines) and `cli/aitbc_cli/utils/dual_mode_wallet_adapter.py` (626 lines) differ only in import paths (`from utils import ...` vs `from aitbc_cli.utils import ...`). The `cli/utils/` copy is the stale pre-package layout.
- **Fix**: Delete `cli/utils/dual_mode_wallet_adapter.py`. Grep for importers of `cli.utils.dual_mode_wallet_adapter` and repoint to `aitbc_cli.utils.dual_mode_wallet_adapter`.
- **Verify**: `ruff check cli/` clean; `grep -r "cli.utils.dual_mode"` returns nothing.

#### B15: blockchain-explorer decomposition
- `main.py` (1,442 lines) defines the FastAPI app + all routes inline.
- Split into `routers/blocks.py`, `routers/transactions.py`, `routers/chains.py`, `routers/stats.py` (group by existing route prefixes). `main.py` becomes app factory + `include_router` calls + uvicorn entrypoint.
- Keep the SSRF validation patterns (`TX_HASH_PATTERN`, `CHAIN_ID_PATTERN`) in a shared `validation.py`.
- **Verify**: app still starts; route count unchanged.

#### B16: exchange simple_exchange_api decomposition
- `simple_exchange_api.py` (1,209 lines) uses stdlib `http.server` (not FastAPI) with inline SQLite.
- Extract: `db.py` (schema + connection), `handlers.py` (request handlers by path), keep `simple_exchange_api.py` as the `HTTPServer` wiring.
- This is stdlib HTTP — no router framework, so group handlers into functions keyed by path prefix.
- **Verify**: server boots; existing exchange tests pass.

#### B17: exchange database.py audit
- `apps/exchange/database.py` (SQLAlchemy `Base` + engine) and `apps/exchange/api/database.py` (sqlite3 + logging) serve different layers. **Decision pending**: likely rename `api/database.py` → `api/db_init.py` to avoid name collision, OR leave as-is with a clarifying docstring. Investigate importers before deciding.

#### B18: systemd symlink audit
- All 12 `aitbc*.service` symlinks verified present (recovery ✅ from v0.5.11). Confirm each symlink target file exists and is non-empty. Report any dangling symlinks.

### Execution Order

1. **B12** first (commit pending index work — clears the working tree).
2. **B13, B14, B18** in parallel (independent, no shared files).
3. **B15, B16** sequential (each is a large refactor; verify one before starting the next).
4. **B17** last (investigation/decision task).

### Coordination with Agent A

- Agent A owns `aitbc/` (types, queues, db connection types). Agent B's B13 touches `apps/*/config.py` only — no `aitbc/` config files. No conflict.
- If B13 requires a shared `DatabaseConfig` to move into `aitbc/`, that becomes Agent A's file — escalate and sequence (A first).
- B15/B16 are pure `apps/` refactors — no Agent A overlap.

---

*Last updated: 2026-06-24*
*Release: v0.5.11 (complete) → v0.5.12 (Agent B plan appended)*
*Status: v0.5.11 all tasks complete; v0.5.12 Agent B plan in progress*
