# v0.10.10 — Agent Task Assignment

**Last Updated**: 2026-07-06
**Version**: 1.0 — Code Quality & Testing Roadmap

**Release Theme**: Code Quality & Testing Roadmap — Expand mypy coverage, raise the coverage gate, add property-based testing, add performance regression tests, pin dependencies, add a local dev script, and add integration fixtures.

**Goal**: Shift from feature/dead-code work to the testing and type-safety foundations that v1.0.0 production readiness depends on.

> **Scope**: 8 tasks across 2 agents. (1) Verify v0.10.9 completion, (2) expand mypy coverage by removing `aitbc/` exclusions, (3) add property-based tests, (4) pin dependencies, (5) add local dev script, (6) raise coverage gate, (7) add performance regression tests, (8) add integration fixtures.

> **Prerequisites**: [v0.10.9](../v0.10.9/change.log) (✅ complete — dead code elimination & status drift cleanup).

> **Risk**: Medium. mypy expansion can surface a large error count; mitigated by incremental exclusion removal and per-file `# mypy: ignore-errors` as a temporary scaffold. Coverage gate raises may require backfilling tests. Performance baselines must be calibrated to the CI runner to avoid flakiness.

---

## Task Split Overview

| Agent | Capability | Tasks | Focus |
|-------|------------|-------|-------|
| **Agent A** | SWE 1.6 (fast mechanical tasks) | 3 items | v0.10.9 verification, mypy coverage expansion, property-based tests |
| **Agent B** | GLM 5.2 (complex tasks) | 5 items | Dependency pinning, local dev script, coverage gate, perf regression tests, integration fixtures |

**Conflict boundary**: Agent A owns `aitbc/` type annotations and `tests/unit` property-based tests. Agent B owns `pyproject.toml` config (coverage gate, dep pins), `scripts/dev/`, `tests/perf/`, and `tests/integration` fixtures. No overlap on `pyproject.toml` — Agent B makes all config edits; Agent A coordinates any mypy exclude changes through Agent B.

---

## Agent A — Type Safety & Shared Core (SWE 1.6)

**Scope**: Verify v0.10.9 is complete, expand mypy coverage by removing `aitbc/` exclusions and fixing surfaced errors, and add property-based tests for edge-case-heavy modules.

**Working directory**: `/opt/aitbc/`

**Verification command**:
```bash
cd /opt/aitbc && ./venv/bin/python -m mypy --show-error-codes aitbc/ && ./venv/bin/python -m ruff check . && ./venv/bin/python -m pytest tests/unit -q -o addopts=""
```

### Tasks

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| A1 | Verify v0.10.9 completion (clean tree, tests green) | 🔴 P0 | n/a (verification only) | ✅ |
| A2 | Expand mypy coverage — remove `aitbc/` exclusions, fix surfaced errors | 🔴 P0 | `pyproject.toml` (via Agent B), `aitbc/**`, `apps/**` | ✅ |
| A3 | Add property-based tests for crypto/decimal/settlement edge cases | 🟡 P1 | `tests/unit/test_property_crypto.py` | ✅ |

### Agent A — Detailed Instructions

#### A1: Verify v0.10.9 completion

**Problem**: Before starting quality work, confirm the prior release left a clean baseline.

**Verification**:
```bash
cd /opt/aitbc && ./venv/bin/python -m ruff check . && ./venv/bin/python -m mypy --show-error-codes aitbc/ && ./venv/bin/python -m pytest tests/unit -q -o addopts=""
```
All three must pass. If any fail, fix before proceeding to A2.

**Estimated impact**: Verification only — no code changes unless a regression is found.

---

#### A2: Expand mypy coverage — remove `aitbc/` exclusions, fix surfaced errors

**Problem**: `pyproject.toml` `[tool.mypy] exclude` still lists `aitbc/` paths. Three excluded dirs (`agent_compliance`, `agent_protocols`, `agent_trading`) no longer exist — deleted in v0.10.9. Phase 1 already fixed all 26 errors in the current scope (0 errors / 408 files). Phase 2 removes the stale exclusions and expands coverage to the rest of `aitbc/`.

**Fix**:

**Step 1**: Coordinate with Agent B to remove stale exclusions from `pyproject.toml`:
- `^aitbc/agent_compliance` — dir deleted in v0.10.9
- `^aitbc/agent_protocols` — dir deleted in v0.10.9
- `^aitbc/agent_trading` — dir deleted in v0.10.9
- Any other `aitbc/` exclusions that no longer apply

**Step 2**: Run mypy on the expanded scope:
```bash
cd /opt/aitbc && ./venv/bin/python -m mypy --show-error-codes aitbc/ 2>&1 | tee /tmp/mypy-expanded.log
```

**Step 3**: Fix surfaced errors module-by-module. For modules requiring extensive annotation work, add `# mypy: ignore-errors` at the top as a temporary scaffold (tracked for follow-up), per the existing gradual-typing approach documented in `pyproject.toml`.

