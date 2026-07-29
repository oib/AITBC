# QA Validation Report — PILOT-64

**Ticket:** PILOT-64 — Iterations-Cap darf nicht agenten-schreibbar sein  
**Commit:** a5a1e627  
**Branch:** PILOT-64-auto  
**QAS run:** 2026-07-26  
**Verdict:** APPROVED

---

## Acceptance Criteria Results

### AC1 — Cap source is configuration, not agent prose
**PASS**

`DEFAULT_CAP="${ITERATION_GUARD_DEFAULT_CAP:-3}"` (line 86 of `scripts/hooks/iteration-guard.sh`).  
The cap floor is an env var with default 3. No comment scanning sets the baseline cap.  
Aligns with ADR-A-0026: control state in typed config, not parsed comments.

### AC2 — Markers may only raise the cap, never lower it
**PASS**

AWK accumulates `marker_cap` via `if (m + 0 > marker_cap + 0) marker_cap = m + 0` — maximum, never latest-wins.  
Bash applies the marker only when it exceeds the floor:
```bash
if [ -n "$marker_cap" ] && [ "$marker_cap" -gt "$cap" ] 2>/dev/null; then
    cap="$marker_cap"
fi
```
An `of 1` marker in any comment — approve, quote, gate-results — cannot pull the effective cap below 3.  
Three test cases confirm this:
- `'of 1' marker cannot lower the cap below floor 3 -> 1 bounce proceeds` — PASS  
- `later 'of 1' does not lower a cap already raised to 5 (max wins)` — PASS  
- `TRACKER_CMD with args at cap -> block` — PASS (control: raise path still works)

### AC3 — Cap-hit names cap source and counted iterations
**PASS**

Block message observed in E2E run:
```
iteration-guard: BLOCK TEST-1 — 2 prior FUNCTIONAL bounce(s) at gate 'In Review',
cap 3 [configured floor ITERATION_GUARD_DEFAULT_CAP=3] reached
(0 infrastructure abort(s) excluded, not counted — PILOT-49/ABS-555);
escalate to human, do not bounce
```
`cap_source` variable carries either `"configured floor ITERATION_GUARD_DEFAULT_CAP=3"` or  
`"raised by marker to M (above configured floor N)"`.  
Test `AC3: block message names the cap source (configured floor)` — PASS  
Test `AC3: block message names the functional bounce count` — PASS

### AC4 — Falsification fixture: APPROVE "Iteration 1 of 1" at 0 bounces → no block
**PASS**

Test: `AC4: APPROVE 'Iteration 1 of 1' at 0 bounces -> no block (cap floored at 3)` — PASS  

E2E reproduction of the PILOT-32 scenario:
- Ticket moved to In Review
- `gate-results` comment posted with body: `QAS Gate Results — Iteration 1 of 1 — APPROVED, no issues found`
- `ITERATION_GUARD_ADAPTER="$MOCK_TRACKER" bash iteration-guard.sh TEST-1`
- **Exit: 0** (no block)

Old code returned exit 2 here. The defect is fixed.

---

## Test Suite

```
bash tests/test-iteration-guard.sh

Total:  65
Passed: 65
Failed: 0

ALL TESTS PASSED
```

Run against commit: a5a1e627

New PILOT-64 test cases (5 of the 65):
- `AC4: APPROVE 'Iteration 1 of 1' at 0 bounces -> no block` — PASS
- `AC2: 'of 1' marker cannot lower the cap below floor 3 -> 1 bounce proceeds` — PASS
- `AC2: later 'of 1' does not lower a cap already raised to 5 (max wins)` — PASS
- `AC3: block message names the cap source (configured floor)` — PASS
- `AC3: block message names the functional bounce count` — PASS

shellcheck: exit 0 (no findings)

---

## Files Changed

```
scripts/hooks/iteration-guard.sh  | 47 +++++++++++++++++++++++++++++++-----------
tests/test-iteration-guard.sh     | 41 +++++++++++++++++++++++++++++++++++
2 files changed, 75 insertions(+), 13 deletions(-)
```

No migrations. No ADR authoring. No new dependencies. No ledger IDs allocated.  
Scope bounded to the iteration-guard shell script and its test suite.

---

## Scope Boundary

The operator's gate-results comment in the ticket history (`Iteration 1 of 9`) demonstrates the defect in the deployed stable guard. Commit a5a1e627 fixes the guard. Post-merge, no comment can lower the cap below `ITERATION_GUARD_DEFAULT_CAP`; the operator's workaround is structurally unnecessary once this lands.

---

## Verdict

**APPROVED — all four ACs met, 65/65 tests pass, shellcheck clean, E2E PILOT-32 reproduction fixed.**
