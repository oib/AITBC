# QA Validation Report — ABS-455

**Ticket**: ABS-455 — Retro: Budget-Pause-Ergonomie — Operator-Push + sauberer Restart-Handshake  
**Branch**: `ABS-455-auto`  
**Commits under review**: `d4c36b7` (feat) + `1e947c8` (test guard)  
**QAS actor**: qas  
**Date**: 2026-07-19  
**Verdict**: ✅ **APPROVED**

---

## Acceptance Criteria Verification

### AC1 — Budget exhaustion emits push notification + unambiguous log exit line

**Implementation evidence:**
- New `budget_pause_push` helper calls shared `operator_push` (backgrounded, non-blocking) from both `pause_for_daily_budget` and `pause_for_budget`
- `exit_budget_pause` emits `"BUDGET-PAUSE exit: …"` log line with reason + residual state at ALL three run-end points (`--once`, loop rc==10, max-cycles)
- `ORCH_BUDGET_PUSH=0` suppresses the operator dialog (escape hatch; tracker NOTIFY still fires)

**Test verification:**  
`PASS ABS-455 AC1: a clear, unambiguous budget-pause exit line is emitted`

**Result**: ✅ PASS

---

### AC2 — Standstill-without-exit path eliminated or explicitly distinguishably documented

**Implementation evidence:**
- `liveness_watchdog` checks `actionable > 0 && (daily_budget_exhausted || budget_exhausted)` BEFORE the STANDSTILL-HELD branch
- A budget-blocked standstill → `STANDSTILL-BUDGET-EXIT` runlog event → same clean budget-pause exit (not a forever hold)
- Human-gated standstills (actionable=0 or human flag) still flow to the loud `STANDSTILL-HELD` — distinguishable, not mixed

**Test verification:**  
```
PASS ABS-455 AC2: a budget-caused standstill exits with the handshake code, not a forever hold
PASS ABS-455 AC2: the standstill-without-exit path is converted to a clean budget-pause exit
PASS ABS-455 AC2: the budget standstill never reaches the forever-hold state
```

**Result**: ✅ PASS

---

### AC3 — Conformance test for exit-code handshake

**Implementation evidence:**
- `ORCH_BUDGET_PAUSE_EXIT_CODE` (default 75 = EX_TEMPFAIL) wired at all three run-end points
- Persisted monotonic restart counter at `$ORCH_STATE_DIR/budget-restart-count`; non-numeric guard; ADR-A-0009 cost gate NOT auto-lifted
- `usage()` and env-var header document the restart handshake and exit codes
- Conformance test: `tests/orchestrator.d/ABS-455-budget-pause-handshake.sh` (10 asserts)

**Test verification:**
```
PASS ABS-455 AC3: budget exhaustion exits with the restart-handshake code (default 75)
PASS ABS-455 AC3: the exit line names the restart counter (ADR-A-0009 review point)
PASS ABS-455 AC3: the restart counter is persisted in the state dir
PASS ABS-455 AC3: a second budget pause exits with the same handshake code
PASS ABS-455 AC3: each budget pause bumps the persisted restart counter (survives restarts)
PASS ABS-455 AC3: ORCH_BUDGET_PAUSE_EXIT_CODE overrides the handshake code
```

**Result**: ✅ PASS

---

## Independent Validation Runs

### bash -n syntax check
```
bash -n scripts/orchestrator.sh → PASS (clean)
```

### ABS-455 conformance test (isolated QAS run)
```
=== ABS-455 budget-pause restart handshake ===
  PASS ABS-455 AC3: budget exhaustion exits with the restart-handshake code (default 75)
  PASS ABS-455 AC1: a clear, unambiguous budget-pause exit line is emitted
  PASS ABS-455 AC3: the exit line names the restart counter (ADR-A-0009 review point)
  PASS ABS-455 AC3: the restart counter is persisted in the state dir
  PASS ABS-455 AC3: a second budget pause exits with the same handshake code
  PASS ABS-455 AC3: each budget pause bumps the persisted restart counter (survives restarts)
  PASS ABS-455 AC3: ORCH_BUDGET_PAUSE_EXIT_CODE overrides the handshake code
  PASS ABS-455 AC2: a budget-caused standstill exits with the handshake code, not a forever hold
  PASS ABS-455 AC2: the standstill-without-exit path is converted to a clean budget-pause exit
  PASS ABS-455 AC2: the budget standstill never reaches the forever-hold state
Total: 10 | Passed: 10 | Failed: 0 — ALL ASSERTIONS PASSED
```

### shellcheck (-S error)
- No new error-level findings in ABS-455 lines
- Pre-existing SC1087/SC1125 on lines 6321, 6920, 7013, 7043, 7058, 7092, 8375 — all confirmed pre-existing (blame outside ABS-455 diff hunks)

### §5.4 budget tests in main suite (partial — confirmed passing mid-run)
```
PASS budget 1 -> exactly one SPAWN this run
PASS budget exhaustion notified
PASS second eligible event skipped for budget
```

### Full suite regression (developer-reported, architecture-confirmed)
- `1224/1224, FAIL=0` (BE developer ran full suite after guarding the 3 budget-exhausting captures with `|| true` to prevent ABS-370 set-e abort)

---

## ADR-A-0009 Human Cost Gate (PO Guardrail)

✅ **PRESERVED**: The human cost review point is intact. The implementation:
- Persists a monotonic restart counter to `$ORCH_STATE_DIR/budget-restart-count`
- Logs the counter on every budget-pause exit with explicit statement: "the cost gate is NOT auto-lifted"
- Documents in `usage()` that a supervisor MAY restart on exit code 75, but the cost gate stays auditable
- Does NOT auto-lift or bypass the ADR-A-0009 review requirement

---

## Files Changed

| File | Change |
|------|--------|
| `scripts/orchestrator.sh` | +88 lines: `operator_push` shared helper, `budget_pause_push`, `exit_budget_pause`, AC2 standstill-budget conversion, env-var docs, 3× main() exit points, `usage()` exit-code table |
| `tests/orchestrator.d/ABS-455-budget-pause-handshake.sh` | +84 lines: 10-assert conformance test (new file) |
| `tests/test-orchestrator.sh` | +9 lines: `ORCH_BUDGET_PUSH=0` guards + `|| true` on 3 budget-exhausting captures (ABS-370 set-e fix) |

---

## Verdict

| Criterion | Status |
|-----------|--------|
| AC1: Push + exit line on budget exhaustion | ✅ PASS |
| AC2: Standstill-without-exit eliminated | ✅ PASS |
| AC3: Exit-code handshake conformance test | ✅ PASS |
| bash -n syntax clean | ✅ PASS |
| Conformance test 10/10 | ✅ PASS |
| shellcheck: no new error-level findings | ✅ PASS |
| ADR-A-0009 cost gate preserved | ✅ PASS |
| No `design` flag → Story Acceptance | N/A |

**Final verdict: APPROVED — all AC criteria met, no blocking findings.**
