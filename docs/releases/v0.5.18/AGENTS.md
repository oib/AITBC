# v0.5.18 — Agent Task Assignment

**Last Updated**: 2026-06-30
**Version**: 1.0

**Release Theme**: Test Suite Repair (Patch). Green the `apps/blockchain-node/tests/` suite (64 failed + 8 errors, all pre-existing), stop it from hanging, quarantine infra-dependent tests behind auto-skip markers, and add the suite to the default `pytest` gate so it can't silently rot again.

**Goal**: `pytest apps/blockchain-node/tests/` → 0 failed / 0 errors (infra tests skip when Redis/Postgres absent), no hangs, zero collection errors, and the suite collected by `testpaths`.

> **Hard constraint**: **test-only + pytest config.** No production `aitbc_chain` source changes. If a "stale test" exposes a real behavioral regression (watch `test_staking`, `test_consensus`, `test_guardian_contract`), STOP and escalate — do not weaken an assertion to force a pass.

> **Scope note**: Full investigation + per-file root causes are in <ref_file file="/opt/aitbc/docs/releases/v0.5.18/suggestions.md" />. All 72 failures verified pre-existing at commit `3d94338c2`.

---

## Documentation Structure

This release documentation has been split into topic-focused files:

- **[Overview](./overview.md)** - Release overview, status baseline, and task split overview
- **[Agent A Tasks](./agent-a.md)** - Shared test config & infrastructure (pytest markers, auto-skip fixtures, testpaths)
- **[Agent B Tasks](./agent-b.md)** - Blockchain-node test fixes (16 test files, stale assertions, infra quarantine)

---

## Quick Navigation

