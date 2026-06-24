# AGENTS.md — AITBC Project Rules & Agent Plans

This file is the source of truth for project conventions, verification commands, and per-agent task plans. Agent-specific plans live at `docs/releases/<version>/AGENTS.md`; this root file holds the stable conventions and the **current** in-flight plan.

## Project Layout

- `aitbc/` — shared core library (types, config, db, logging, queues, crypto, network, agent_bridge, agent_protocols, agent_registry, etc.)
- `apps/` — microservices (coordinator-api, blockchain-node, exchange, wallet, marketplace, miner, edge, gpu, governance, …)
- `cli/` — `aitbc_cli` command-line tool
- `packages/py/` — publishable Python packages
- `tests/` — `unit/`, `integration/`, `e2e/`, `coordinator/`
- `scripts/` — ops, deployment, monitoring, migration, security
- `docs/releases/<version>/` — per-release changelogs and agent task assignment

## Verification Commands

```bash
# Type check (shared core)
./venv/bin/python -m mypy --show-error-codes aitbc/

# Lint (whole repo)
./venv/bin/python -m ruff check .

# Tests (note: requires pytest-rerunfailures + pytest-asyncio; add -o addopts="" to bypass if missing)
./venv/bin/python -m pytest tests/unit -q
./venv/bin/python -m pytest tests/integration -q

# Coordinator-api tests (needs PYTHONPATH=src and aitbc_shared installed)
cd apps/coordinator-api && PYTHONPATH=src ../../venv/bin/python -m pytest tests -q -o addopts=""
```

## Conventions

- **Python 3.13**, line length 127 (black + ruff), `target-version = "py313"`.
- **SQLModel** for ORM models in `apps/coordinator-api/src/app/domain/`. Add `index=True` on columns filtered/ordered at the SQL layer. Composite indexes via `sqlalchemy.Index(...)` in `__table_args__` tuple.
- **Config**: `pydantic_settings.BaseSettings`. Shared base lives in `apps/shared-core/src/app/core/config.py` (`ServiceSettings`, `DatabaseConfig`). New services should subclass these rather than redefining `DatabaseConfig`.
- **Logging**: `aitbc.aitbc_logging` is canonical. `aitbc/log_utils/logging.py` is a thin re-export shim — do not duplicate logging setup.
- **Constants**: `aitbc/constants.py` sources `REPO_DIR` from `AITBC_REPO_DIR` env var (defaults to `/opt/aitbc`).
- **DB init**: services call `SQLModel.metadata.create_all` (or `Base.metadata.create_all`). `create_all` only adds indexes to fresh DBs; for existing DBs add an Alembic migration under `apps/coordinator-api/alembic/versions/` using `if_not_exists=True`.
- **Commit style**: `type(scope): subject` — see `git log --oneline`. Include `Generated with [Devin]` trailer + Co-Authored-By when committing via Devin.
- **Do not** edit files outside your agent's ownership without coordinating (see conflict boundaries in the release plan).

## Agent Roles (stable across releases)

| Agent | Domain | Owns |
|-------|--------|------|
| **Agent A** | Type safety & shared core (`aitbc/`) | All of `aitbc/` except `aitbc/constants.py`, `aitbc/log_utils/` |
| **Agent B** | Bug fixes, infrastructure & apps | `aitbc/constants.py`, `aitbc/log_utils/`, all `apps/`, `cli/`, systemd config |

**Conflict boundary**: both agents must not edit the same file. Shared files (`aitbc/database/replica.py`, `aitbc/network/circuit_breaker.py`, agent bridge imports) are sequenced — see the release plan's Coordination Protocol.

---

## Current Plan — v0.5.12 (Agent B)

**Release theme**: Duplication elimination & large-file decomposition in `apps/` and `cli/`.

**Status of prior phases**:
- Phase 1 (quick wins): ✅ DONE (committed in `38a0c70cc`)
- Phase 2 (test split): ✅ DONE — `tests/integration/test_agent_coordinator.py` (3,177 lines) split into 9 domain files; original deleted.
- Phase 3 (dedup + indexes): **IN PROGRESS** — database indexes ✅ DONE (this session, uncommitted); config/db duplication + large-file decomposition remain.
- Phase 4 (coordinator-api bounded context): not started.

**Agent B working directory**: `/opt/aitbc/` (cross-cutting: `apps/`, `cli/`).

**Verification**:
```bash
cd /opt/aitbc && ./venv/bin/python -m ruff check apps/ cli/ && ./venv/bin/python -m mypy --show-error-codes apps/coordinator-api/src apps/blockchain-node/src
```

