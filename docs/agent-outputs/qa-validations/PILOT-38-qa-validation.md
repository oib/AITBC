# QA Validation Report — PILOT-38

**Ticket:** PILOT-38 — seat_spawn CLOSE session_stored: source store_session's authoritative verdict  
**QAS seat:** qas  
**Date:** 2026-07-27  
**Commit:** `b95e9483` on branch `PILOT-38-auto`  
**Files changed:** `scripts/orchestrator.sh` (+52/-16), `tests/orchestrator.d/PILOT-38-close-session-verdict.sh` (+105)

---

## Validation Method

Independent re-run from the `PILOT-38-auto` worktree (`tmp/PILOT-38-work`).  
All tests driven without relying on the system-architect's reported results.

**PILOT-38 conformance (AC1/AC2):**
```
SUITE_INCLUDE_ONLY=PILOT-38-close-session-verdict.sh  bash tests/test-orchestrator.sh
Total: 10  Passed: 10  Failed: 0
```

**PILOT-27 regression (AC3):**
```
SUITE_INCLUDE_ONLY=PILOT-27-seat-session.sh  bash tests/test-orchestrator.sh
Total: 8  Passed: 8  Failed: 0
```

**Full staged suite (AC4) — ABS-285 back-to-back:**
- Baseline (merge-base `1a8889e8`): `orch-core` 741/741 PASS
- Branch `b95e9483` orch-core: 741/741 PASS
- Branch `b95e9483` stories: 55/55 PASS (all orchestrator.d includes)
- Branch `b95e9483` pool: 102/102 PASS
- `tests/staged-suite.sh --verify`: **GATE GREEN** — all 3 stages at HEAD

---

## Acceptance Criteria Verification

| AC | Criterion | Result | Evidence |
|----|-----------|--------|----------|
| AC1 | Clean salvage + birth-denials corner records `session_stored=false` | ✅ PASS | `PASS PILOT-38 AC1: clean salvage + birth-denials (force_poison=1) -> session_stored=false` |
| AC1 | Confirms pre-fix optimistic path: clean salvage alone (no force_poison) reads `true` | ✅ PASS | `PASS PILOT-38: the same clean salvage WITHOUT force_poison reads true` |
| AC1/AC2 | Producer→endpoint seam serializes `"session_stored":false` (JSON boolean) for the corner | ✅ PASS | `PASS PILOT-38 AC1/AC2: the salvage+birth-denials corner serializes "session_stored":false` |
| AC2 | Corner never emits `"session_stored":true` (no undercount) | ✅ PASS | `PASS PILOT-38 AC2: the corner never emits session_stored=true` |
| AC3 | Normal birth (clean, no force_poison) → `session_stored=true` — no regression | ✅ PASS | `PASS PILOT-38 AC3: normal birth (clean result, no force_poison) -> session_stored=true` |
| AC3 | Poison-rejection (result carries `permission_denials`) → `false` — no regression | ✅ PASS | `PASS PILOT-38 AC3: poison-rejection (result carries permission_denials) -> session_stored=false` |
| AC3 | No-session (result carries no session id) → `false` — no regression | ✅ PASS | `PASS PILOT-38 AC3: no-session (result carries no session id) -> session_stored=false` |
| AC3 | Resume-off (`ORCH_SESSION_RESUME=0`) → `false` — no regression | ✅ PASS | `PASS PILOT-38 AC3: resume-off (ORCH_SESSION_RESUME=0) -> session_stored=false` |
| AC3 | PILOT-27 suite (8/8) stays green | ✅ PASS | `Total: 8  Passed: 8  Failed: 0` |
| AC4 | Full suite: no new failing test names vs baseline | ✅ PASS | Baseline 741/741 PASS; branch orch-core 741/741, stories 55/55, pool 102/102 — zero new failures |

**All 4 ACs: PASS**

---

## Implementation Review

The fix introduces `session_stored_verdict()`, a single predicate that both the CLOSE
recompute and `store_session` read. It mirrors `store_session`'s existing poison-guard logic:
stores the session when resume is on, a session id is present, and neither `force_poison=1`
nor `result_has_permission_denials` fires.

`SPAWN_FORCE_POISON="$birth_denials"` threads the original birth spawn's denial state into
the salvage's `run_spawn_cmd` call, matching how `SPAWN_RESUME_ID` and
`SPAWN_MAX_TURNS_OVERRIDE` already carry birth-context into the salvage. The salvage's
own clean output no longer overwrites the drop that `store_session` already decided.

Direct paths pass `SPAWN_FORCE_POISON` unset (defaults to `0`), preserving their existing
behaviour exactly — confirmed by AC3's 8 assertions.

No schema, API contract, UI, or session-resume semantics changed. Out-of-scope items
(PILOT-24, ABS-535, ABS-195) are untouched.

---

## Verdict

**APPROVED for RTE.**

Commit `b95e9483` on `PILOT-38-auto` satisfies all four acceptance criteria. Full staged
suite green at HEAD with no new failures vs the merge-base baseline.
