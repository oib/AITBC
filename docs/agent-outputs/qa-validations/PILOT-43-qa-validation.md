# QA Validation Report — PILOT-43

**Ticket**: PILOT-43 — Ops-Sweep Tier A+B: Worktree-/Lock-Hygiene und evidenzgebundene Tracker-Auflösung scharf schalten  
**Validator**: QAS  
**Date**: 2026-07-26  
**Commit under review**: `dc4ca0db` — feat(orchestrator): activate ops-sweep Tier A+B (shadow phase over) [PILOT-43]  
**Branch**: `PILOT-43-auto` (also on `remotes/gitlab/PILOT-43-auto`)  
**Verdict**: ✅ **APPROVED**

---

## Test Suite Results

```
Suite: tests/test-orchestrator.sh (from PILOT-43-auto worktree)
Environment: BACKEND_URL, BACKEND_TOKEN, TRACKER_CMD, ORCH_INSTANCE_ID unset
             (operator guardrail — prevents prod-backend pollution)
TEST_JOBS=4 (parallel shards, default)
Commit: dc4ca0db

Total:   1340
Passed:  1340  ✅
Failed:  0
Exit:    0 (ALL TESTS PASSED)
```

### PILOT-43 Shard (6/6 PASS)

```
PASS  PILOT-43: sweep fires when due
PASS  PILOT-43 FALSIFICATION: no ORCH_OPS_SWEEP_TIERS => stays Phase-0 shadow (not activated)
PASS  PILOT-43: ORCH_OPS_SWEEP_TIERS=A => phase=1 tiers=A
PASS  PILOT-43: ORCH_OPS_SWEEP_TIERS=ab => phase=2 tiers=AB (case-insensitive)
PASS  PILOT-43: junk ORCH_OPS_SWEEP_TIERS => degrades to shadow, never mis-activates
PASS  PILOT-43: interval 0 => no sweep even with tiers set (byte-identical to legacy)
```

### PILOT-42 Shard (7/7 PASS)
```
PASS  PILOT-42 AC1: knob 0 => no ops-sweep dispatch
PASS  PILOT-42 AC1: knob 0 => no cadence marker written (byte-identical)
PASS  PILOT-42: first sweep seeds cadence, no immediate dispatch
PASS  PILOT-42: first sweep seeds the cadence marker
PASS  PILOT-42: not due (elapsed < interval) => no dispatch
PASS  PILOT-42: cadence elapsed => OPS-SWEEP dispatched (reason ops-sweep, TDM seat)
PASS  PILOT-42: outage pause suppresses the ops-sweep (never fight recovery)
```

---

## AC Verification

### Core Ticket ACs

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 1 | Tier A — main-HEAD reset only clean tree + branch on live remote | ✅ PASS | In `ops_sweep_packet()` Phase 1 and `tdm.md` Tier A: "ONLY when its tree is clean AND the story branch is already safe on the live remote" |
| 2 | Tier A — orphaned worktree removal | ✅ PASS | `tdm.md` Tier A: "Remove an orphaned worktree (its path is gone / no live seat owns it)" |
| 3 | Tier A — stale lock/outage-marker clearing | ✅ PASS | `tdm.md` Tier A: "Clear a stale lock or outage/fastfail marker whose owning PID is dead or whose window has elapsed" |
| 4 | Tier B — dep-release with merge-fact evidence (also handles Origin=Backlog) | ✅ PASS | `tdm.md` Tier B: `git merge-base --is-ancestor` check; "origin was Backlog — closes the Pilot-#5 gap the auto-release misses" |
| 5 | Tier B — NOMOVE-Vollzug with provenance verification | ✅ PASS | `tdm.md` Tier B: role+verdict+timestamp against handoff required; fail-closed on mismatch |
| 6 | Every action: evidence comment + OPS-SWEEP-DONE idempotency marker | ✅ PASS | 5-step loop in `tdm.md`; marker format: `OPS-SWEEP-DONE[<class>:<key>]` |
| 7 | Hard prohibitions: no merge/push to protected, no --force, no delete-without-backup, no force-transition, no live-seat intervention | ✅ PASS | Enumerated in both `ops_sweep_packet()` Phase 1+2 and `tdm.md` Hard prohibitions section |
| 8 | N-findings-per-class => escalate (`ORCH_OPS_SWEEP_MAX_PER_CLASS=3`) | ✅ PASS | Knob defined in `orchestrator.sh`, documented in SOP, referenced in packet; `tdm.md` runaway cap step 5 |
| 9 | AC-Falsifikation: real Blocked (dep-head NOT in target branch) must NOT be released | ✅ PASS | `tdm.md`: "A Blocked whose dep head is NOT in the target branch is a REAL block — leave it, never release it (fail-closed)". Backed mechanically by PILOT-40 dep-release-due sensor. Test PILOT-43 FALSIFICATION asserts shadow by default. |

