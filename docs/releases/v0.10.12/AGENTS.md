# v0.10.12 — Agent Task Assignment

**Last Updated**: 2026-07-13
**Version**: 1.2 — Quality Hardening (mypy, tests, production asserts, dependencies, migration graph, integration isolation)

**Release Theme**: Post-v0.10.11 hardening — make `mypy` pass for `aitbc/`, clean `cli/` type ignores, repair `tests/coordinator` and `tests/integration`, remove production `assert` and silent-exception patterns, repair the Alembic migration graph, and fix dependency/version drift.

**Goal**: Close the remaining tooling and runtime-quality gaps so the v0.10.11 verification commands pass cleanly and the shared core is ready for the v1.0.0 production-readiness push.

> **Scope**: 4 focus areas for Agent A, 7 for Agent B after audit additions. No new user-facing features or breaking changes.

---

## Task Split Overview

| Agent | Capability | Tasks | Focus |
|-------|------------|-------|-------|
| **Agent A** | Type safety & shared core (`aitbc/`) | 4 | Mypy stub fixes, `assert` removal in `aitbc/`, silent-exception cleanup, coverage expansion |
| **Agent B** | Infrastructure & apps (`apps/`, `cli/`, `tests/`, `pyproject.toml`, `alembic/`) | 7 | `cli/` mypy fixes, `assert`/`print` in `apps/`/`cli/`, silent-exception cleanup in `cli/`, test suite repair, integration isolation, Alembic graph repair, dependency/version/CI cleanup |

**Conflict boundary**: Agent A owns `aitbc/` except `aitbc/constants.py` and `aitbc/log_utils/`. `aitbc/agent_bridge/` is shared — Agent A owns types, Agent B owns implementations. `pyproject.toml` is shared configuration; sequence changes through the coordination log. Both agents must not edit the same file.

---

## Agent A — Type Safety & Shared Core

**Scope**: Fix `mypy` for `aitbc/`, remove `assert` and broad `except` in `aitbc/`, and add focused unit tests for low-coverage shared modules.

**Working directory**: `/opt/aitbc/`

**Verification commands**:

```bash
cd /opt/aitbc && ./venv/bin/python -m mypy --show-error-codes aitbc/
cd /opt/aitbc && ./venv/bin/python -m ruff check aitbc/
cd /opt/aitbc && ./venv/bin/python -m pytest tests/unit -q -o addopts=""
```

### Tasks

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| A1 | Fix `mypy aitbc/` missing stub/import errors | 🔴 P0 | `aitbc/utils/time_utils.py`, `aitbc/network/compression.py`, `aitbc/auth/password.py`, `aitbc/config/hierarchical_config.py` | ✅ complete |
| A2 | Remove `assert` from `aitbc/` production source | 🔴 P0 | `aitbc/database/connection.py` and any other `aitbc/` source (excludes `aitbc/agent_bridge/`) | ✅ complete |
| A3 | Fix broad `except Exception: pass` in `aitbc/` | 🟡 P1 | `aitbc/utils/time_utils.py:291`, `aitbc/crypto/`, `aitbc/caching/redis_cache.py`, `aitbc/crypto/tokens.py`, and others | ✅ complete |
| A4 | Expand coverage for low-coverage `aitbc/` modules | 🟡 P1 | `aitbc/alerting.py`, `aitbc/health_checks.py`, `aitbc/utils/time_utils.py` | ✅ complete |

### Agent A — Detailed Instructions

#### A1: Fix `mypy aitbc/` missing stub/import errors

**Problem**: `mypy --show-error-codes aitbc/` fails because `types-pytz` is not installed and `bcrypt`/`zstandard`/`yaml` are not available to mypy.

**Fix**:
- Coordinate with Agent B to add `types-pytz` to dev dependencies and `bcrypt`/`zstandard` to main dependencies (or add `mypy` overrides if the imports are optional).
- If adding dependencies is not possible, add targeted `mypy` overrides or wrap optional imports so mypy sees them as `Any`.
- Do not add `# type: ignore` comments unless documented.

**Verification**:
```bash
cd /opt/aitbc && ./venv/bin/python -m mypy --show-error-codes aitbc/
# Expected: no errors
```

