# QA Validation Report — ABS-406

**Ticket**: ABS-406 Wait-State-Watchdog: Profil-Paritaet fuer jira/mock (degradierter Orchestrator-Sweep)
**QAS Actor**: qas
**Date**: 2026-07-18
**Branch**: ABS-406-auto
**Commit Audited**: 256b2af
**Verdict**: ✅ APPROVED

---

## Validation Evidence

### Test Suite Results

```
bash tests/test-orchestrator.sh  (exit code: 0)

=== ABS-406 degraded wait-state invariant sweep ===
  PASS  ABS-406 AC2 (ABS-354): Ready for Merge with no MR raises exactly one invariant-violation signal
  PASS  ABS-406 AC2: the signal names the missing evidence
  PASS  ABS-406 AC2/AC5: the ticket did NOT move — detection only
  PASS  ABS-406 AC3 (ABS-333): Docs with an unmerged MR raises an invariant-violation signal
  PASS  ABS-406 AC3: the signal names why (PR open, not merged)
  PASS  ABS-406 AC3/AC5: the ticket rests in Docs — never transitioned
  PASS  ABS-406 AC4: Ready for Merge WITH an open MR raises NO signal
  PASS  ABS-406 AC4: Merging with an active seat (within grace) raises NO signal
  PASS  ABS-406 AC4: Docs WITH a merged MR raises NO signal
  PASS  ABS-406 AC1: Merging with no branch/seat but within grace raises NO signal (just-entered story)
  PASS  ABS-406 AC1: Merging with no branch/seat PAST grace raises a signal
  PASS  ABS-406 AC1: the grace-expired signal names the missing branch-or-seat evidence
  PASS  ABS-406 AC5: the sweep DID act (posted a comment) on the violation
  PASS  ABS-406 AC5: the sweep issued NO transition op — human-only boundary intact
  PASS  ABS-406 AC6: two sweeps over the same unchanged violation still leave exactly ONE signal
  PASS  ABS-406: ORCH_INVARIANT_SWEEP=0 disables the sweep (off-switch)

=== Test Results (aggregated over 4 shards) ===
  Total:  1173
  Passed: 1173
  Failed: 0
  ALL TESTS PASSED
```

### bash -n Syntax Checks

```
orchestrator.sh:    CLEAN
mock-tracker.sh:    CLEAN
jira-tracker.sh:    CLEAN
```

---

## Acceptance Criteria Verification

### AC1 — Shared declarative Status→Evidence rule table, 3 core rules
**PASS**

- `ORCH_INVARIANT_RULES` is an env-overridable declarative config variable (not hardcoded logic), defined at orchestrator.sh:488
- Covers all 3 required rules:
  - `Ready for Merge|open-mr|0` — resting at the human merge gate requires an OPEN mirrored PR
  - `Merging|branch-or-seat|600` — a merging story requires a branch (PR) or an active seat
  - `Docs|mr-merged|0` — a story in Docs requires its PR to be MERGED (merge-base gate)
- Parity with ABS-391's `WAIT_STATE_INVARIANTS` verified 1:1: same status values, same evidence kinds, same grace second (600), same descriptions (substance-identical)
- Test: 2 assertions covering grace boundary (within → no signal, past grace → signal)

### AC2 — ABS-354 replay: `Ready for Merge` + no open MR → loud signal
**PASS**

- `_abs406_sweep "Ready for Merge" "NONE"` produces `VIOL=1`
- Signal body contains `"no PR mirrored"` — names the missing evidence
- Ticket status remains `Ready for Merge` (STATUS=Ready for Merge) — detection only, not corrected
- 3/3 assertions PASS

### AC3 — ABS-333 replay: `Docs` + MR still OPEN → signal
**PASS**

- `_abs406_sweep "Docs" "OPEN #7"` produces `VIOL=1`
- Signal body contains `"not merged"` — names the reason
- Ticket status remains `Docs` — no correction
- 3/3 assertions PASS

### AC4 — No false positives for normal/compliant cases (both sides covered)
**PASS**

- `Ready for Merge` WITH open MR → `VIOL=0` ✅
- `Merging` with active seat (within grace) → `VIOL=0` ✅
- `Docs` WITH merged MR → `VIOL=0` ✅
- 3/3 no-violation-side assertions PASS

### AC5 — Sweep NEVER self-corrects (ADR-A-0004 Human-Only boundary)
**PASS**

- Code inspection: `invariant_sweep` contains **zero** `tracker transition` calls — only `tracker comment --kind invariant-violation`
- Independently verified via `awk` extraction of the function body + grep for "tracker transition"
- Test spy confirms: `CALLS` contains `comment`, does NOT contain `transition`
- 2/2 assertions PASS (one positive — comment present; one negative — no transition op)

### AC6 — Idempotency: one signal per violation episode, not per sweep
**PASS**

- `_abs406_sweep "Ready for Merge" "NONE" "twice"` (two sweep runs) → `VIOL=1`
- Idempotency logic verified: `v_epoch >= t_epoch` check mirrors ABS-391's SQL `hasOpenViolationEvent`
- 1/1 assertion PASS

---

## Additional Quality Checks

| Check | Result |
|-------|--------|
| Both adapters updated (`invariant-violation` kind in valid-kind guard) | PASS — mock-tracker.sh L606, jira-tracker.sh L1425 |
| Kill-switch `ORCH_INVARIANT_SWEEP=0` disables sweep | PASS — test assertion PASS |
| Fail-open when `$FORGE_CMD` unset (no false-positive spam) | PASS — code: `[ -n "$FORGE_CMD" ] || return 0` |
| `invariant_sweep` wired into `reconcile()` after liveness watchdog | PASS — orchestrator.sh:6546 |
| No drive-by refactors — minimal diff (275 lines, 4 files) | PASS — only the 4 required files changed |
| ABS-391 rule-table parity 1:1 | PASS — status, evidence, grace (600s), description all verified |
| Prior gates | System Architect APPROVED; Security Review PASSED |

---

## Verdict

**APPROVED for Story Acceptance**

All 6 Acceptance Criteria met. Full suite 1173/1173 PASS including all 16 ABS-406 two-sided conformance assertions. `bash -n` clean. No `design` flag → exit to `Story Acceptance`.
