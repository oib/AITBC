# Contributing to AITBC

Thanks for considering a contribution. This guide covers how to set up a development environment, run the verification suite, and follow the project's conventions.

## Development setup

The project is tested on Python 3.13 and uses Poetry for dependency management.

```bash
# Clone
git clone https://github.com/oib/aitbc.git /opt/aitbc
cd /opt/aitbc

# Install dependencies
pip install poetry
poetry install

# Or use the existing venv if one is already provisioned
source ./venv/bin/activate
```

## Verification commands

Run these before committing:

```bash
# Lint (whole repo)
./venv/bin/python -m ruff check .

# Type check shared core
./venv/bin/python -m mypy --show-error-codes aitbc/

# Unit tests
./venv/bin/python -m pytest tests/unit -q

# Integration tests
./venv/bin/python -m pytest tests/integration -q

# coordinator-api tests
cd apps/coordinator-api && PYTHONPATH=src ../../venv/bin/python -m pytest tests -q -o addopts=""

# blockchain-node tests
cd apps/blockchain-node && PYTHONPATH=src ../../venv/bin/python -m pytest tests -q -o addopts=""
```

> If you see missing-plugin warnings, add `-o addopts=""` to skip the `pytest-rerunfailures`/`pytest-asyncio` extras.

## Project layout

- `aitbc/` — shared core library (logging, crypto, network, auth, rate limiting, queues, etc.)
- `apps/` — microservices: `coordinator-api`, `blockchain-node`, `exchange`, `marketplace`, `wallet`, `miner`, `edge`, `gpu`, `governance`, ...
- `cli/` — `aitbc_cli` command-line tool
- `packages/py/` — publishable Python packages
- `tests/` — `unit/`, `integration/`, `e2e/`, `coordinator/`
- `scripts/` — ops, deployment, monitoring, migration, security
- `docs/` — user-facing docs, reference, scenarios, and the release index
- `docs/releases/<version>/` — per-release changelogs and agent task assignments

## Code conventions

- **Python 3.13**, line length 127, `target-version = "py313"` in `pyproject.toml`.
- **Imports**: use absolute imports inside `aitbc/`, relative imports are fine inside a single app package.
- **ORM**: SQLModel for coordinator-api domain models; add `index=True` on columns used in `WHERE`/`ORDER BY`; composite indexes go in `__table_args__`.
- **Config**: use `pydantic_settings.BaseSettings`. New services should subclass `ServiceSettings`/`DatabaseConfig` from the shared core rather than redefining them.
- **Logging**: use `aitbc.aitbc_logging` (`configure_logging`, `get_logger`) everywhere. Do not set up logging from scratch.
- **Constants**: `aitbc/constants.py` resolves `REPO_DIR` from `AITBC_REPO_DIR` (defaults to `/opt/aitbc`).
- **DB init**: services call `SQLModel.metadata.create_all` (or `Base.metadata.create_all`). For existing databases, add an Alembic migration under the relevant app with `if_not_exists=True`.
- **Auth**: use `aitbc.auth` for JWT/API-key auth, RBAC, and middleware. Do not introduce new hardcoded API keys.
- **Tests**: one small runnable check for non-trivial logic; full tests for user-facing paths. Target 85% coverage for new code.

## Commit style

Use [Conventional Commits](https://www.conventionalcommits.org/):

```
type(scope): short subject

Body explaining why, not just what.

Generated with [Devin](https://devin.ai)
Co-Authored-By: Devin <158243242+devin-ai-integration[bot]@users.noreply.github.com>
```

Examples:

- `feat(auth): add X-Api-Key support to AuthMiddleware`
- `fix(blockchain): handle missing keystore password gracefully`
- `docs(readme): update hero section and status matrix`

## Release planning

This repo uses an internal agent-release model documented in `AGENTS.md`:

- **Agent A** owns `aitbc/` shared core (type safety, auth, rate limiting, etc.).
- **Agent B** owns `apps/`, `cli/`, `aitbc/constants.py`, `aitbc/log_utils/`, and systemd config.
- Shared files (`aitbc/database/replica.py`, `aitbc/network/circuit_breaker.py`, `aitbc/agent_bridge/`, blockchain-node `sync.py`/`router.py`) require coordination.

The current in-flight plan is in `docs/releases/v0.10.16/AGENTS.md`. If your change touches a file outside the current agent's boundary, declare intent in the release's `AGENTS.md` and follow the coordination protocol.

## Pull request process

1. Open a PR against `main`.
2. Ensure `ruff check .` and the relevant test commands pass.
3. Include a concise description and test plan.
4. Reference the release plan if this is part of an in-flight release.

## Questions?

- Read the [Master Index](../../MASTER_INDEX.md) for documentation navigation.
- See [docs/releases/STATUS.md](../../releases/STATUS.md) for what's currently in progress.
- For support, visit https://devin.ai/support.