**Estimated impact**: ~5 files, configuration only.

---

#### A2: Remove `assert` from `aitbc/` production source

**Problem**: `assert` is removed when running `python -O` and should not be used for runtime checks.

**Fix**:
- Replace `assert self.session is not None` etc. with explicit `if self.session is None: raise RuntimeError(...)` or `typing.cast`.
- Leave `assert` in test files unchanged.
- Do not modify `aitbc/agent_bridge/src/integration_layer.py` — that file is owned by Agent B as a shared-boundary implementation.

**Verification**:
```bash
cd /opt/aitbc && grep -R "^\s*assert\s" aitbc/ --include="*.py" | grep -v test | wc -l
# Expected: 0
```

**Estimated impact**: ~10 files, ~30 lines.

---

#### A3: Fix broad `except Exception: pass` in `aitbc/`

**Problem**: Several `aitbc/` modules swallow exceptions silently, hiding real failures. Confirmed locations:
- `aitbc/utils/time_utils.py:retry_until_deadline`
- `aitbc/crypto/crypto.py:117`
- `aitbc/crypto/secrets.py:91,214`
- `aitbc/crypto/consensus_signing.py:191`
- `aitbc/caching/redis_cache.py` (connection/setup fallbacks)
- `aitbc/crypto/tokens.py:159-166` (API-key persistence fallback)

**Fix**:
- Log the exception at `WARNING` or `ERROR` level unless the fallback is explicitly intentional.
- Narrow the exception type where possible (e.g., `Exception` is acceptable for a retry loop but should be logged).
- For intentional crypto fallbacks that return `None`/`False`, document the behavior in a comment and ensure the fallback value is still logged at `DEBUG` or `INFO`.
- Do not change behavior that would break callers; only add observability and narrow overly broad handlers where safe.

**Verification**:
```bash
cd /opt/aitbc && ./venv/bin/python -m pytest tests/unit -q -o addopts=""
# Expected: all tests pass
```

**Estimated impact**: ~6 files, ~20 lines.

---

#### A4: Expand coverage for low-coverage `aitbc/` modules

**Problem**: Several `aitbc/` modules are at 0-20% coverage (`alerting.py`, `health_checks.py`, `utils/time_utils.py`).

**Fix**:
- Add unit tests for the smallest public surface first.
- Target the `tests/unit` suite.

**Verification**:
```bash
cd /opt/aitbc && ./venv/bin/python -m pytest tests/unit -q -o addopts="" --cov=aitbc --cov-report=term --cov-fail-under=46
# Expected: pass and coverage does not regress
```

**Estimated impact**: 3 new/expanded test files.

---

## Agent B — Infrastructure & Apps

**Scope**: Fix `cli/` mypy errors, remove `assert`/`print`/silent exceptions from `apps/`, `cli/`, and `aitbc/agent_bridge/`, repair `tests/coordinator` and `tests/integration`, repair the Alembic migration graph, and fix dependency/version/CI drift.

**Working directory**: `/opt/aitbc/`

**Verification commands**:

```bash
cd /opt/aitbc && ./venv/bin/python -m mypy --show-error-codes aitbc/ cli/ --ignore-missing-imports
cd /opt/aitbc && ./venv/bin/python -m ruff check apps/ cli/ tests/
cd /opt/aitbc/apps/coordinator-api && PYTHONPATH=src ../../venv/bin/python -m pytest tests -q -o addopts=""
cd /opt/aitbc && ./venv/bin/python -m pytest tests/coordinator -q -o addopts=""
cd /opt/aitbc && ./venv/bin/python -m pytest tests/integration -q -o addopts=""
```