### Overview
- [Status Baseline](./overview.md#status-baseline--verified-facts-do-not-re-investigate)
- [Task Split Overview](./overview.md#task-split-overview)

### Agent A (Shared Test Config)
- [Scope](./agent-a.md#scope)
- [Tasks](./agent-a.md#tasks)
- [Register markers + default timeout](./agent-a.md#a1-register-markers--default-timeout)
- [Auto-skip fixtures](./agent-a.md#a2-auto-skip-fixtures)
- [Add to testpaths (LAST)](./agent-a.md#a3-add-to-testpaths-last)

### Agent B (Blockchain-Node Test Fixes)
- [Scope](./agent-b.md#scope)
- [Tasks](./agent-b.md#tasks)
- [test_rpc_router](./agent-b.md#b1-test_rpc_router-12)
- [test_guardian_contract](./agent-b.md#b2-test_guardian_contract-14)
- [test_mempool](./agent-b.md#b3-test_mempool-8)
- [Monkeypatch-target drift](./agent-b.md#b4-monkeypatch-target-drift-9)
- [Quarantine infra tests](./agent-b.md#b5-quarantine-infra-tests-12)
- [Remaining stale assertions](./agent-b.md#b6-remaining-stale-assertions-17)
- [Green run + fix v0.5.17 docs](./agent-b.md#b7-green-run--fix-v0517-docs)

---

## Status Baseline — Verified Facts (do NOT re-investigate)

| Fact | Evidence |
|------|----------|
| 64 failed + 8 errors in `apps/blockchain-node/tests/` | full run with `--timeout=15` |
| Identical 64+8 at `3d94338c2` (pre-session) | git worktree run — failures are pre-existing, not session-introduced |
| Suite hangs without timeout | ≥1 test blocks >20s on Redis/Postgres retry |
| `apps/blockchain-node/tests` NOT in `testpaths` | `pyproject.toml` `[tool.pytest.ini_options]` |
| `--strict-markers` + `--strict-config` ON | `pyproject.toml` `addopts` |
| `pytest-timeout` 2.4.0 installed; no default `timeout` | `pyproject.toml` deps |
| `fakeredis` NOT installed | `import fakeredis` fails |

---

## Task Split Overview

| Agent | Domain | Tasks | Files |
|-------|--------|-------|-------|
| **Agent A** | Shared test config / infrastructure | 3 items | `pyproject.toml` `[tool.pytest.ini_options]`, `apps/blockchain-node/tests/conftest.py` (marker auto-skip fixtures) |
| **Agent B** | Blockchain-node test fixes | 8 items | `apps/blockchain-node/tests/**` (16 test files) |

**This is a B-heavy patch** — nearly all work is per-test fixes in `apps/blockchain-node/tests/` (Agent B domain). Agent A owns only the cross-cutting pytest configuration and the reusable skip-guard infrastructure, which must land **first** because `--strict-markers` rejects any unregistered marker B tries to use.

**Conflict boundary**: Agent A edits `pyproject.toml` and adds marker/skip fixtures to `apps/blockchain-node/tests/conftest.py`. Agent B edits the individual test files only. The one shared file is `conftest.py` — Agent A creates the fixtures first, Agent B consumes them. The `testpaths` flip (A3) is the **last** step, after all of B's fixes are green.

---

**Documentation Version**: 1.0
**Last Updated**: 2026-06-30
**Release**: v0.5.18 — Test Suite Repair

---

## Agent A — Shared Test Config & Infrastructure

**Scope**: pytest markers, default timeout, reusable auto-skip fixtures, and the final `testpaths` inclusion. No test-logic changes.

**Verification command**:
```bash
cd /opt/aitbc && ./venv/bin/python -m pytest apps/blockchain-node/tests/ --collect-only -q 2>&1 | tail -5
```

### Tasks

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| A1 | Register `requires_redis`, `requires_postgres`, `requires_genesis` markers + add default `timeout` to pytest config. | 🔴 P0 (blocks B) | `pyproject.toml` | ✅ DONE |
| A2 | Add shared auto-skip fixtures/hooks so `requires_redis`/`requires_postgres`/`requires_genesis` tests skip when the resource is unreachable. | 🔴 P0 (blocks B) | `apps/blockchain-node/tests/conftest.py` | ✅ DONE |
| A3 | **(LAST)** Add `apps/blockchain-node/tests` to `testpaths` once B's suite is green. | High | `pyproject.toml` | ✅ DONE |

### Agent A — Detailed Instructions

#### A1: Register markers + default timeout
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

#### A2: Auto-skip fixtures
- In `apps/blockchain-node/tests/conftest.py`, add a `pytest_collection_modifyitems` hook (or autouse fixtures) that:
  - For `requires_redis`: attempt a fast Redis connection (env `REDIS_URL`, short timeout). On failure → `pytest.skip("Redis not available")`.
  - For `requires_postgres`: attempt a fast Postgres connection (env `DATABASE_URL`/`MEMPOOL_DB_URL`). On failure → skip.
  - For `requires_genesis`: skip if the expected genesis path is absent (unless a fixture provides one).
- Keep probes cheap (≤1–2s, guarded by the A1 default `timeout`). Do **not** add `fakeredis` or any new dependency in this patch.
- **Verify**: In this no-infra sandbox, `pytest apps/blockchain-node/tests/ -m "requires_redis or requires_postgres"` reports skips, not failures (after B5 tags the tests).

#### A3: Add to testpaths (LAST)
- After B1–B6 are green, add `"apps/blockchain-node/tests"` to `testpaths` in `pyproject.toml`.
- **Do not do this earlier** — it would turn the default `pytest` run red while B is mid-flight.
- **Verify**: `cd /opt/aitbc && ./venv/bin/python -m pytest -q` collects the blockchain-node suite with 0 failed / 0 errors (infra tests skipped).

---

## Agent B — Blockchain-Node Test Fixes

**Scope**: Update the 16 stale/infra test files to current APIs and apply Agent A's markers. No production source changes.

**Verification command**:
```bash
cd /opt/aitbc && ./venv/bin/python -m pytest apps/blockchain-node/tests/ -q -o addopts="" --timeout=60
```

### Tasks

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| B1 | `test_rpc_router.py` (12) — rebuild tx dicts to v0.5.16 `TransactionRequest` schema (top-level `to`/`amount`/`signature`); update error-message assertions. | 🔴 P0 | `test_rpc_router.py` | ✅ DONE |
| B2 | `test_guardian_contract.py` (14) — use valid 0x checksum addresses; align `reason`/`message` keys + status values. | 🔴 P0 | `test_guardian_contract.py` | ✅ DONE |
| B3 | `test_mempool.py` (8) — pass `sqlite:///{path}` URL to `DatabaseMempool`. | 🔴 P0 | `test_mempool.py` | ✅ DONE |
| B4 | Monkeypatch-target drift — `test_hub_manager.py` (6, `redis`), `test_force_sync_endpoints.py` (3, `session_scope`). | High | `network/test_hub_manager.py`, `test_force_sync_endpoints.py` | ✅ DONE |
| B5 | Quarantine infra tests with A's markers — `test_gossip_network.py` (7), `test_websocket.py` (4), `test_database_security.py` (1). | High | `test_gossip_network.py`, `test_websocket.py`, `security/test_database_security.py` | ✅ DONE |
| B6 | Remaining stale assertions — `test_staking.py` (6), `test_models.py` (2), `test_sync.py` (2), `test_consensus.py` (2), `test_gossip_broadcast.py` (2), `test_escrow.py` (1), `test_multi_validator_poa.py` (1), `test_island_join.py` (1). | Medium | (8 files) | ✅ DONE |
| B7 | Full-suite green run + correct v0.5.17 Final Test Results table. | Medium | `docs/releases/v0.5.17/change.log` | ✅ DONE |
| B8 | (Optional) Add CI collect-only guard note/script. | Low | docs / CI | ⬜ |

### Agent B — Detailed Instructions

#### B1: test_rpc_router (12)
- Tests build `TransactionRequest(...)` with the old shape (nested `recipient`/`value` in `payload`, no top-level `to`/`amount`/`signature`). The model now requires `to`, `amount`, `signature` (and accepts `chain_id`).
- Rebuild each test's tx dict to the current schema (mirror `apps/blockchain-node/tests/test_signing_round_trip.py`, which is green). For tests asserting validation rejection, assert against the **current** error messages.
- 2 failures are `AssertionError: Regex pattern did not match` — update the expected error-message regex.

#### B2: test_guardian_contract (14)
- `initiate_transaction()` now calls `to_checksum_address(to_address)`; placeholder addresses (`"0xrecipient"`) are rejected with `{"status":"rejected","reason":...}` — no `message` key → `KeyError: 'message'`.
- Replace placeholder addresses with valid 0x checksum addresses (e.g. `0x5E2D7C7A4F8E9B1c3D5A2E8F4C6B8A0D2E4F6A8C`).
- Align assertions to current response keys (`reason` on rejection vs `message` on approval) and status strings (`approved`/`time_locked`/`rejected`). Verify the spending-limit-message tests against `_check_spending_limits` (source line ~270).

#### B3: test_mempool (8)
- `DatabaseMempool(db_path, ...)` is given a raw filesystem path; the constructor builds a SQLAlchemy engine → `Could not parse SQLAlchemy URL`.
- Pass `f"sqlite:///{tmp_path / 'mempool.db'}"` (check the current `DatabaseMempool.__init__` signature in `apps/blockchain-node/src/aitbc_chain/mempool.py` ~line 174 for the exact expected arg).

#### B4: Monkeypatch-target drift (9)
- `test_hub_manager.py`: `monkeypatch.setattr(hub_manager, "redis", ...)` fails — module has no top-level `redis`. Patch the actual seam used by the current `hub_manager` (lazy import / client attribute). Tests that genuinely need Redis → tag `requires_redis` (B5).
- `test_force_sync_endpoints.py`: `monkeypatch.setattr(rpc_router, "session_scope", ...)` fails — `rpc.router` no longer exposes `session_scope`. Patch the current DB/session seam.

#### B5: Quarantine infra tests (12)
- Apply Agent A's markers (must be merged first):
  - `test_gossip_network.py` → `@pytest.mark.requires_redis` / `@pytest.mark.requires_postgres` per test (Redis URL scheme + Postgres 5432 auth errors).
  - `test_websocket.py` → `requires_redis` (pub/sub backed) where applicable.
  - `security/test_database_security.py` → `requires_postgres`.
- After tagging, these **skip** (not fail) in a no-infra environment.

#### B6: Remaining stale assertions (17)
- `test_staking.py` (6): messages/values drifted (`'self stake must be at least 1000.0'` vs `'insufficient stake'`, staked totals, active validators). **Verify current StakingManager behavior before editing** — if logic genuinely regressed, escalate.
- `test_models.py` (2): construct `Block` with `chain_id` (NOT NULL); fix hash-validation message.
- `test_sync.py` (2): add `skip_state_root_validation` kwarg to the `fake_import_block` double; fix `'Invalid hash length'` message assertion.
- `test_consensus.py` (2): proposer start/stop — may need a `requires_genesis` mark or a genesis fixture (the `Genesis file required for chain test-chain` RuntimeError). Classify and apply A's marker if infra-bound.
- `test_gossip_broadcast.py` (2): update to current `BroadcastGossipBackend` API (`_broadcast`, async-CM `TopicSubscription`).
- `test_escrow.py` (1): `EscrowManager.verify_milestone` renamed — use current method.
- `test_multi_validator_poa.py` (1), `test_island_join.py` (1): verify + update assertions.

#### B7: Green run + fix v0.5.17 docs
- Run the full suite; confirm 0 failed / 0 errors (infra skipped). Then correct the Final Test Results table in `docs/releases/v0.5.17/change.log` (it measured only 3 of 17 blockchain-node files).

---

## Coordination Protocol

### File Ownership
| File | Owner | Notes |
|------|-------|-------|
| `pyproject.toml` `[tool.pytest.ini_options]` | Agent A | A1 (markers+timeout) first; A3 (testpaths) last |
| `apps/blockchain-node/tests/conftest.py` | Agent A | A2 skip fixtures — created before B5 consumes markers |
| `apps/blockchain-node/tests/*.py` (test bodies) | Agent B | B1–B6 |
| `docs/releases/v0.5.17/change.log` | Agent B | B7 |

### Execution Order
```
Phase 1 (Agent A — unblocks B):
  A1 register markers + default timeout   (pyproject.toml)
  A2 auto-skip fixtures                    (conftest.py)

Phase 2 (Agent B — parallel across files, after A1/A2):
  B1 test_rpc_router        B2 test_guardian_contract     B3 test_mempool
  B4 monkeypatch drift      B5 quarantine infra tests      B6 remaining stale
  B7 green run + v0.5.17 doc fix

Phase 3 (Agent A — LAST, after B green):
  A3 add apps/blockchain-node/tests to testpaths
```

`A1`/`A2` must precede `B5` (strict-markers). `A3` must be last (would otherwise turn the default gate red mid-flight). B1–B6 are independent per-file and can be done in any order / parallelized.

---

## Success Criteria

- ✅ `pytest apps/blockchain-node/tests/` → 0 failed, 0 errors (infra tests skip when Redis/Postgres absent)
- ✅ Suite cannot hang — default `timeout` enforced
- ✅ `--strict-markers` passes with new markers registered
- ✅ `apps/blockchain-node/tests` in `testpaths`; default `pytest -q` collects it green
- ✅ Zero collection errors (`--collect-only` clean)
- ✅ Diff contains **no** `apps/blockchain-node/src/**` changes (tests + `pyproject.toml` + conftest only)
- ✅ `tests/unit` and `tests/cli` remain green
