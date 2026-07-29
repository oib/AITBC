# QA Validation: ABS-598

**Ticket**: ABS-598 — Eine verweigerte LESE-Operation vergiftet die Session und verwirft 61 Turns Kontext  
**Branch**: ABS-598-auto  
**Commit**: e8220de013d421b7aa7b3646e59dbf2cb9d4aa97  
**Pushed to**: refs/remotes/gitlab/ABS-598-auto  
**QAS run**: 2026-07-27  
**Verdict**: **APPROVED**

---

## Acceptance Criteria Checklist

| AC | Description | Result | Evidence |
|----|-------------|--------|----------|
| AC1 | Denied read-only tools (Read, Grep, Glob) do NOT poison the session | ✅ PASS | 3/3 assertions below |
| AC2 | Denied mutating tools (Write, Edit, NotebookEdit, Bash) still poison, with tool+target in log | ✅ PASS | 3/3 assertions below |
| AC3 | SESSION-POISONED log names the triggering tool and target | ✅ PASS | 3/3 assertions below |
| AC4 | Regression test: denied Read → session stored + resumed with full cap; denied Write → session dropped | ✅ PASS | 4/4 assertions below |
| AC5 | Nebenbefund: salvage-cap=5 is too small for full-suite exit criteria | ✅ EVALUATED | Carved to ABS-605 (Backlog, parent ABS-604) by be-developer; ABS-605 verified to exist |

---

## Test Run Evidence

### AC1 + AC2 + AC3 — predicate-level unit tests

**Command**: `_SHARD_RANGE=2963:3031 bash tests/test-orchestrator.sh`  
**Commit**: e8220de0

```
=== ABS-598 read-only denials do not poison the session ===
  PASS  ABS-598 AC1: a denied Read does NOT poison
  PASS  ABS-598 AC1: a denied Grep does NOT poison
  PASS  ABS-598: an empty permission_denials array does NOT poison
  PASS  ABS-598 AC2: a denied Write poisons
  PASS  ABS-598 AC2: a denied Bash poisons
  PASS  ABS-598 AC2: a mixed Read+Edit denial poisons (the mutating one triggers)
  PASS  ABS-598 AC3: the log summary names the mutating tool + file target
  PASS  ABS-598 AC3: the log summary names a denied Bash command target
  PASS  ABS-598 AC3: a read-only denial yields no mutating summary
  PASS  ABS-598 AC4: a denied Read stores the session (full cap, no poison)
  PASS  ABS-598 AC4: a denied Read logs no SESSION-POISONED
  PASS  ABS-598 AC4: the read-denial session was stored and later resumed
  PASS  ABS-598 AC4: a denied Write drops the session
  PASS  ABS-598 AC3/AC4: the SESSION-POISONED log names the triggering mutating tool

##SHARDRESULT PASS=14 FAIL=0 TOTAL=14
```

### PILOT-38 — session_stored verdict tests (regression guard for session-poison classification)

**Command**: `SUITE_INCLUDE_ONLY=PILOT-38-close-session-verdict.sh bash tests/test-orchestrator.sh`  
**Commit**: e8220de0

```
=== PILOT-38 CLOSE session_stored = store_session's authoritative verdict ===
  PASS  PILOT-38 AC1: clean salvage + birth-denials (force_poison=1) -> session_stored=false
  PASS  PILOT-38: the same clean salvage WITHOUT force_poison reads true
  PASS  PILOT-38 AC1/AC2: the salvage+birth-denials corner serializes "session_stored":false
  PASS  PILOT-38 AC2: the corner never emits session_stored=true
  PASS  PILOT-38 AC3: normal birth (clean result, no force_poison) -> session_stored=true
  PASS  PILOT-38 AC3: poison-rejection (result carries permission_denials) -> session_stored=false
  PASS  PILOT-38 AC3: no-session (result carries no session id) -> session_stored=false
  PASS  PILOT-38 AC3: resume-off (ORCH_SESSION_RESUME=0) -> session_stored=false
  PASS  PILOT-38: the salvage resume threads the birth denials into run_spawn_cmd (SPAWN_FORCE_POISON)
  PASS  PILOT-38: the CLOSE recompute sources the authoritative verdict, honoring SPAWN_FORCE_POISON

  Total: 10  Passed: 10  Failed: 0
```

### ABS-254 — denial-poisoned session regression tests (the guard this ticket sharpens)

**Command**: `_SHARD_RANGE=2867:2961 bash tests/test-orchestrator.sh`  
**Commit**: e8220de0

```
  PASS  ABS-254: a clean spawn still stores its session (guard inert on the healthy path)
  PASS  ABS-254: the stored clean session was resumed (pre-condition for the drop)
  PASS  ABS-254: a denial-hit spawn stores no session — and drops the one it resumed
  PASS  ABS-254: the drop is a run.log event
  PASS  ABS-254: a denial-hit session is never resumed
  PASS  ABS-254: the next spawn starts fresh against the fixed permission surface
  PASS  ABS-254: ORCH_SESSION_POISON_GUARD=0 stores the denial-hit session anyway
  PASS  ABS-254: kill-switch off -> no drop event
  PASS  ABS-254: a denial+cap birth spawn still salvage-resumes (work is not discarded)
  PASS  ABS-254: the salvage produced a clean handoff
  PASS  ABS-254: the salvaged session is NOT stored — birth-spawn denials poison the resumed transcript
  PASS  ABS-254: the salvage-store drop is a run.log event
  PASS  ABS-254 control: a clean cap birth spawn salvage-resumes
  PASS  ABS-254 control: a clean salvage DOES store its session (the drop is birth-denial-driven)

##SHARDRESULT PASS=14 FAIL=0 TOTAL=14
```