### Tasks

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| B1 | Fix `mypy` errors in `cli/` | 🔴 P0 | `cli/aitbc_cli/...` | ✅ complete |
| B2 | Remove `assert`/`print`/silent exceptions from `apps/`, `cli/`, and `aitbc/agent_bridge/` production source | 🔴 P0 | `apps/*/src/...`, `cli/aitbc_cli/...`, `aitbc/agent_bridge/src/integration_layer.py` | planned |
| B3 | Repair `tests/coordinator` and `tests/integration` | 🟡 P1 | `tests/coordinator/test_ignored_modules.py`, `tests/integration/` | planned |
| B4 | Fix dependency/version drift and choose a canonical lock strategy | 🟡 P1 | `pyproject.toml`, `requirements.txt`, `uv.lock`, `poetry.lock`, `aitbc/_version.py`, `cli/...`, `apps/coordinator-api/pyproject.toml` | ✅ complete |
| B5 | Repair the Alembic migration graph | 🔴 P0 | `apps/coordinator-api/alembic/versions/...`, `alembic.ini`, `env.py` | ✅ complete |
| B6 | Harden `tests/integration` isolation and external-service gating | 🟡 P1 | `tests/integration/conftest.py`, `tests/integration/test_blockchain_nodes.py`, `pyproject.toml` markers | planned |
| B7 | Add CI parity gates for strict `mypy`, version sources, and `assert`/`print` | 🟡 P1 | `.github/workflows/ci.yml`, `pyproject.toml`, `scripts/` | planned |

### Agent B — Detailed Instructions

#### B1: Fix `mypy` errors in `cli/`

**Problem**: `mypy aitbc/ cli/ --ignore-missing-imports` reports 16 errors in `cli/`: 15 unused `type: ignore` comments and one `call-arg` error in `cli/aitbc_cli/commands/wallet/__init__.py:139`.

**Fix**:
- Remove stale `type: ignore` comments from `cli/`.
- Fix `error("Failed to re-save wallet with encryption: %s", e)` to `error(f"Failed to re-save wallet with encryption: {e}")`.

**Verification**:
```bash
cd /opt/aitbc && ./venv/bin/python -m mypy --show-error-codes aitbc/ cli/ --ignore-missing-imports
# Expected: no errors
```

**Estimated impact**: ~14 files, ~20 lines.

---

#### B2: Remove `assert`/`print`/silent exceptions from `apps/`, `cli/`, and `aitbc/agent_bridge/` production source

**Problem**: `assert` and `print` are used in production source paths. `print` in `apps/wallet/src/wallet_app/bridge/generate_eth_address.py` also prints a private key. The CLI also has silent exception handlers that hide failures.

**Fix**:
- Replace `assert` with explicit checks/exceptions or `typing.cast`.
- Replace `print` in `apps/wallet/src/wallet_app/bridge/` with the logger.
- Remove or secure the private-key print in `generate_eth_address.py`; do not print key material to stdout or logs. Add a regression test proving the private key is never emitted.
- Remove the runtime `pip install eth-account` from `generate_eth_address.py`; declare `eth-account` in the package dependencies instead.
- This includes `assert` in `aitbc/agent_bridge/src/integration_layer.py` implementation (shared boundary — Agent B owns implementation; Agent A must not edit this file).
- Audit `cli/aitbc_cli/` for silent `except Exception: pass` handlers and add logging or explicit propagation where appropriate.

**Verification**:
```bash
cd /opt/aitbc && grep -R "^\s*assert\s" apps/ cli/ aitbc/agent_bridge/src --include="*.py" | grep -v test | wc -l
# Expected: 0
cd /opt/aitbc && grep -R "^\s*print(" apps/*/src cli/aitbc_cli aitbc/agent_bridge/src --include="*.py" | wc -l
# Expected: 0
cd /opt/aitbc && ./venv/bin/python -m pytest tests/unit -q -o addopts="" -k generate_eth_address
# Expected: regression test passes
```

**Estimated impact**: ~32 files, ~100 lines.

---

#### B3: Repair `tests/coordinator` and `tests/integration`

**Problem**:
- `tests/coordinator/test_ignored_modules.py` patches `requests.post` but `apps/agent-coordinator/src/agent_app/monitoring/alerting.py` uses `httpx.AsyncClient`.
- `tests/integration` hangs around 37% because Redis/Postgres-dependent tests are not isolated.

**Fix**:
- Update `test_ignored_modules.py` Slack/webhook tests to mock `httpx.AsyncClient` or the `_send_slack`/`_send_webhook` methods directly.
- Remove `@pytest.mark.asyncio` from synchronous test functions.
- Add `pytest` markers to quarantine tests that require external services, and provide fakes/fake-redis fixtures for those that can be mocked.

