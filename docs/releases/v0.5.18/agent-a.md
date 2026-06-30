# v0.5.18 Test Suite Repair — Agent A Tasks

**Last Updated**: 2026-06-30
**Version**: 1.0

**Agent**: Agent A (Shared Test Config & Infrastructure)

**Scope**: pytest markers, default timeout, reusable auto-skip fixtures, and the final `testpaths` inclusion. No test-logic changes.

**Verification command**:
```bash
cd /opt/aitbc && ./venv/bin/python -m pytest apps/blockchain-node/tests/ --collect-only -q 2>&1 | tail -5
```

---

## Tasks

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| A1 | Register `requires_redis`, `requires_postgres`, `requires_genesis` markers + add default `timeout` to pytest config. | 🔴 P0 (blocks B) | `pyproject.toml` | ✅ DONE |
| A2 | Add shared auto-skip fixtures/hooks so `requires_redis`/`requires_postgres`/`requires_genesis` tests skip when the resource is unreachable. | 🔴 P0 (blocks B) | `apps/blockchain-node/tests/conftest.py` | ✅ DONE |
| A3 | **(LAST)** Add `apps/blockchain-node/tests` to `testpaths` once B's suite is green. | High | `pyproject.toml` | ✅ DONE |

---

## A1: Register markers + default timeout

- In `pyproject.toml` `[tool.pytest.ini_options]`:
  - Append to `markers`:
    ```toml
    "requires_redis: test needs a reachable Redis instance (auto-skipped if absent)",
    "requires_postgres: test needs a reachable PostgreSQL instance (auto-skipped if absent)",
    "requires_genesis: test needs an on-disk genesis file fixture (auto-skipped if absent)",
    ```
  - Add `timeout = 60` (seconds). `pytest-timeout` is already installed. This prevents CI hangs.
- **Verify**: `pytest apps/blockchain-node/tests/ --collect-only -q` shows no "unknown marker" errors once B applies them.
- **Sequencing**: A1 must merge **before** B5 (B applies these markers). `--strict-markers` will error otherwise.

---

## A2: Auto-skip fixtures

- In `apps/blockchain-node/tests/conftest.py`, add a `pytest_collection_modifyitems` hook (or autouse fixtures) that:
  - For `requires_redis`: attempt a fast Redis connection (env `REDIS_URL`, short timeout). On failure → `pytest.skip("Redis not available")`.
  - For `requires_postgres`: attempt a fast Postgres connection (env `DATABASE_URL`/`MEMPOOL_DB_URL`). On failure → skip.
  - For `requires_genesis`: skip if the expected genesis path is absent (unless a fixture provides one).
- Keep probes cheap (≤1–2s, guarded by the A1 default `timeout`). Do **not** add `fakeredis` or any new dependency in this patch.
- **Verify**: In this no-infra sandbox, `pytest apps/blockchain-node/tests/ -m "requires_redis or requires_postgres"` reports skips, not failures (after B5 tags the tests).

---

## A3: Add to testpaths (LAST)

- After B1–B6 are green, add `"apps/blockchain-node/tests"` to `testpaths` in `pyproject.toml`.
- **Do not do this earlier** — it would turn the default `pytest` run red while B is mid-flight.
- **Verify**: `cd /opt/aitbc && ./venv/bin/python -m pytest -q` collects the blockchain-node suite with 0 failed / 0 errors (infra tests skipped).

---

## Related Topics

- [Overview](./overview.md) - Release overview and status baseline
- [Agent B Tasks](./agent-b.md) - Blockchain-node test fixes implementation details

---

**Documentation Version**: 1.0
**Last Updated**: 2026-06-30
**Release**: v0.5.18 — Test Suite Repair
**Agent**: Agent A (Shared Test Config & Infrastructure)
