# QA Validation — PILOT-63

**Ticket**: PILOT-63 — Zaehler: fehlgeschlagene Admissions duerfen kein Budget kosten + Work-Credit einschalten  
**Commit**: `04043b7e` on `PILOT-63-auto`  
**QAS run date**: 2026-07-26  
**Verdict**: **APPROVED**

---

## Evidence chain

### Commit reachability
```
git cat-file -e 04043b7e^{commit}  → exists
git for-each-ref --contains 04043b7e:
  04043b7e9f433c2270411a277f245ec983055f5f commit refs/heads/PILOT-63-auto
  04043b7e9f433c2270411a277f245ec983055f5f commit refs/remotes/gitlab/PILOT-63-auto
```

### bash -n syntax check
```
bash -n scripts/orchestrator.sh → SYNTAX OK
```

---

## AC1 — failed admission costs no budget unit

**Criterion**: A spawn that never reaches a model (worktree failure, kill-switch, phantom-event, lock) costs no budget unit. Decrement only after successful handoff to seat.

**Verification**: Read `scripts/orchestrator.sh` lines 8870–8930.

`spawn_dispatch` resets `SPAWN_CWD=""` at line 8881, then calls `provision_seat_worktree()` at line 8883 before the budget block. On failure, `release_lock` + `return 0` fires with no charge. The budget increments (`LIVE_SPAWNS`, `SPAWN_BUDGET`, `SPAWNS_USED`, `ticket_spawn_incr`, `record_daily_spawn`) sit at lines 8889–8893, after the provisioning gate. Every other never-reached-a-model path (kill-switch, outage, halt, backoff, single-flight lock, concurrency cap, lost claim) already returned above line 8883, so worktree failure was the sole leak — now closed.

`live_spawn` retains a defense-in-depth gate at line 9884 for direct/resume callers where `SPAWN_CWD` may be unset.

**Result**: ✅ PASS

---

## AC2 — ORCH_ESCALATION_WORK_CREDIT default-on

**Criterion**: `ORCH_ESCALATION_WORK_CREDIT` defaults to 1 (on), with documented signal.

**Verification**: `scripts/orchestrator.sh` line 2702:
```bash
ORCH_ESCALATION_WORK_CREDIT="${ORCH_ESCALATION_WORK_CREDIT:-1}"
```
SOP table entry updated: "1 (ADR-A-0018; on by default, PILOT-63 AC2)". Signal documentation confirms two sources: runner-verified commits (strong, unbounded) and bounded self-asserted `progress:` markers (ADR-A-0018).

Dependent test `ABS-311-escalation-work-credit.sh` sets the var explicitly → immune to the default change.

**Result**: ✅ PASS

---

## AC3 — ORCH_MAX_SPAWNS_PER_DAY recalibrated 200 → 400

**Criterion**: Daily cap recalibrated based on measured usage (Pilot 4: 161, Pilot 5: 251 — one epic wave exceeded the shipped default of 200).

**Verification**: `scripts/orchestrator.sh` line 7348:
```bash
ORCH_MAX_SPAWNS_PER_DAY="${ORCH_MAX_SPAWNS_PER_DAY:-400}"
```
SOP table entry: "400 (`0` off) | Per-day spawn cap... Recalibrated from 200 (PILOT-63 AC3): measured runs consumed 161–251, so one epic wave overran the old default."

Knob-drift test: **4/4 PASS** — all `ORCH_*` knobs read in `scripts/` are documented in the SOP.

**Operator note (non-blocking, from architect review)**: 400 is a judgment above the observed max (251) with headroom, not a measured value. PO/operator may confirm against the ~2-epics/day sizing intent.

**Result**: ✅ PASS

---

## AC4 — falsification: N failed worktree provisions → budget unchanged

**Criterion**: Fixture with N failed worktree provisionings → daily budget ledger stays unchanged. Non-vacuous (positive control proves a real spawn charges exactly 1 unit).

**Test file**: `tests/orchestrator.d/PILOT-63-failed-admission-budget.sh`

**Mechanism**: Branch `$Tfail-auto` is pre-occupied in the repo so `git worktree add` fails with "already checked out elsewhere" — a representative provisioning failure identical to the C9b fail-closed path.

**Run output** (this seat, `SUITE_INCLUDE_ONLY`, env-scrubbed):
```
PASS  PILOT-63 AC4: worktree provisioning fails closed (attempt 1)
PASS  PILOT-63 AC4: no spawn reached a seat on the failed provisioning (attempt 1)
PASS  PILOT-63 AC4: worktree provisioning fails closed (attempt 2)
PASS  PILOT-63 AC4: no spawn reached a seat on the failed provisioning (attempt 2)
PASS  PILOT-63 AC4: worktree provisioning fails closed (attempt 3)
PASS  PILOT-63 AC4: no spawn reached a seat on the failed provisioning (attempt 3)
PASS  PILOT-63 AC4: 3 failed worktree provisionings charged 0 budget units (daily ledger unchanged)
PASS  PILOT-63 AC4 control: a spawn that reaches a seat charges exactly one budget unit

Total: 8  Passed: 8  Failed: 0
```

**Result**: ✅ PASS (8/8, non-vacuous)

---

## ABS-455 regression pin

`ABS-455-budget-pause-handshake.sh` (pinned to its own cap by the implementer after AC3 changed the default):

```
PASS  ABS-455 AC3: budget exhaustion exits with restart-handshake code (default 75)
PASS  ABS-455 AC1: clear budget-pause exit line emitted
PASS  ABS-455 AC3: exit line names restart counter
PASS  ABS-455 AC3: restart counter persisted in state dir
PASS  ABS-455 AC3: second budget pause exits with same handshake code
PASS  ABS-455 AC3: each budget pause bumps persisted restart counter
PASS  ABS-455 AC3: ORCH_BUDGET_PAUSE_EXIT_CODE overrides handshake code
PASS  ABS-455 AC2: budget-caused standstill exits with handshake code
PASS  ABS-455 AC2: standstill-without-exit path converted to clean budget-pause exit
PASS  ABS-455 AC2: budget standstill never reaches forever-hold state

Total: 10  Passed: 10  Failed: 0
```

**Result**: ✅ PASS (10/10)

---

## Regression check — stories stage

All 52 `tests/orchestrator.d/*.sh` includes ran via `bash tests/staged-suite.sh --stage stories` (env-scrubbed, run on commit `04043b7e`):

```
=== all 52 story includes PASSED ===
stage stories PASSED (126s) — recorded at HEAD 04043b7e9f43
```

**Result**: ✅ PASS — no regressions

---

## Summary

| AC | Criterion | Result |
|----|-----------|--------|
| AC1 | Failed admission (worktree) costs no budget unit | ✅ PASS |
| AC2 | ORCH_ESCALATION_WORK_CREDIT default 0→1 + documented signal | ✅ PASS |
| AC3 | ORCH_MAX_SPAWNS_PER_DAY 200→400 + SOP updated | ✅ PASS |
| AC4 | Falsification: 3 failed provisions → ledger 0; positive control charges 1 | ✅ PASS (8/8) |
| ABS-455 pin | Budget-pause handshake unbroken | ✅ PASS (10/10) |
| Knob-drift | All ORCH_* knobs documented | ✅ PASS (4/4) |
| bash -n | Syntax clean | ✅ PASS |
| Stories stage | No regressions | ✅ PASS (52/52) |

**Verdict: APPROVED** — all acceptance criteria met, no regressions, commit `04043b7e` on `PILOT-63-auto` ready for Story Acceptance.