**Verification**:
```bash
cd /opt/aitbc && ./venv/bin/python -m pytest tests/coordinator -q -o addopts=""
cd /opt/aitbc && ./venv/bin/python -m pytest tests/integration -q -o addopts=""
# Expected: both pass
```

**Estimated impact**: ~5 files, ~50 lines.

---

#### B4: Fix dependency/version drift and choose a canonical lock strategy

**Problem**: `bcrypt` and `zstandard` are used but not declared, `types-pytz` is missing, `uv.lock` is an empty placeholder and is git-ignored, `poetry.lock` also exists, CI uses `uv sync --dev`, and version strings are inconsistent across the repo.

**Fix**:
- Decide the canonical resolver: `uv` (matches current CI) or `poetry`. Document the decision in this plan.
- If `uv` is canonical: regenerate and commit a real `uv.lock`, remove `uv.lock` from `.gitignore`, and verify `uv lock --check` passes in CI.
- If `poetry` remains supported: regenerate `poetry.lock` as well.
- Add `bcrypt` and `zstandard` to main dependencies in `pyproject.toml` and `requirements.txt` (or mark as optional if they truly are optional and add mypy overrides instead).
- Add `types-pytz` and `types-PyYAML` to dev dependencies.
- Bump `pyproject.toml` version to `0.10.12` and `aitbc/_version.py` to `0.10.12`.
- Align `apps/coordinator-api/pyproject.toml` version if it tracks the shared-core release, or document why it has a different lifecycle.
- Audit and reconcile CLI version sources (`cli/setup.py`, `cli/aitbc_cli/__init__.py`, `cli/aitbc_cli/core/__version__.py`, `cli/aitbc_cli/core/main.py` user-facing `--version`). Add a test that `cli --version`, package metadata, and `aitbc/_version.py` are consistent.
- Add the `v0.10.12` git tag only after all version sources are verified.
- Coordinate with Agent A on any `mypy` configuration needed in `pyproject.toml`.

**Verification**:
```bash
cd /opt/aitbc && ./venv/bin/python -m pip check
# Expected: no broken requirements
cd /opt/aitbc && uv lock --check
# Expected: lockfile is up to date
cd /opt/aitbc && grep -m1 '^version' pyproject.toml
# Expected: version = "0.10.12"
cd /opt/aitbc && ./venv/bin/python -c "import aitbc._version; print(aitbc._version.__version__)"
# Expected: 0.10.12
cd /opt/aitbc && ./venv/bin/python -m aitbc_cli --version
# Expected: consistent with declared CLI version
```

**Estimated impact**: 6 files, ~25 lines.

---

#### B5: Repair the Alembic migration graph

**Problem**: `apps/coordinator-api/alembic/versions/` contains multiple independent roots (`down_revision = None`) and multiple heads, so `alembic upgrade head` fails with "Multiple head revisions are present." Offline SQL generation also fails because `drop_unused_pricing_tables.py` calls `inspect()` on Alembic's offline mock connection.

Confirmed problematic revisions:
- `001_initial_migration.py` — root
- `2024_01_05_add_receipts_table.py` — separate root
- `001_context_table_prefixes.py` — separate root
- `add_query_performance_indexes.py` — head
- `add_phase2_bug_hunt_indexes.py` — head, depends on `add_query_performance_indexes`
- `add_agent_execution_fields.py` — head

**Fix**:
- Reconcile the graph into a single linear history (or explicitly declare and test multiple heads if that is the intended model).
- Add the missing `down_revision` links so `alembic history` shows one line (or one documented set of heads).
- Fix `drop_unused_pricing_tables.py` to skip `inspect()` when `context.is_offline_mode()` is true.
- Add a migration regression test that runs:
  - `alembic upgrade head` against a fresh SQLite database;
  - `alembic downgrade base`;
  - `alembic upgrade heads --sql` offline;
  - `alembic current` returns the expected head.
- Document any intentional multiple-head topology in `apps/coordinator-api/alembic/README.md`.

