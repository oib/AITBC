# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

AITBC is a decentralized marketplace for AI compute: GPU providers offer compute, agents discover/rent it, and clients submit inference/training jobs that are paid, executed, and settled on a multi-island PoA blockchain network. It's a Python 3.13 monorepo (Poetry-managed) of ~20 FastAPI microservices plus a CLI, coordinated through a shared core library.

**`AGENTS.md` at the repo root is the source of truth** for release planning, in-flight work, and agent ownership boundaries — read it before making non-trivial changes. It tracks the current release (`docs/releases/<version>/change.log`), file-ownership rules between concurrent agents, and a history of scope decisions worth knowing before touching bridge/consensus/settlement code.

## Common commands

```bash
# Lint (whole repo) — ruff, line length 127, target py313
./venv/bin/python -m ruff check .

# Type check (shared core only — this is the mypy-clean scope)
./venv/bin/python -m mypy --show-error-codes aitbc/

# Unit / integration tests
./venv/bin/python -m pytest tests/unit -q
./venv/bin/python -m pytest tests/integration -q

# Run a single test
./venv/bin/python -m pytest tests/unit/test_caching.py::test_specific_case -q

# coordinator-api tests (separate package, needs its own src on PYTHONPATH)
cd apps/coordinator-api && PYTHONPATH=src ../../venv/bin/python -m pytest tests -q -o addopts=""

# blockchain-node tests (same pattern)
cd apps/blockchain-node && PYTHONPATH=src ../../venv/bin/python -m pytest tests -q -o addopts=""

# Start the coordinator API locally
cd apps/coordinator-api && PYTHONPATH=src poetry run uvicorn coordinator_api.main:app --reload
```

If pytest complains about missing `pytest-rerunfailures`/`pytest-asyncio` plugins, add `-o addopts=""` to bypass the root `addopts` (reruns/strict-markers) — this is expected in per-app test runs that don't share the root plugin set.

Root-level `pytest` picks up `testpaths` from `pyproject.toml` (`tests/unit`, `tests/integration`, `tests/smoke`, `tests/coordinator`, `tests/e2e`, `tests/security`, `tests/cli`, `tests/services`, `tests/production`, `tests/ui-accessibility`, plus `apps/blockchain-node/tests`) — app-specific suites under other `apps/*/tests` need to be run from within that app as shown above.

## Architecture

### Layout

- `aitbc/` — shared core library: logging, config, crypto, auth, rate limiting, queues, gossip, database helpers, agent bridge/protocols/registry, settlement, tee, compliance, etc. Almost every app imports from here.
- `apps/` — independent FastAPI microservices, each with its own `pyproject.toml` and (usually) `src/<pkg>/` layout: `coordinator-api` (the central job/marketplace/governance API — internally split into ~35 bounded `contexts/` under `src/coordinator_api/contexts/`), `blockchain-node` (PoA consensus, gossip, RPC, sync), `blockchain-explorer`, `wallet`, `exchange`, `marketplace`, `trading`, `pool-hub`, `miner`, `edge`, `gpu`, `governance`, `agent-coordinator`, `ai-engine`, `api-gateway`, `bridge-monitor`, `blockchain-event-bridge`, `whisper`, `ffmpeg`, `zk-circuits`, `memory`, plus `shared-core`/`shared-domain` libraries consumed by several apps.
- `cli/aitbc_cli/` — the `aitbc_cli` command-line tool (50+ command groups: client, miner, wallet, auth, blockchain, marketplace, admin, config, governance, trade, bridge, consensus, chain, node…).
- `packages/py/` — publishable Python packages (`aitbc-sdk`, `aitbc-agent-sdk`, `aitbc-agent-core`, `aitbc-crypto`) and `packages/aitbc-shared` (installed as `aitbc-shared`, develop-mode dependency of the root project).
- `contracts/` — standalone Solidity contracts (ZK receipt verifier).
- `tests/` — cross-cutting `unit/`, `integration/`, `e2e/`, `coordinator/`, `security/`, `cli/`, `smoke/`, `production/`; individual apps also carry their own `apps/*/tests/`.
- `scripts/` — ops/deployment/monitoring/migration/security scripts, organized by purpose (see `docs/architecture/8_codebase-structure.md`).
- `docs/releases/<version>/` — per-release changelogs and (during multi-agent work) agent task assignments; `docs/releases/STATUS.md` gives the release-by-release status overview.

### Cross-app conventions (see `AGENTS.md`/`CONTRIBUTING.md` for the full list)

- **Config**: `pydantic_settings.BaseSettings`. Shared base is `ServiceSettings`/`DatabaseConfig` in `apps/shared-core/src/app/core/config.py` — new services subclass these rather than redefining DB config.
- **Logging**: `aitbc.aitbc_logging` (`configure_logging`, `get_logger`) is canonical everywhere; `aitbc/log_utils/logging.py` is a thin re-export shim, don't duplicate setup.
- **Auth**: `aitbc.auth` provides the unified JWT handler, password hashing, API keys, RBAC, FastAPI dependencies, and middleware — app-level auth modules were consolidated into re-export shims (v0.10.5); don't hand-roll new auth.
- **ORM**: SQLModel for `coordinator-api` domain models (`apps/coordinator-api/src/coordinator_api/domain/`). Add `index=True` on filtered/ordered columns; composite indexes via `sqlalchemy.Index(...)` in `__table_args__`. DB init calls `SQLModel.metadata.create_all`/`Base.metadata.create_all` (adds indexes only to fresh DBs) — for existing DBs, add an Alembic migration under `apps/coordinator-api/alembic/versions/` with `if_not_exists=True`.
- **Constants**: `aitbc/constants.py` derives `AITBC_HOME`/`DATA_DIR`/`CONFIG_DIR`/`LOG_DIR`/`REPO_DIR` from env vars (defaults rooted at `/opt/aitbc` or `/var/lib`, `/etc`, `/var/log` — see the file for the override rules).
- **Money**: financial code (wallet, trading, marketplace, pool-hub billing/pricing) uses `Decimal`, not float — this was a multi-release migration; don't reintroduce floats for amounts.
- **Feature flags**: `feature_flags.json` at repo root gates risky/incomplete behavior (rollout percentage, allow/blacklist). Check it before assuming a capability (e.g. ZK proof verification, structlog, shared agent-integration service) is actually live.

### Multi-agent release model

This repo is developed by coordinated AI agents against a versioned release plan (see `AGENTS.md`). Two stable ownership domains exist:

- **Agent A**: `aitbc/` shared core (except `aitbc/constants.py`, `aitbc/log_utils/`).
- **Agent B**: `apps/`, `cli/`, `aitbc/constants.py`, `aitbc/log_utils/`, systemd config.

A short list of files (`aitbc/database/replica.py`, `aitbc/network/circuit_breaker.py`, `aitbc/agent_bridge/`, blockchain-node `sync.py`/`router.py`) requires sequencing between the two — see the Coordination Protocol in `AGENTS.md` before editing them. If you're working as one of these agents (or on their behalf), check `AGENTS.md`'s current in-flight release section first — it names the active version, what's done, and what's still open.

### Commit style

Conventional Commits (`type(scope): subject`), body explaining why not just what. Historical commits from the automated agent pipeline carry `Generated with [Devin]` + a `Co-Authored-By: Devin` trailer — don't add that trailer yourself unless replicating that pipeline.
