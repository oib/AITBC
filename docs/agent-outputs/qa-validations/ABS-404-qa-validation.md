# QA Validation Report — ABS-404

**Date:** 2026-07-17
**Validator:** qas
**Branch:** ABS-404-auto
**Commits reviewed:** `daa11fd` (over `ebcac8a`)
**Verdict: ✅ APPROVED**

---

## Ticket Summary

ABS-404: `statuses.yaml` is not single-source-of-truth — a new status must be manually propagated to ≥3 embedded locations (ABS-338 Canceled-drift).

**Goal:** make status drift fail BEFORE the merge (not at release), by inventorying every embedded copy and running a unified guard in CI.

---

## Acceptance Criteria Validation

### AC1 — Complete inventory of all embedded copies

| Copy | Location | What it embeds | Guard | Result |
|------|----------|---------------|-------|--------|
| A | `scripts/hooks/iteration-guard.sh` ranks[]/eranks[] | Chain order | ✅ GUARDED | PASS |
| B | `scripts/orchestrator.sh` is_known_status() | Membership set | ✅ GUARDED | PASS |
| C | `scripts/orchestrator.sh` terminal rest-skip lists (3 fns) | Terminal subset | ✅ GUARDED | PASS |
| D | `backend/packages/core/src/workflows/statuses.yaml` | Byte-identical mirror | ✅ GUARDED | PASS |
| E | `scripts/fastlane-eligibility.sh` IN_FLIGHT | Active-work membership subset | ✅ GUARDED (daa11fd) | PASS |

**Not-copies (data-driven, no drift):** `jira-tracker.sh` CANON_STATUS_LIST, `status_is_terminal()`, `mock-tracker.sh` validation — documented in guard header.

**Out-of-scope (documented, not silently missed):** backend TS status literals (`invariants.ts`, `board.ts`, `dashboard.ts`, `util.ts`) — COPY D already pins the backend `statuses.yaml` byte-identical; TS-side guard belongs with the backend workspace lint/typecheck.

**AC1: ✅ PASS** — inventory complete and bounded; no embedded copy left undocumented.

---

### AC2 — Single unified drift-guard (Option-b)

`scripts/status-source-drift-guard.sh` covers COPY A through COPY E in one place.

Evidence (live run, clean repo):
```
  COPY A OK: iteration-guard ranks match statuses.yaml order
  COPY B OK: orchestrator is_known_status() matches statuses.yaml names
  COPY C OK: all terminal statuses present in the orchestrator rest-skip lists
  COPY D OK: backend statuses.yaml mirror is byte-identical
  COPY E OK: fastlane IN_FLIGHT tokens are all valid statuses.yaml names
status-source-drift-guard: OK — all embedded status copies match statuses.yaml.
EXIT: 0
```

**AC2: ✅ PASS**

---

### AC3 — Regression test: injected status turns guard red

`tests/test-status-source-drift.sh` — **9/9 PASS** (live run this session)

| Test case | Expected | Result |
|-----------|---------|--------|
| Clean repo against real statuses.yaml | exit 0 | ✅ PASS |
| Injected non-terminal status → guard exits 1 | exit 1 | ✅ PASS |
| COPY A drift reported (iteration-guard ranks) | DRIFT: COPY A | ✅ PASS |
| COPY B drift reported (is_known_status) | DRIFT: COPY B | ✅ PASS |
| COPY D drift reported (backend mirror) | DRIFT: COPY D | ✅ PASS |
| Injected terminal status → guard exits 1 | exit 1 | ✅ PASS |
| COPY C drift reported (terminal rest-skip lists) | DRIFT: COPY C | ✅ PASS |
| Bogus IN_FLIGHT token → guard exits 1 | exit 1 | ✅ PASS |
| COPY E drift reported (fastlane IN_FLIGHT) | DRIFT: COPY E | ✅ PASS |

Additional probes (manual):
- `STATUS_SOURCE_FILE=/nonexistent/file.yaml` → `exit 2` (hard error, never silently passes) ✅

**AC3: ✅ PASS**

---

### AC4 — Pre-release / CI wiring (drift fails before merge)

All three discovery points confirmed (live `grep`):

| Discovery mechanism | Location | Result |
|--------------------|---------|--------|
| `tests/test-*.sh` glob | `scripts/pre-release-check.sh:98` | ✅ auto-discovers |
| `tests/test-*.sh` array | `.github/workflows/tests.yml:60` | ✅ auto-discovers |
| `tests/test-*.sh` loop | `bitbucket-pipelines.yml:138` | ✅ auto-discovers |

`tests/test-status-source-drift.sh` is named with the `test-*.sh` pattern and placed in `tests/` → zero CI config edits required.

**AC4: ✅ PASS**

---

## Regression Check

`tests/test-iteration-guard.sh` — **54/54 PASS** (live run this session). No regressions introduced.

---

## Summary

| Criterion | Verdict |
|-----------|---------|
| AC1 — Complete inventory | ✅ PASS |
| AC2 — Unified drift-guard | ✅ PASS |
| AC3 — Regression test (guard goes red on drift) | ✅ PASS |
| AC4 — Pre-release / CI wiring | ✅ PASS |
| No regressions (test-iteration-guard 54/54) | ✅ PASS |

**Final Verdict: APPROVED**

All four acceptance criteria are met. The implementation is bash/CI tooling only — no RLS/DB/auth/frontend surface. Option-b (unified guard, not codegen) is the PO-sanctioned choice per the AC text. The ticket has no `design` flag; releasing to Story Acceptance.