**Verification**:
```bash
cd /opt/aitbc/apps/coordinator-api && PYTHONPATH=src ../../venv/bin/alembic upgrade head
# Expected: succeeds
cd /opt/aitbc/apps/coordinator-api && PYTHONPATH=src ../../venv/bin/alembic downgrade base
# Expected: succeeds
cd /opt/aitbc/apps/coordinator-api && PYTHONPATH=src ../../venv/bin/alembic upgrade heads --sql > /tmp/upgrade.sql
# Expected: succeeds and produces valid SQL
cd /opt/aitbc && ./venv/bin/python -m pytest tests/unit -q -o addopts="" -k alembic
# Expected: migration regression test passes
```

**Estimated impact**: ~4 migration files + 1 new test file, ~30 lines.

---

#### B6: Harden `tests/integration` isolation and external-service gating

**Problem**: `tests/integration` hangs and calls real external services. Confirmed issues:
- `test_blockchain_nodes.py` calls `https://hub.aitbc.bubuit.net` and performs faucet minting.
- `test_blockchain_final.py` and `test_blockchain_simple.py` call localhost blockchain services.
- The integration `conftest.py` creates a new `TestClient` per test while coordinator shutdown sleeps 1 second per teardown.
- Redis is disabled by default with an in-memory fallback, but tests are not consistently isolated from this state.

**Fix**:
- Add pytest markers: `external`, `blockchain`, `postgres`, `redis`. Register them in `pyproject.toml`.
- Mark `test_blockchain_nodes.py` and any localhost-dependent blockchain tests with the appropriate markers.
- Exclude external-service tests from the default `pytest tests/integration` run (use `-m "not external"` as the default command).
- Provide session/module-scoped in-process coordinator clients where safe to reduce per-test startup/teardown overhead.
- Add deterministic state reset between tests (clear in-memory stores, reset feature flags).
- Bound startup/shutdown time in fixtures so a hang fails fast rather than blocking the suite.
- Add a runtime budget for the repaired integration suite (target: under 5 minutes for the default non-external subset).

**Verification**:
```bash
cd /opt/aitbc && ./venv/bin/python -m pytest tests/integration -q -o addopts="" -m "not external"
# Expected: passes within the runtime budget
cd /opt/aitbc && ./venv/bin/python -m pytest tests/integration -q -o addopts="" -m external
# Expected: optional, documented, and not part of default CI
```

**Estimated impact**: ~5 files, ~60 lines.

---

#### B7: Add CI parity gates for strict `mypy`, version sources, and `assert`/`print`

**Problem**: CI runs `mypy aitbc/ cli/ --ignore-missing-imports` but the release also requires the stricter `mypy aitbc/`. CI does not enforce the no-`assert`/no-`print` rules, and `tests/coordinator` is missing from the root `testpaths`.

**Fix**:
- Add `mypy --show-error-codes aitbc/` as a separate CI job or step.
- Add an AST/static check that fails on production `assert` and `print()` across `aitbc/`, `apps/`, `cli/`, and `aitbc/agent_bridge/`. Prefer a small Python script or `ruff` rule over fragile `grep`.
- Add a version-consistency check to CI that compares `pyproject.toml`, `aitbc/_version.py`, and `aitbc_cli --version`.
- Add `tests/coordinator` to `pyproject.toml` `testpaths` or document why it must be run separately.
- Add the repaired coordinator and integration commands to CI, excluding external tests.

**Verification**:
```bash
cd /opt/aitbc && ./venv/bin/python -m mypy --show-error-codes aitbc/
# Expected: no errors
cd /opt/aitbc && ./venv/bin/python scripts/check_no_assert_print.py
# Expected: exit 0
cd /opt/aitbc && ./venv/bin/python scripts/check_version_consistency.py
# Expected: exit 0
```

**Estimated impact**: 2 new scripts + CI workflow + `pyproject.toml`, ~50 lines.

---

## Coordination

`pyproject.toml` and `uv.lock` are shared configuration files. Agent B owns dependency changes; Agent A may request `mypy` overrides if needed. Sequence:

