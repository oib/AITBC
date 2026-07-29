# QA Validation Report — PILOT-47

**Ticket**: PILOT-47 — Spawn-Budget fortschritts-bewusst: Drain-Modus statt Hard-Stop, Auto-Extend bei gesundem Run, Per-Ticket-Cap  
**QAS Seat**: qas (independent validation)  
**Commit under review**: `2384f3e9` (`feat(orchestrator): progress-aware spawn budget — drain, auto-extend, per-ticket cap [PILOT-47]`)  
**Branch**: `PILOT-47-auto`  
**Date**: 2026-07-26  
**Verdict**: ✅ **APPROVED**

---

## Pre-flight Checks

| Check | Result |
|-------|--------|
| Commit `2384f3e9` exists | ✅ PASS |
| Commit reachable from `refs/heads/PILOT-47-auto` | ✅ PASS |
| `bash -n scripts/orchestrator.sh` (syntax) | ✅ PASS — `SYNTAX OK` |
| No harness/agents/skills changes | ✅ PASS — no mirror regen needed (rule 10 N/A) |
| Branch is `PILOT-47-auto` (not main) | ✅ PASS |

---

## Test Suite Results

**Command**:
```bash
bash -c '
  unset BACKEND_URL BACKEND_TOKEN TRACKER_CMD ORCH_INSTANCE_ID
  for v in $(env | grep "^ORCH_" | cut -d= -f1); do unset "$v"; done
  bash tests/test-orchestrator.sh
' | tee work/scratch/PILOT-47-qa-fullsuite-clean.log
```

**Environment**: Fully scrubbed (ORCH_* vars + operator guardrail vars unset before run)  
**Test harness**: `tests/test-orchestrator.sh`, 4 parallel shards  
**Commit under test**: `2384f3e9`

| Metric | Value |
|--------|-------|
| Total assertions | 1346 |
| Passed | **1346** |
| Failed | **0** |
| Exit code | **0** |

Note: A first run produced 1 aborted shard (1195/1346) due to a leftover `/tmp/orchestrator-recorder-ns-XXXXXX.sh` from the prior architect test run. After removing that stale artifact, a clean re-run yielded **1346/1346 PASS, exit 0** — the abort was a test infrastructure issue, not a code regression.

---

## Acceptance Criteria Verification

### AC1 — DRAIN instead of STOP
*At ORCH_MAX_SPAWNS_PER_RUN: no new intake, in-flight tickets finish, ends clean (exit 0)*

| Test Assertion | Result |
|---------------|--------|
| A NEW intake at the exhausted soft cap is held (SKIP-DRAIN-INTAKE) | ✅ PASS |
| Reaching the soft cap without an extend enters DRAIN mode | ✅ PASS |
| An in-flight continuation still spawns at the exhausted soft cap (pipeline drains) | ✅ PASS |
| A soft-cap run ends CLEANLY (exit 0), not the exit-75 budget pause | ✅ PASS |
| The run logs entering DRAIN at the soft cap | ✅ PASS |
| The run logs a clean DRAIN-COMPLETE once in-flight work finished | ✅ PASS |
| A soft-cap drain never takes the exit-75 hard-pause path | ✅ PASS |

**AC1: PASS (7/7)**

Independent code review confirms: `DRAIN-COMPLETE` returns 10 from `one_cycle` (triggering the clean-exit path in `main()`), and `BUDGET_HALT` is NOT set in drain — so `main()` reaches `exit 0`, never the exit-75 budget pause.

---

### AC2 — Progress-aware auto-extend (ORCH_SPAWN_BUDGET_AUTOEXTEND, default on)
*Done-count watermark; +25% increments; PushNotification/Attention-Event with health picture*

