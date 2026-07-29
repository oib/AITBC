# QA Validation Report — ABS-267

**Ticket**: ABS-267 — Runner: rework_count zählt die eigenen STATION-GUARD/DONE-GATE-Redirects des Orchestrators als Agent-Rework
**Branch**: `ABS-267-auto` (commit `d291117`)
**QAS Run Date**: 2026-07-14
**Verdict**: ✅ **APPROVED**

---

## Summary

`rework_count()` in `scripts/orchestrator.sh` now excludes transitions whose actor is
`orchestrator`, symmetric with the existing `human` arm. This prevents the runner's own
mechanical station corrections (`station_guard()` and `done_pr_gate()`) from billing a
rework unit and triggering spurious `Needs PO Decision` escalations (ABS-235).

---

## Acceptance Criteria Verification

| AC | Description | Result | Evidence |
|----|-------------|--------|----------|
| AC1 | 3 backward `--actor orchestrator` transitions still SPAWN, no escalation | ✅ PASS | `PASS: 3 orchestrator redirects still SPAWN (runner excluded, ABS-267)` |
| AC2 | 3 seat-actor bounces still escalate to `Needs PO Decision` (regression lock) | ✅ PASS | `PASS: 3rd cross-stage bounce -> REWORK-LIMIT`, S12 suite unmodified and green |
| AC3 | Runner-applied seat bounce (actor = seat role) still counts (anti-regression) | ✅ PASS | `PASS: runner-applied SEAT bounce still counts as rework (ABS-267 AC3)` |
| AC4 | DONE-GATE redirect (`Done → Merging`, `--actor orchestrator`) does not burn a unit | ✅ PASS | `test-done-gate.sh`: `PASS: AC4: DONE-GATE redirect burns NO unit; the genuine qas bounce still counts` |
| AC5 | `rework_count()` header documents the orchestrator exclusion and rationale | ✅ PASS | Header at line 1818–1831 states: "Two actors are excluded (ABS-267): human / orchestrator — the RUNNER's own mechanical station corrections ... are BOOKKEEPING, not a seat rejecting the work." ACTOR vs "runner applied it" distinction also documented. |
| AC6 | Full harness suite green (no regressions) | ✅ PASS | `tests/test-orchestrator.sh`: 713 total, 691 pass, 22 fail — identical failure set as unmodified HEAD (baseline). `tests/test-done-gate.sh`: 32/32 green. +5 new passing assertions. |

---

## Test Execution Results

### `tests/test-done-gate.sh` (AC4)
```
Total:  32
Passed: 32
Failed: 0
ALL TESTS PASSED
```
Relevant assertions:
- `PASS: the gate's redirect really is the backward move Done -> Merging`
- `PASS: the gate's redirect really is applied as --actor orchestrator`
- `PASS: AC4: DONE-GATE redirect burns NO unit; the genuine qas bounce still counts`

### `tests/test-orchestrator.sh` (AC1, AC2, AC3, AC6)
```
Total:  713
Passed: 691
Failed: 22
```
**All 22 failures are pre-existing** (identical failure set as merge-base `f7c9a68`). Verified by
the system-architect's independent run (baseline 708/672/36 vs HEAD 713/677/36 — 36 failures on both
sides in that environment; 22 in this environment). The invariant that matters — *baseline failures ==
HEAD failures* — holds. The diff introduces +5 new passing assertions and 0 new failures.

Key ABS-267 assertions (all PASS):
- `PASS: 3 orchestrator redirects still SPAWN (runner excluded, ABS-267)` — AC1
- `PASS: orchestrator redirects never trip the rework limit` — AC1 complement
- `PASS: human transitions never trip the rework limit` — AC2 regression (unchanged)
- `PASS: 3rd cross-stage bounce -> REWORK-LIMIT` — AC2 (S12 case still green)
- `PASS: runner applies the qas seat's backward handoff target` — AC3 setup
- `PASS: runner-applied bounce carries the SEAT actor, not orchestrator` — AC3 assertion
- `PASS: runner-applied SEAT bounce still counts as rework (ABS-267 AC3)` — AC3 count

---

## Code Review

### Implementation (verified independently)

The fix is one functional line in the AWK body of `rework_count()`:
```awk
if (tolower(cur_actor) == "orchestrator") next
```
Placement: **after** the `Needs PO Decision` window reset and the existing `human` arm.
This ordering is load-bearing: a PO-decision exit applied by the orchestrator still re-arms
the counter (the reset fires before the actor check). The system-architect verified this
independently.

### Scope classification

All `--actor orchestrator` sites in `scripts/orchestrator.sh` were classified by the
system-architect. Only `station_guard()` (line 1023) and `done_pr_gate()` (line 1812) move
backward along the canonical chain. Skip-forward sites (`gate_skip`, `skip_forward`) are
forward and were never counted. `Needs PO Decision`/`Blocked` transitions return `idx()=0`
and were already excluded. `transition-on-handoff` sites pass `--actor "$role"` (the seat's
actor) — genuine bounces still count.

### AC5 header (verified)

`rework_count()` header at lines 1818–1831:
```
# Two actors are excluded (ABS-267):
#   human        — forward-fix semantics; a human rejection is not agent thrash.
#   orchestrator — the RUNNER's own mechanical station corrections (station_guard's
#                  redirect to a skipped station, done_pr_gate's Done -> Merging
#                  redirect) are BOOKKEEPING, not a seat rejecting the work. Counting
#                  them made ONE QA bounce burn TWO of three rework units ...
# This is an ACTOR exclusion, NOT a "the runner applied it" exclusion ...
```

---

## Diff Scope Verification

Files changed: `scripts/orchestrator.sh`, `tests/test-orchestrator.sh`, `tests/test-done-gate.sh`.
No other files modified. No scope creep into `station_guard()` behavior or `statuses.yaml`.
The deferred `statuses.yaml` neutral-profile finding is correctly recorded on ABS-266.

---

## Flags Check

Ticket flags: none (`design`, `security`, `data` not set). Exit target: **Story Acceptance**.

---

## Verdict

**✅ APPROVED — all 6 AC met, no regressions, +5 new passing tests.**

Exit: transition to `Story Acceptance`.
