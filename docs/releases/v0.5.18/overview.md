# v0.5.18 Test Suite Repair — Overview

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
- [Status Baseline](#status-baseline--verified-facts-do-not-re-investigate)
- [Task Split Overview](#task-split-overview)

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

## Related Topics

- [Agent A Tasks](./agent-a.md) - Shared test config & infrastructure implementation details
- [Agent B Tasks](./agent-b.md) - Blockchain-node test fixes implementation details

---

**Documentation Version**: 1.0
**Last Updated**: 2026-06-30
**Release**: v0.5.18 — Test Suite Repair