### Operator Extra ACs (2026-07-25T15:10:46Z notification — NOMOVE-Vollzug)

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 10 | Draft provenance MUST be verified: role + verdict + timestamp vs. announcing handoff | ✅ PASS | `tdm.md` Tier B NOMOVE section |
| 11 | If provenance cannot be shown: do NOT post, escalate (fail-closed) | ✅ PASS | `tdm.md`: "If provenance does not hold or cannot be shown, do NOT post: escalate" |
| 12 | Post under the role that AUTHORED the draft, never guessed | ✅ PASS | `tdm.md`: "Post under the role that AUTHORED the draft, never a guessed one" |
| 13 | Stale foreign-role scratch note → sweep does NOT post, escalates | ✅ PASS | Documented in `tdm.md` NOMOVE section |

### Structural Checks

| Check | Status | Evidence |
|-------|--------|----------|
| Default-OFF: unset/empty ORCH_OPS_SWEEP_TIERS = Phase-0 shadow (byte-identical) | ✅ PASS | Test PILOT-43 FALSIFICATION + knob default `ORCH_OPS_SWEEP_TIERS="${ORCH_OPS_SWEEP_TIERS:-}"` |
| Harness↔provider mirror parity (Rule 10) | ✅ PASS | `diff harness/claude/agents/tdm.md agent_providers/claude_code/prompts/tdm.md` = identical |
| Knob-drift guard: all 6 ORCH_OPS_SWEEP_* knobs documented in ORCHESTRATOR_SOP.md | ✅ PASS | SOP table updated; system-architect confirmed guard is GREEN |
| Junk tier value degrades to shadow (typo safety) | ✅ PASS | Test "junk ORCH_OPS_SWEEP_TIERS => degrades to shadow, never mis-activates" |
| Case-insensitive tier parsing (`ab` → `AB`) | ✅ PASS | Test "ORCH_OPS_SWEEP_TIERS=ab => phase=2 tiers=AB" |

---

## Architecture Review Non-Blocking Finding

System-architect noted one MEDIUM non-blocking finding (not a bounce criterion):
- **ABS-296 zero-commit trivial-ancestor gap**: The PILOT-40 dep-release-due sensor has no zero-commit guard. Recommend a fast-follow before enabling `ORCH_OPS_SWEEP_TIERS=AB` in a live run. The change is default-off so no live risk exists as shipped.
- **Action required**: Advisory — do NOT set `ORCH_OPS_SWEEP_TIERS=AB` in a live run until ABS-296 zero-commit guard lands.

---

## Files Changed (commit dc4ca0db)

```
scripts/orchestrator.sh                          | 74 +++++++++++++++++++++++--
harness/claude/agents/tdm.md                     | 60 ++++++++++++++++++-
agent_providers/claude_code/prompts/tdm.md       | 60 ++++++++++++++++++-
docs/sop/ORCHESTRATOR_SOP.md                     |  6 ++
tests/orchestrator.d/PILOT-43-ops-sweep-tiers.sh | 70 ++++++++++++++++++++++
5 files changed, 260 insertions(+), 10 deletions(-)
```

---

## Verdict

**✅ APPROVED — Story Acceptance**

All 13 ACs pass. Full test suite 1340/1340 (exit 0). Mirror parity confirmed. Knob-drift guard green. The one architecture advisory (ABS-296 zero-commit gap) is non-blocking — the knob is default-off and creates no live risk as shipped.

No `design` flag on the ticket → exit target: **Story Acceptance**.
