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

## Current Plan — v0.5.12 (Agent B) — ✅ COMPLETE

**Release theme**: Duplication elimination & large-file decomposition in `apps/` and `cli/`.

**All B1–B7 tasks complete** (verified 2026-06-24). Full task table, detailed instructions, execution order, and coordination notes moved to <ref_file file="/opt/aitbc/docs/releases/v0.5.12/change.log" /> (see "Completed Work (Agent B)" section).

**Status of prior phases**:
- Phase 1 (quick wins): ✅ DONE (committed in `38a0c70cc`)
- Phase 2 (test split): ✅ DONE — `tests/integration/test_agent_coordinator.py` (3,177 lines) split into 9 domain files; original deleted.
- Phase 3 (dedup + indexes): ✅ DONE — B1–B7 all complete. Verified 2026-06-24.
- Phase 4 (coordinator-api bounded context): P1 ✅ DONE, P2 ✅ DONE, P3 ✅ DONE, P4 ✅ DONE, P5 ⏭️ SKIPPED. **Phase 4 complete.**

**Agent B working directory**: `/opt/aitbc/` (cross-cutting: `apps/`, `cli/`).

**Verification**:
```bash
cd /opt/aitbc && ./venv/bin/python -m ruff check apps/ cli/ && ./venv/bin/python -m mypy --show-error-codes apps/coordinator-api/src apps/blockchain-node/src
```

---

## Open Tasks — v0.5.13 (Agent B): Phase 4 — coordinator-api bounded context — ✅ COMPLETE

**Full task details, grounding facts, and corrections from the rejected draft are in** <ref_file file="/opt/aitbc/docs/releases/v0.5.12/change.log" /> (see "Phase 4 Open Tasks" section).

### Task Summary

| # | Task | Priority | Status |
|---|------|----------|--------|
| P1 | Standardize on PyJWT — migrate `jwt_auth.py` from `python-jose` to `PyJWT`, drop `python-jose` dep | High | ✅ DONE |
| P2 | Audit + document cross-context imports into `app/domain/` | High | ✅ DONE |
| P3 | Add `README.md` to each `contexts/*/` + `__all__` to `__init__.py` files | Medium | ✅ DONE |
| P4 | Decide agent-coordinator service boundary (fold in vs keep separate) + add README | Medium | ✅ DONE |
| P5 | Restructure agent-coordinator into bounded context (GATED on P4) | Low | ⏭️ SKIPPED (P4 decided "keep separate") |

**All Phase 4 tasks complete.** P5 skipped — P4 decision doc (`docs/releases/v0.5.13/agent_coordinator_boundary.md`) recommends keeping agent-coordinator as a separate service (zero runtime coupling between the two services).