### Tasks

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| B1 | Commit the database index additions (35 single-col + 11 composite) + Alembic migration from this session | High | `apps/coordinator-api/src/app/domain/*.py`, `apps/coordinator-api/src/app/contexts/agent_identity/domain/agent_identity.py`, `apps/coordinator-api/alembic/versions/add_query_performance_indexes.py` | ⏳ PENDING (work done, needs commit) |
| B2 | Consolidate duplicated `DatabaseConfig` — agent-management/coordinator-api/edge should subclass `shared-core`'s `ServiceSettings`/`DatabaseConfig` instead of redefining | High | `apps/agent-management/src/app/core/config.py`, `apps/coordinator-api/src/app/config.py`, `apps/edge/src/aitbc_edge/config.py` | ⏳ PENDING |
| B3 | Remove duplicate CLI `dual_mode_wallet_adapter.py` — `cli/utils/` copy is stale; keep `cli/aitbc_cli/utils/` version, delete the other | Medium | `cli/utils/dual_mode_wallet_adapter.py` | ⏳ PENDING |
| B4 | Decompose `apps/blockchain-explorer/main.py` (1,442 lines) — split routes into a `routers/` package, keep `main.py` as app factory | Medium | `apps/blockchain-explorer/main.py`, new `apps/blockchain-explorer/routers/*.py` | ⏳ PENDING |
| B5 | Decompose `apps/exchange/simple_exchange_api.py` (1,209 lines, stdlib `http.server`) — extract handlers + db layer | Medium | `apps/exchange/simple_exchange_api.py` | ⏳ PENDING |
| B6 | Audit duplicate `database.py` files — `apps/exchange/database.py` vs `apps/exchange/api/database.py` (genuinely different, likely keep both but rename for clarity); `apps/edge/src/aitbc_edge/routers/database.py` vs `schemas/database.py` (router vs schemas — not dup, no action) | Low | `apps/exchange/database.py`, `apps/exchange/api/database.py` | ⏳ PENDING |
| B7 | Verify all systemd symlinks present (recovery ✅, backup, monitoring, etc.) and that service files exist at symlink targets | Low | `/etc/systemd/system/aitbc*.service` | ⏳ PENDING |

### Detailed Instructions

#### B1: Commit index work
- Stage the 10 modified domain files + the new migration `add_query_performance_indexes.py`.
- Commit message: `perf(db): add query performance indexes to coordinator-api domain models`.
- Do NOT touch `tests/integration/` (Agent A's test-split work is uncommitted there).

#### B2: DatabaseConfig consolidation
- **Problem**: `DatabaseConfig` with `effective_url` is copy-pasted in `apps/shared-core/src/app/core/config.py` (canonical), `apps/agent-management/src/app/core/config.py`, `apps/coordinator-api/src/app/config.py`, `apps/edge/src/aitbc_edge/config.py`. Each drifts (different default DB filenames, different postgres URLs).
- **Fix**: In each non-canonical config, `from aitbc_shared.core.config import DatabaseConfig, ServiceSettings` (or the shared-core path) and subclass with service-specific overrides only. Keep per-service default DB filename via a subclass override of `effective_url` or a `db_filename` field.
- **Verify**: `mypy` + `ruff` clean on the 3 modified files; each service still imports its settings correctly.

#### B3: CLI duplicate wallet adapter
- **Problem**: `cli/utils/dual_mode_wallet_adapter.py` (626 lines) and `cli/aitbc_cli/utils/dual_mode_wallet_adapter.py` (626 lines) differ only in import paths (`from utils import ...` vs `from aitbc_cli.utils import ...`). The `cli/utils/` copy is the stale pre-package layout.
- **Fix**: Delete `cli/utils/dual_mode_wallet_adapter.py`. Grep for importers of `cli.utils.dual_mode_wallet_adapter` and repoint to `aitbc_cli.utils.dual_mode_wallet_adapter`.
- **Verify**: `ruff check cli/` clean; `grep -r "cli.utils.dual_mode" ` returns nothing.

#### B4: blockchain-explorer decomposition
- `main.py` (1,442 lines) defines the FastAPI app + all routes inline.
- Split into `routers/blocks.py`, `routers/transactions.py`, `routers/chains.py`, `routers/stats.py` (group by existing route prefixes). `main.py` becomes app factory + `include_router` calls + uvicorn entrypoint.
- Keep the SSRF validation patterns (`TX_HASH_PATTERN`, `CHAIN_ID_PATTERN`) in a shared `validation.py`.
- **Verify**: app still starts; route count unchanged.

#### B5: exchange simple_exchange_api decomposition
- `simple_exchange_api.py` (1,209 lines) uses stdlib `http.server` (not FastAPI) with inline SQLite.
- Extract: `db.py` (schema + connection), `handlers.py` (request handlers by path), keep `simple_exchange_api.py` as the `HTTPServer` wiring.
- This is stdlib HTTP — no router framework, so group handlers into functions keyed by path prefix.
- **Verify**: server boots; existing exchange tests pass.

#### B6: exchange database.py audit
- `apps/exchange/database.py` (SQLAlchemy `Base` + engine) and `apps/exchange/api/database.py` (sqlite3 + logging) serve different layers. **Decision pending**: likely rename `api/database.py` → `api/db_init.py` to avoid name collision, OR leave as-is with a clarifying docstring. Investigate importers before deciding.

#### B7: systemd symlink audit
- All 12 `aitbc*.service` symlinks verified present (recovery ✅ from v0.5.11). Confirm each symlink target file exists and is non-empty. Report any dangling symlinks.

### Execution Order

1. **B1** first (commit pending index work — clears the working tree).
2. **B2, B3, B7** in parallel (independent, no shared files).
3. **B4, B5** sequential (each is a large refactor; verify one before starting the next).
4. **B6** last (investigation/decision task).

### Coordination with Agent A

- Agent A owns `aitbc/` (types, queues, db connection types). Agent B's B2 touches `apps/*/config.py` only — no `aitbc/` config files. No conflict.
- If B2 requires a shared `DatabaseConfig` to move into `aitbc/`, that becomes Agent A's file — escalate and sequence (A first).
- B4/B5 are pure `apps/` refactors — no Agent A overlap.
