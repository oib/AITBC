# QA Validation Report — ABS-424

**Ticket**: ABS-424 — Backend-package (TS) status-literal drift guard  
**QAS Actor**: qas  
**Date**: 2026-07-18  
**Commit under review**: `ca11f57`  
**Branch**: `ABS-424-auto`  
**Verdict**: ✅ **APPROVED**

---

## Summary

Backend-native drift guard for TypeScript status-literal subsets. Closes the ABS-338
"Canceled" silent-drift incident class on the backend-TS side, which ABS-404 explicitly
scoped out. Implemented as a self-contained guard script (`scripts/backend-status-literal-drift-guard.sh`)
using the ABS-404 Option-b marker pattern — no dependency on ABS-404's scripts-side guard,
so it lands cleanly on `epic/ABS-392` without a modify/delete conflict.

---

## Acceptance Criteria Verification

### AC1 — Full inventory, every subset guarded or documented out-of-scope ✅

**Command run**: `git grep 'drift-guard:status-name' -- backend/`

**Result** — 13 marked literals across 5 files:

| File | Subset | Literals | Status |
|------|--------|----------|--------|
| `backend/packages/core/src/board.ts` | `ESCALATION_INBOX_STATUSES` | Blocked, Needs PO Decision, Ready for Epic Acceptance, Ready for Human Acceptance | GUARDED |
| `backend/packages/core/src/invariants.ts` | `WAIT_STATE_INVARIANTS.status` | Ready for Merge, Merging, Docs | GUARDED |
| `backend/packages/core/src/transitions.ts` | `REBASE_GATE_FROM / REBASE_GATE_TO` | Story Acceptance, Merging | GUARDED |
| `backend/apps/server/src/routes/dashboard.ts` | `MERGE_GATE_STATUSES` | Ready for Merge, Ready for Epic Acceptance | GUARDED |
| `backend/apps/web/src/util.ts` | `MERGE_GATE_STATUSES` | Ready for Merge, Ready for Epic Acceptance | GUARDED |