| Test Assertion | Result |
|---------------|--------|
| Progress (Done rose) auto-extends the soft cap | ✅ PASS |
| The extension adds the increment to the remaining budget | ✅ PASS |
| A second extend needs FRESH progress (no double-extend on the same Done) | ✅ PASS |
| The extension emits a SPAWN-BUDGET-EXTEND runlog line | ✅ PASS |
| ORCH_SPAWN_BUDGET_AUTOEXTEND=0 never extends | ✅ PASS |

**AC2: PASS (5/5)**

Code review: `run_made_progress()` advances the `DONE_AT_LAST_CHECK` watermark on each successful check, requiring a FRESH Done increment per extension. The health picture (`spawn_budget_health()`) includes `x/y Done, spawns=N, cost=$Z`. `budget_event_push` calls `operator_push`.

---

### AC3 — Per-ticket spawn cap (ORCH_MAX_SPAWNS_PER_TICKET, default 25)
*Cyclic ticket → Needs PO Decision with escalation comment; run continues*

| Test Assertion | Result |
|---------------|--------|
| A ticket at the per-ticket cap emits BLOCK-TICKET-SPAWN-CAP | ✅ PASS |
| The capped ticket is escalated to Needs PO Decision | ✅ PASS |

**AC3: PASS (2/2)**

Code review: `TICKET_SPAWNS` is a string accumulator (`[<id>|<n>]` format, same idiom as the PENDING set). Per-ticket count is incremented at the single `record_daily_spawn` chokepoint. `block_for_ticket_spawn_cap` posts a comment + transitions in live mode.

---

### AC4 — Hard backstop preserved (exit-75 handshake)
*Absolute ceiling = soft cap × ORCH_SPAWN_BUDGET_HARD_MULTIPLE; SPAWNS_USED monotonic counter*

| Test Assertion | Result |
|---------------|--------|
| Auto-extend never crosses the hard backstop | ✅ PASS |
| The hard backstop brakes with SKIP-BUDGET | ✅ PASS |
| The hard backstop sets BUDGET_HALT (exit-75 handshake) | ✅ PASS |
| The hard-backstop pause names the ceiling in run.log | ✅ PASS |

**AC4: PASS (4/4)**

Code review: `hard_backstop_reached()` checks the MONOTONIC `SPAWNS_USED` counter (not `SPAWN_BUDGET`, which can be refilled by auto-extend). This means an auto-extended budget CANNOT slip past the absolute ceiling — fail-closed by design. `ORCH_MAX_SPAWNS_PER_RUN=0` makes the ceiling 0, preserving the ABS-455 "starve the budget" test path.

---

### AC5 — Exit-code/marker semantics preserved
*exit-75 + BUDGET-PAUSE for hard case; drain + auto-extend → runlog lines only, no new marker files*

| Test Assertion | Result |
|---------------|--------|
| Drain/auto-extend create NO new marker file under the state dir | ✅ PASS |

**AC5: PASS (1/1)**

Code review: `enter_drain_mode()` sets an in-memory flag (`DRAIN_MODE=1`) and writes `SPAWN-BUDGET-DRAIN` to the runlog only. `try_autoextend_budget()` writes `SPAWN-BUDGET-EXTEND` to the runlog only. Neither creates a file under `work/.orchestrator*`. SOP exit-code table updated to document drain → exit 0.

---

## DoD Checklist

- [x] All 5 acceptance criteria met and independently verified
- [x] Test suite: **1346/1346 PASS, exit 0** (clean scrubbed env)
- [x] 19 PILOT-47-specific assertions all green
- [x] `bash -n` syntax check clean
- [x] No harness/agents/skills changes → no provider mirror regen needed
- [x] SOP (`docs/sop/ORCHESTRATOR_SOP.md`) updated with 4 new knobs + revised cost gate section
- [x] Commit `2384f3e9` on `PILOT-47-auto`, reachable from `refs/heads/PILOT-47-auto`
- [x] No design flag → exit target is Story Acceptance

---

## Final Verdict

**APPROVED** — all 5 ACs met, full test suite green (1346/1346), implementation is pattern-compliant and fail-closed. Advancing to Story Acceptance.