**Step 4**: Verify zero errors:
```bash
cd /opt/aitbc && ./venv/bin/python -m mypy --show-error-codes aitbc/
# Expected: no errors
```

**Estimated impact**: Expanded type coverage across `aitbc/`. Line count depends on surfaced errors.

---

#### A3: Add property-based tests for crypto/decimal/settlement edge cases

**Problem**: Edge-case-heavy modules rely on example-based tests, which miss boundary conditions. `hypothesis` is already a production dependency.

**Fix**:

**Step 1**: Identify edge-case-heavy modules:
- `aitbc/crypto/` — signature verification, key derivation, hash functions
- Decimal math in pool-hub billing, trading pricing/bid engines (v0.10.4 migration)
- Atomic settlement state transitions (v0.9.0)

**Step 2**: Add property-based test files:
- `tests/unit/test_crypto_properties.py` — round-trip sign/verify, key derivation determinism, hash collision resistance (bounded)
- `tests/unit/test_decimal_properties.py` — Decimal arithmetic invariants (no float contamination, rounding consistency)
- `tests/unit/test_settlement_properties.py` — settlement state transition invariants (no invalid states reachable)

**Step 3**: Use `hypothesis.settings(max_examples=50, deadline=None)` to keep CI fast and avoid flaky deadline failures.

**Verification**:
```bash
cd /opt/aitbc && ./venv/bin/python -m pytest tests/unit/test_crypto_properties.py tests/unit/test_decimal_properties.py tests/unit/test_settlement_properties.py -q -o addopts=""
```

**Estimated impact**: 3 new test files, ~150 lines total. Catches edge cases example-based tests miss.

---

## Agent B — Infrastructure & Testing (GLM 5.2)

**Scope**: Pin all dependencies to exact installed versions, add a one-command local dev script, raise the coverage gate, add a performance regression test suite, and add reusable integration fixtures.

**Working directory**: `/opt/aitbc/`

**Verification command**:
```bash
cd /opt/aitbc && ./venv/bin/python -m mypy --show-error-codes aitbc/ && ./venv/bin/python -m ruff check . && ./venv/bin/python -m pytest tests/unit -q -o addopts=""
```

### Tasks

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| B1 | Pin all dependencies to exact installed versions | 🟢 P2 | `pyproject.toml` | ✅ |
| B2 | Add `scripts/dev/setup.sh` one-command setup + checks | 🟢 P2 | `scripts/dev/setup.sh` | ✅ |
| B3 | Raise coverage gate (`--cov-fail-under`) | 🟡 P1 | `pyproject.toml`, `scripts/dev/setup.sh` | ✅ |
| B4 | Add performance regression test suite (deterministic baselines, `perf` marker) | 🟡 P1 | `tests/perf/`, `pyproject.toml` (marker) | ✅ |
| B5 | Add reusable integration fixtures | 🟡 P1 | `tests/integration/conftest.py`, `tests/integration/fixtures/` | ✅ |

### Agent B — Detailed Instructions

#### B1: Pin all dependencies to exact installed versions ✅

**Problem**: Unbounded `>=` ranges auto-resolve to brand-new releases, exposing the project to supply-chain drift and unvetted updates.

**Fix (complete)**:
- Pinned all 50+ production dependencies to exact versions (e.g. `fastapi = "0.136.3"`, `cryptography = "48.0.0"`)
- Updated dev deps to match installed versions (`mypy = "2.1.0"`, `ruff = "0.15.17"`, `pytest-cov = "7.1.0"`)
- Replaced unbounded `>=` ranges with exact pins

**Verification**:
```bash
cd /opt/aitbc && grep -E '>=' pyproject.toml | grep -v extras | grep -v '^\s*#'
# Expected: no unbounded ranges in main/dev deps (extras may retain ranges intentionally)
```

**Estimated impact**: Supply-chain hardening. No runtime behavior change.

---

#### B2: Add `scripts/dev/setup.sh` one-command setup + checks ✅

**Problem**: New contributors need a documented, repeatable setup path.

**Fix (complete)**: Created `scripts/dev/setup.sh` — one-command setup that:
- Creates venv if needed
- Installs deps (via `uv sync` if available, else `pip install -e .[dev]`)
- Installs pre-commit hooks
- Runs checks (ruff, mypy, tests)
- Optional: starts dev services via existing `start-aitbc-dev.sh`
- Made executable, tested with `--check` — all checks passed (ruff, mypy, pytest)

**Verification**:
```bash
cd /opt/aitbc && scripts/dev/setup.sh --check
# Expected: all checks pass
```

**Estimated impact**: ~80 lines. DX improvement for onboarding.

---

#### B3: Raise coverage gate (`--cov-fail-under`)

**Problem**: `pyproject.toml` has no enforced `--cov-fail-under` threshold. Coverage can silently regress without CI failing.