**Out-of-scope documentation** (in guard header, explicitly named):
- `board.ts:79,83` — `"Backlog"` / `"Done"` group labels: structurally-derived UI column headers that name-collide with statuses; NOT status-membership literals; explicitly called out to prevent confusion with a gap.
- `items.ts ADR_STATUS_MAP` + `"Superseded"` path literals + `server.ts to === "Accepted"`: single/fixed ADR-lifecycle literals keyed off `adr-lifecycle.yaml` (already in the guard's valid-name union); over-guarding these would exceed the ticket's "list/order/terminality subset" scope. Reasonable and documented.

**Full-tree inventory verification**: `git grep` from repo root across all backend TS files finds zero unmarked status-name literals of the drift class. The architect's second review (commit `3086287` → `ca11f57`) confirmed this after the iteration-1 bounce closed the `dashboard.ts` + `util.ts` gap.

**AC1: PASS**

---

### AC2 — Drift check fails on invalid literal (rename/removal direction) ✅

**Guard run on clean tree**:
```
backend-status-literal-drift-guard: OK — 13 marked backend TS status literals all valid workflow names.
Exit code: 0
```

**Rename/removal simulation** (from regression test case 2 — `Merging` removed from YAML):
- Guard output: `DRIFT: TS status literal 'Merging' in .../invariants.ts is not a valid workflow status name`
- Exit code: 1 ✓

**Bogus literal simulation** (regression test case 3 — `"Totally Not A Status"` added to dashboard.ts):
- Guard output: `DRIFT: TS status literal 'Totally Not A Status' ... is not a valid workflow status name`
- Exit code: 1 ✓

**AC2: PASS**

---

### AC3 — Regression test: rename turns check red; clean tree stays green ✅

**Command**: `bash tests/test-backend-status-literal-drift.sh`

**Output**:
```
Backend TS status-literal drift guard (ABS-424)
  ✓ clean tree: guard exits 0
  ✓ YAML rename/removal of 'Merging' turns the guard red
  ✓ bogus marked TS literal turns the guard red
  ✓ stripping every marker trips the anti-rot lock
  ✓ adr-lifecycle.yaml union validates an ADR-only literal ('Proposed')

  5/5 passed
```

Coverage:
- Clean tree → exit 0 ✓
- Rename/removal drift direction → exit 1 ✓
- Bogus apps-tree literal → exit 1 ✓
- Anti-rot lock (all markers stripped) → exit 1 ✓
- `adr-lifecycle.yaml` union supplies ADR-lifecycle names (e.g. `Proposed`) → exit 0 ✓

**AC3: PASS**

---

### AC4 — Pre-merge CI wiring via existing auto-discovery loop ✅

The test file `tests/test-backend-status-literal-drift.sh` matches the `tests/test-*.sh` glob
auto-discovered by all three CI entry points:

| CI Entry Point | Discovery Pattern | Line | Status |
|----------------|------------------|------|--------|
| `scripts/pre-release-check.sh` | `for test_file in tests/test-*.sh` | ~100 | AUTO-DISCOVERED ✓ |
| `.github/workflows/tests.yml` | `TESTS=(tests/test-*.sh)` | ~65 | AUTO-DISCOVERED ✓ |
| `bitbucket-pipelines.yml` | `for t in tests/test-*.sh` | ~143 | AUTO-DISCOVERED ✓ |

No manual registration needed. Drift fails on the PR, not at release — satisfies the CI
pre-merge requirement.

**AC4: PASS**

---

## Iteration History

| Iteration | Actor | Result |
|-----------|-------|--------|
| 1 (commit `74cdd9e`) | system-architect | CHANGES REQUESTED — AC1 incomplete: `dashboard.ts` + `util.ts` `MERGE_GATE_STATUSES` unguarded and undocumented (`apps/` tree missed) |
| 2 (commit `3086287`) | system-architect | APPROVED — gap closed, MEDIUM items documented; then re-homed as self-contained guard due to merge conflict |
| Final (commit `ca11f57`) | system-architect | APPROVED — self-contained guard lands cleanly on `epic/ABS-392`; no further issues |

System Architect gave final approval at commit `ca11f57`. QAS verification independently
confirms all 4 ACs against live runs.

---

## Additional Checks

- **Guard design**: Marker-based extraction (`drift-guard:status-name`) prevents false positives from comments, UI labels, SQL fragments. Precise and auditable. ✓
- **Anti-rot lock**: Guard exits 1 if zero markers found — the guard cannot be silently unwired. ✓
- **Valid-name union**: `statuses.yaml ∪ adr-lifecycle.yaml` correctly handles ADR-lifecycle names (`Proposed`, `Accepted`, etc.) that don't appear in the workflow status machine. ✓
- **Reverse direction**: Honestly documented out-of-scope (no mechanical check possible without an attribute in the YAML) — same honest limitation as ABS-404 COPY E. ✓
- **No ADR needed**: Approach mirrors ABS-404 Option-b precedent; no new architectural decision. ✓
- **No RLS/auth/DB/migration surface**: Pure tooling + TS comment markers. ✓
- **Flags**: none — `design`/`security`/`data` all absent; exit route is `Story Acceptance`. ✓

---

## Final Verdict

| Criterion | Result |
|-----------|--------|
| AC1 — Full inventory, guarded or documented | ✅ PASS |
| AC2 — Guard fails on invalid literal | ✅ PASS |
| AC3 — Regression test: clean→green, rename→red | ✅ PASS |
| AC4 — CI pre-merge auto-discovery wired | ✅ PASS |

**Overall: ✅ APPROVED — Story Acceptance**

> QAS validation complete for ABS-424. All 4 acceptance criteria PASS. Commit `ca11f57`,
> branch `ABS-424-auto`. No design flag — releasing to Story Acceptance.
