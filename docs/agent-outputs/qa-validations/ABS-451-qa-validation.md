# QA Validation Report — ABS-451

**Ticket**: ABS-451 — Retro: TDM-Resume-Ziel muss spawnbar sein — In-Progress-Dead-End beheben  
**Branch**: ABS-451-auto  
**HEAD commit**: 1b72a67  
**QAS run date**: 2026-07-19  
**Verdict**: ✅ APPROVED

---

## Files Changed (diff main...ABS-451-auto)

| File | Purpose |
|------|---------|
| `harness/claude/agents/tdm.md` | AC1 — duty-5 resume-target rule |
| `agent_providers/claude_code/prompts/tdm.md` | AC1 — provider mirror (ABS-317 guard) |
| `scripts/orchestrator.sh` | AC2 — `heal_inprogress_orphan()` + `check_stuck()` hook |
| `tests/orchestrator.d/ABS-451-inprogress-orphan-heal.sh` | AC2 — new conformance suite (15 tests) |
| `tests/test-orchestrator.sh` | AC3 — legacy ABS-116/ABS-195 blocks re-pinned with `ORCH_INPROGRESS_HEAL_SWEEPS=0` |

---

## Acceptance Criteria Verification

### AC1 — TDM role definition contains the resume-target rule with status mapping ✅ PASS

**Evidence verified:**
- `harness/claude/agents/tdm.md` duty-5 heading changed from "Resume to origin" → "Resume to a SPAWNABLE status"
- `In Progress` explicitly declared forbidden as a resume target with rationale (ABS-417 3× in 12h, ABS-438)
- Status mapping table present with all required entries:
  - `In Progress` (dev work) → **`Ready for Development`**
  - `In Review` / `In Test` (QAS repetition) → **`In Test`**
  - epic `Grooming` / groom stages → recorded groom stage
  - any already-spawnable status → resume as recorded
- "Safe spawnable default = `Ready for Development`" stated
- Exit transitions block and handoff format updated to reference spawnable target (never `In Progress`)
- `agent_providers/claude_code/prompts/tdm.md` is byte-identical to source (`diff` = 0 output; ABS-317 guard satisfied)

### AC2 — Runner test: unowned In Progress auto-healed after 3 sweeps (comment + transition); conformance test green ✅ PASS

**Implementation verified:**
- `ORCH_INPROGRESS_HEAL_SWEEPS` knob added (default 3; 0 = pure ABS-116 NOTIFY-only fallback)
- `heal_inprogress_orphan()` function: confirms status still In Progress, defers on SPAWN-CRASH marker (ABS-295 owns that path), emits `INPROGRESS-HEAL` intent, posts `gate-results` audit comment, executes transition to `Ready for Development`
- `check_stuck()` hook: invokes `heal_inprogress_orphan` only when status=`In Progress`, knob>0, count≥threshold; calls `clear_stuck_row` on success to reset the episode

**New conformance suite `tests/orchestrator.d/ABS-451-inprogress-orphan-heal.sh` — 15/15 PASS:**
- Sweep 1 & 2: no premature heal (below threshold) ✅
- Sweep 3: `INTENT INPROGRESS-HEAL` emitted, target = `Ready for Development` ✅
- Status confirmed `Ready for Development` post-transition ✅
- Gate-results audit comment present on ticket ✅
- Idempotency: no double-heal after ticket leaves In Progress ✅
- Knob-off (`=0`): no heal fires, ABS-116 NOTIFY preserved ✅
- Owned lock guard: locked In Progress not a heal candidate ✅
- SPAWN-CRASH deferral: heal defers to ABS-295 CRASH-REPAIR ✅

**Syntax checks:** `bash -n scripts/orchestrator.sh` → OK; `bash -n tests/orchestrator.d/ABS-451-inprogress-orphan-heal.sh` → OK

### AC3 — Existing suites remain green ✅ PASS

**Full test run result:**
```
Total:  1229
Passed: 1229
Failed: 0
ALL TESTS PASSED
```

- ABS-116 block re-pinned with `ORCH_INPROGRESS_HEAL_SWEEPS=0` (preserves NOTIFY-only safety net assertion; heal-ON path covered by new ABS-451 suite)
- ABS-195 block re-pinned with `ORCH_INPROGRESS_HEAL_SWEEPS=0` (same rationale; both updates include explanatory comments)
- Exit code 0

---

## Architecture Review Cross-check

System Architect approved (Stage 1, Iteration 1 of 3) verifying:
- ADR-A-0004 "eyes not hands" not reopened — heal routes to spawnable status for a FRESH seat, not a session-resume of the dead seat
- ABS-295 CRASH-REPAIR precedence correct (SPAWN-CRASH marker = defer)
- ABS-296 interaction handled via `clear_stuck_row()` post-heal
- ABS-116 NOTIFY safety net preserved via knob=0
- Knob-gating follows house pattern (ORCH_STUCK_SWEEPS / ORCH_CRASH_REPAIR_SECONDS)
- No `design` flag → exit target: **Story Acceptance**

---

## Summary

| Check | Result |
|-------|--------|
| AC1: TDM duty-5 resume-target rule + mapping | ✅ PASS |
| AC1: Provider mirror byte-identical (ABS-317) | ✅ PASS |
| AC2: `heal_inprogress_orphan()` + `check_stuck()` hook | ✅ PASS |
| AC2: 15/15 new conformance tests green | ✅ PASS |
| AC3: 1229/1229 existing tests green | ✅ PASS |
| bash -n syntax clean | ✅ PASS |

**Verdict: APPROVED — Releasing to Story Acceptance**
