# v0.10.18 — Update Deployment Stabilization

**Last Updated**: 2026-07-22
**Version**: 1.1 — Complete ✅

**Release Theme**: Fix the post-v0.10.17 update path: resolve the coordinator-api
`market_metrics` migration conflict, restore the missing wallet keystore package,
harden `update.sh` and `health_check.sh`, and switch dependency installation
to a Poetry-based, profile-aware export so GPU/FHE/ML packages are optional.

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

### B5: Switch dependency sync to Poetry (P2) ✅

- File: `pyproject.toml`
  - Move `tenseal`, `pycuda`, `torch`, `torchvision`, `pillow`, and
    `opencv-python` to `[tool.poetry.extras]` (`gpu`, `fhe`, `ml`).
  - Set `tool.poetry.package-mode = false`.
- File: `poetry.lock`
  - Regenerated from the updated `pyproject.toml`.
- File: `scripts/deployment/install-profiles.sh` (new)
  - Exports the right `requirements-$PROFILE.txt` from `poetry.lock` for the
    detected hardware/role profile and installs it into `venv`.
- File: `scripts/deployment/update.sh`
  - Calls `install-profiles.sh` (no more missing-script warning).
  - Restarts all `aitbc-*` services correctly after detecting running units.

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

### B6: Reconcile coordinator-api schema drift (P1) ✅

- File: `apps/coordinator-api/alembic/env.py`
  - Add `render_as_batch=True` so SQLite column alterations are emitted as
    `batch_alter_table` blocks.
- File: `apps/coordinator-api/alembic/versions/236edfbd9728_reconcile_schema_drift_v0_10_18.py` (new)
  - Drop unused empty legacy tables (`fusion_models`, `edge_gpu_metrics`,
    `consumer_gpu_profiles`, `rl_configurations`, `multi_chain_transaction`,
    `auction_config`).
  - Add missing columns/indexes and align `Numeric`, `JSON`, `Enum`, and
    `String` types so `alembic check` reports no drift.

## Release Gate

- [x] `market_metrics` migration conflict resolved (`alembic upgrade head` passes).
- [x] `wallet_app.keystore` restored and `aitbc-wallet` starts cleanly.
- [x] `update.sh` runs without `--no-migrate`.
- [x] `health_check.sh all` passes.
- [x] `alembic check` reports no new upgrade operations for coordinator-api.
- [x] Version bumped to `0.10.18` in `pyproject.toml` and `aitbc/_version.py`.

*Generated with [Devin](https://devin.ai)*
