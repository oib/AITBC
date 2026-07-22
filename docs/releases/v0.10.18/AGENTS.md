# v0.10.18 — Update Deployment Stabilization

**Last Updated**: 2026-07-22
**Version**: 1.0 — In Progress

**Release Theme**: Fix the post-v0.10.17 update path: resolve the coordinator-api
`market_metrics` migration conflict, restore the missing wallet keystore package,
harden `update.sh` and `health_check.sh`, and prepare to switch dependency
installation from `pip` to `poetry`.

**Prerequisites**: v0.10.17 complete.

---

## Task Split Overview

| Agent | Files | Tasks |
|---|---|---|
| **Agent B** | `apps/coordinator-api/`, `apps/wallet/`, `scripts/deployment/`, `scripts/monitoring/`, `.gitignore`, `pyproject.toml` | Migration fix, keystore restore, `update.sh`/`health_check.sh` fixes, optional `poetry` switch |

---

## Agent B — Applications & Operations

### B1: Resolve `market_metrics` table collision (P0) ✅

- File: `apps/coordinator-api/src/coordinator_api/contexts/analytics/domain/analytics.py`
  - Rename `MarketMetric.__tablename__` to `analytics_market_metrics`.
- File: `apps/coordinator-api/alembic/versions/add_query_performance_indexes.py`
  - Update `recorded_at` index to target `analytics_market_metrics`.
  - Point `down_revision` to the new migration `7350cc615a22`.
- File: `apps/coordinator-api/alembic/versions/7350cc615a22_rename_analytics_market_metrics.py` (new)
  - Inspect DB and either rename an existing analytics `market_metrics` table
    or create `analytics_market_metrics` from scratch.

### B2: Restore `wallet_app.keystore` package (P0) ✅

- File: `apps/wallet/src/wallet_app/keystore/__init__.py` (new)
- File: `apps/wallet/src/wallet_app/keystore/persistent_service.py` (new)
- File: `apps/wallet/src/wallet_app/api_jsonrpc.py`
  - Switch import to `PersistentKeystoreService`.
- File: `.gitignore`
  - Change `keystore/` to `/keystore/` so source keystore packages are tracked.

### B3: Harden `update.sh` (P1) ✅

- File: `scripts/deployment/update.sh`
  - Include `/opt/aitbc` and `packages/py/*/src` in Alembic `PYTHONPATH`.
  - Skip Alembic migrations for services not linked for the current node role.

### B4: Fix `health_check.sh` (P1) ✅

- File: `scripts/monitoring/health_check.sh`
  - Marketplace endpoint: `http://localhost:8102/health`.
  - Exchange service key: `aitbc-exchange`.
  - System memory parsing: handle localized `free` output and guard against
    division by zero.

### B5: Switch dependency sync to Poetry (P2) ⏳

- File: `pyproject.toml`
  - Move `tenseal`, `pycuda`, `nvidia-*`, `torch`, `torchvision`, and other
    optional GPU/FHE/ML packages to `[tool.poetry.extras]`.
- File: `scripts/deployment/update.sh`
  - Install `poetry` and use `poetry install --locked --no-dev` (with extras
    selected by role/hardware profile) instead of `pip install -r requirements.txt`.
- File: `poetry.lock`
  - Regenerate after `pyproject.toml` changes.

---

## Verification Commands

```bash
cd /opt/aitbc
./venv/bin/python -m ruff check .
./venv/bin/python -m mypy --show-error-codes aitbc/
./venv/bin/python -m pytest tests/unit -q -o addopts=""

# Coordinator-api migrations
cd apps/coordinator-api
PYTHONPATH="/opt/aitbc:src:$(ls -d /opt/aitbc/packages/py/*/src | tr '\n' ':')" \
  /opt/aitbc/venv/bin/alembic upgrade head
cd /opt/aitbc

# Full health check
/opt/aitbc/scripts/monitoring/health_check.sh all
```

## Coordination Protocol

- Agent B owns all files in this release.
- No Agent A shared files are touched.

---

## Release Gate

- [ ] `market_metrics` migration conflict resolved (`alembic upgrade head` passes).
- [ ] `wallet_app.keystore` restored and `aitbc-wallet` starts cleanly.
- [ ] `update.sh` runs without `--no-migrate`.
- [ ] `health_check.sh all` passes.
- [ ] Version bumped to `0.10.18` in `pyproject.toml` and `aitbc/_version.py`.

*Generated with [Devin](https://devin.ai)*
