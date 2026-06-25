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

## Completed Releases

All prior release plans are complete. Details are in the respective changelogs:

- **v0.5.12** — Duplication elimination & large-file decomposition: <ref_file file="/opt/aitbc/docs/releases/v0.5.12/change.log" />
- **v0.5.13** — coordinator-api bounded context (P1–P4, T1–T3): <ref_file file="/opt/aitbc/docs/releases/v0.5.13/change.log" />
- **v0.5.14** — Cross-context dependency elimination (X1–X9, L1–L19): <ref_file file="/opt/aitbc/docs/releases/v0.5.14/change.log" />
- **v0.5.15** — Flat-to-context migration (P1–P6): <ref_file file="/opt/aitbc/docs/releases/v0.5.15/change.log" />