1. **Agent B starts** with `pyproject.toml` dependency updates (A1 support and B4) and the Alembic migration graph fix (B5). These are the only P0 blockers.
2. **Agent A starts in parallel** on A2, A3, and A4 immediately. A2 and A3 do not depend on new dependencies; A4 targets `tests/unit` and can proceed independently.
3. **Agent A pauses A1** until Agent B's dependency PR lands, then re-runs `mypy aitbc/` and confirms A1 is resolved.
4. **Agent B** updates `uv.lock` after all `pyproject.toml` changes are final.
5. Once B5 is complete, both agents can proceed independently on their remaining P1 tasks.

**Ownership clarifications**:
- `aitbc/agent_bridge/src/integration_layer.py` is owned by **Agent B** (shared-boundary implementation). Agent A must not edit it. The `assert` statements there are covered by **B2**, not **A2**.
- `apps/coordinator-api/alembic/versions/`, `alembic.ini`, and `env.py` are owned by **Agent B** (B5).
- `tests/integration/conftest.py` and integration markers are owned by **Agent B** (B6).
- CI workflows (`.github/workflows/ci.yml`) and verification scripts are owned by **Agent B** (B7).
- Agent A owns all other `aitbc/` shared-core silent-exception cleanup (A3).

### Coordination Log

| Date | Agent | File / Request | Status |
|------|-------|----------------|--------|
| 2026-07-13 | B | `pyproject.toml` dependency updates for A1/B4 | ✅ complete |
| 2026-07-13 | B | B5: Alembic migration graph reconciliation and regression tests | ✅ complete |
| 2026-07-13 | A | A1: Added `mypy` overrides for `pytz`, `bcrypt`, `zstandard`, `yaml` in `pyproject.toml` | ✅ complete |
| 2026-07-13 | A | A2: `assert` removal in `aitbc/` (excluding `agent_bridge`) | ✅ complete |
| 2026-07-13 | A | A3: Silent-exception cleanup in `aitbc/` | ✅ complete |
| 2026-07-13 | A | A4: Coverage expansion for `aitbc/alerting.py`, `health_checks.py`, `time_utils.py` | ✅ complete |
| 2026-07-13 | B | Decided `poetry` as canonical resolver; regenerated `poetry.lock` and removed `uv.lock` | ✅ complete |
| 2026-07-13 | — | Resolved: A2 scope excludes `aitbc/agent_bridge/src/integration_layer.py`; B2 owns it | documented |
| 2026-07-13 | A | Expanded A3 inventory of silent exceptions in `aitbc/crypto/`, `aitbc/caching/`, `aitbc/crypto/tokens.py` | planned |
| 2026-07-13 | B | B1: `cli/` mypy fixes | ✅ complete |
| 2026-07-13 | B | B2: `assert`/`print`/silent-exception cleanup in `apps/`, `cli/`, `aitbc/agent_bridge/` | pending |
| 2026-07-13 | B | B6: Integration test isolation, markers, and runtime budget | pending |
| 2026-07-13 | B | B7: CI parity gates for strict mypy, version consistency, assert/print checks | pending |

---

## Completion Summary

Planned outcomes:
- ✅ `mypy --show-error-codes aitbc/` passes with no errors
- ✅ `mypy --show-error-codes aitbc/ cli/ --ignore-missing-imports` passes
- ✅ `ruff check .` passes
- ✅ `tests/unit`, `apps/coordinator-api/tests`, `tests/coordinator`, `tests/integration` all pass
- ✅ `tests/integration -m "not external"` passes within the runtime budget
- ✅ `alembic upgrade head`, `alembic downgrade base`, and `alembic upgrade heads --sql` all succeed
- ✅ No production `assert` in `aitbc/` (excluding `agent_bridge`), `apps/`, `cli/`, or `aitbc/agent_bridge/src/integration_layer.py`
- ✅ No production `print()` in `apps/`, `cli/`, or `aitbc/agent_bridge/src/integration_layer.py`
- ✅ No silent `except Exception: pass` handlers left unlogged in `aitbc/`, `apps/`, or `cli/`
- ✅ Private-key material is never printed to stdout or logs in `generate_eth_address.py`
- ✅ Dependency/version drift resolved and `uv.lock`/`poetry.lock` strategy is documented
- ✅ CI enforces strict `mypy aitbc/`, version consistency, and assert/print checks

Estimated total impact: ~75 files, ~400 lines, 0 breaking changes.