**Fix**:

**Step 1**: Measure current coverage baseline:
```bash
cd /opt/aitbc && ./venv/bin/python -m pytest tests/unit --cov=aitbc --cov-report=term-missing -o addopts="" 2>&1 | tail -5
```

**Step 2**: Set `--cov-fail-under` to a conservative floor below current coverage (e.g. current - 2%) to avoid immediate CI breakage, then ratchet upward each release.

**Step 3**: Add to `pyproject.toml` `[tool.pytest.ini_options]`:
```toml
addopts = "-ra -q --strict-markers --strict-config --reruns 2 --reruns-delay 1 --cov=aitbc --cov-fail-under=<BASELINE>"
```
Note: only add `--cov` opts if `pytest-cov` is reliably installed; otherwise document the gate in `scripts/dev/setup.sh` and CI instead.

**Step 4**: Update `scripts/dev/setup.sh` `--check` mode to enforce the gate.

**Verification**:
```bash
cd /opt/aitbc && ./venv/bin/python -m pytest tests/unit --cov=aitbc --cov-fail-under=<BASELINE> -o addopts=""
# Expected: passes (coverage >= baseline)
```

**Estimated impact**: ~3 lines in `pyproject.toml`. Prevents silent coverage regression.

---

#### B4: Add performance regression test suite (deterministic baselines, `perf` marker)

**Problem**: No deterministic perf baseline exists. Silent regressions in hot paths (tx validation, sync, gossip, settlement) go undetected.

**Fix**:

**Step 1**: Create `tests/perf/` directory with a `conftest.py` that:
- Registers the `perf` marker
- Provides a `benchmark` fixture (lightweight — `time.perf_counter` based, no extra dependency)
- Skips perf tests unless `-m perf` is passed or `RUN_PERF=1` env var is set

**Step 2**: Add deterministic perf tests for hot paths:
- `tests/perf/test_tx_validation_perf.py` — N transactions, assert under threshold
- `tests/perf/test_sync_perf.py` — block sync loop, assert under threshold
- `tests/perf/test_settlement_perf.py` — settlement state machine, assert under threshold

**Step 3**: Calibrate thresholds to the CI runner with a generous margin (e.g. 3x observed median) to avoid flakiness. Document the calibration method in each test's docstring.

**Step 4**: Register the `perf` marker in `pyproject.toml` `[tool.pytest.ini_options] markers`.

**Step 5**: Ensure perf tests are skipped by default in CI (not in `testpaths` or excluded via `-m "not perf"`).

**Verification**:
```bash
cd /opt/aitbc && ./venv/bin/python -m pytest tests/perf -m perf -q -o addopts=""
# Expected: passes with calibrated thresholds
cd /opt/aitbc && ./venv/bin/python -m pytest tests/unit -q -o addopts=""
# Expected: perf tests not collected (skipped by default)
```

**Estimated impact**: ~4 new files, ~200 lines. Catches silent perf regressions.

---

#### B5: Add reusable integration fixtures

**Problem**: The integration suite lacks reusable, deterministic fixtures, leading to test duplication and flakiness.

**Fix**:

**Step 1**: Audit existing integration tests for duplicated setup:
```bash
cd /opt/aitbc && grep -rn "async def.*fixture" tests/integration --include="*.py" | head -30
```

**Step 2**: Create `tests/integration/fixtures/` package with shared fixtures:
- `db.py` — isolated DB session per test (temp dir, `SQLModel.metadata.create_all`, teardown)
- `seeded_data.py` — deterministic seed data (chains, islands, validators, offers)
- `mock_services.py` — lightweight in-process mocks for coordinator/blockchain/wallet
- `__init__.py` — re-exports

**Step 3**: Update `tests/integration/conftest.py` to import and expose the shared fixtures.

**Step 4**: Refactor 2-3 existing integration tests to use the shared fixtures as a proof-of-concept (do not refactor the entire suite in this release — that's a follow-up).

**Verification**:
```bash
cd /opt/aitbc && ./venv/bin/python -m pytest tests/integration -q -o addopts=""
# Expected: passes, no new failures
```

**Estimated impact**: ~5 new files, ~300 lines. Reduces duplication and flakiness; foundation for future integration test cleanup.

---

## Coordination

No shared files require sequencing in this release. The only cross-agent touch point is `pyproject.toml`:
- Agent B owns all `pyproject.toml` edits (dep pins, coverage gate, markers, mypy excludes).
- Agent A requests mypy exclude removal via a comment in this file under "Coordination Log" below; Agent B applies the edit.

### Coordination Log

| Date | Agent | Request | Status |
|------|-------|---------|--------|
| 2026-07-06 | A2 | Remove stale `aitbc/agent_compliance`, `aitbc/agent_protocols`, `aitbc/agent_trading` exclusions from `[tool.mypy] exclude` (dirs deleted in v0.10.9) | Pending |