---

## Code Review Summary

Files changed in e8220de0:
- `scripts/orchestrator.sh` — replaces `result_has_permission_denials` with `result_has_mutating_denial` (classifies by tool mutation property, not presence of any denial); adds `result_denied_tools`, `result_denial_summary`; adds `ORCH_MUTATING_DENIAL_TOOLS` env knob; updates `store_session` and `attempt_spawn` call sites; enriches SESSION-POISONED log with tool+target (AC3)
- `tests/test-orchestrator.sh` — adds ABS-598 section (14 assertions covering AC1–AC4 at predicate and E2E level)
- `tests/fixtures/stub-spawn.sh` — adds `readonly` mode for `STUB_PERMISSION_DENIALS` (a denied Read that should NOT poison)
- `tests/orchestrator.d/PILOT-38-close-session-verdict.sh` — updates `_p38_poison` fixture to use `tool_name` field (the real CLI JSON key) and a mutating tool (Bash) as required post-ABS-598
- `docs/sop/ORCHESTRATOR_SOP.md` — documents `ORCH_MUTATING_DENIAL_TOOLS`, updates `ORCH_SESSION_POISON_GUARD` entry, adds read-only-denials paragraph to Poisoned-session guard section

No RLS/auth/DB/payment surface. No harness mirror files touched. `bash -n scripts/orchestrator.sh` passes (verified by architect in In-Review stage).

---

## AC5 Disposition

AC5 asks: is `ORCH_SALVAGE_MAX_TURNS=5` sufficient for a station with a full-suite exit criterion?

The be-developer evaluated this on-ticket (comment 2026-07-27T17:13:00Z) and opened ABS-605 to carry the station-dependent cap + RTE turn-cap recalibration. ABS-605 is verified to exist (parent ABS-604, status Backlog). The evaluation is sound: ABS-598 removes the most frequent poison trigger, reducing pressure on the salvage path at the epic-integration station. The remaining cap work is a separate, measurable cut.

---

## Verdict

**APPROVED for Story Acceptance.**

All four testable ACs pass with 38 test assertions across three independent test runs (14 ABS-598 + 10 PILOT-38 + 14 ABS-254). AC5 is properly evaluated and tracked in ABS-605. No design flag; no blocking findings.

---

## Re-validation at branch tip c4f382ae (2026-07-27 — after ledger-fix commit)

**Commit validated**: `c4f382ae` (`fix(ledger): point R-1016 sensor at renamed result_has_mutating_denial`)  
**Change scope**: `docs/rule-ledger.yaml` only — 1 line (sensor name updated from `result_has_permission_denials` → `result_has_mutating_denial`). No orchestrator logic or test file changes.

### ABS-598 shard at c4f382ae

```
_SHARD_RANGE=2963:3031 bash tests/test-orchestrator.sh
```

```
=== ABS-598 read-only denials do not poison the session ===
  PASS  ABS-598 AC1: a denied Read does NOT poison
  PASS  ABS-598 AC1: a denied Grep does NOT poison
  PASS  ABS-598: an empty permission_denials array does NOT poison
  PASS  ABS-598 AC2: a denied Write poisons
  PASS  ABS-598 AC2: a denied Bash poisons
  PASS  ABS-598 AC2: a mixed Read+Edit denial poisons (the mutating one triggers)
  PASS  ABS-598 AC3: the log summary names the mutating tool + file target
  PASS  ABS-598 AC3: the log summary names a denied Bash command target
  PASS  ABS-598 AC3: a read-only denial yields no mutating summary
  PASS  ABS-598 AC4: a denied Read stores the session (full cap, no poison)
  PASS  ABS-598 AC4: a denied Read logs no SESSION-POISONED
  PASS  ABS-598 AC4: the read-denial session was stored and later resumed
  PASS  ABS-598 AC4: a denied Write drops the session
  PASS  ABS-598 AC3/AC4: the SESSION-POISONED log names the triggering mutating tool

##SHARDRESULT PASS=14 FAIL=0 TOTAL=14
```

### Rule-ledger at c4f382ae

```
bash scripts/rule-ledger-check.sh
# → rule-ledger-check: OK — every scoped rule section has a declared enforcement status.
# exit 0

bash tests/test-rule-ledger.sh
# → Total: 19  Passed: 19  Failed: 0  ALL TESTS PASSED
# exit 0
```

**Re-validation verdict**: APPROVED at c4f382ae. All AC1–AC4 assertions hold; R-1016 ledger sensor correctly points to `result_has_mutating_denial`.
