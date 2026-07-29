# QA Validation Report — PILOT-10

**Ticket**: PILOT-10 — RTE hard guard: Automerge darf nie main treffen  
**Validator**: QAS  
**Date**: 2026-07-22  
**Commit under test**: `c2da5548e7245af43fd0b08cfe32b2b9c4e7350b`  
**Branch**: `PILOT-10-auto`  
**Verdict**: ✅ **APPROVED**

---

## Green-Run Proof (ABS-453)

Test file added: `tests/test-merge-target-guard.sh`

**Command run:**
```
bash tests/test-merge-target-guard.sh
```

**Output (verbatim):**
```
=== RTE merge-target guard (PILOT-10) ===

A. AC1 — main refused, epic allowed, both with ORCH_AUTOMERGE=1
  PASS target main + ORCH_AUTOMERGE=1 -> REFUSE (exit 1)
  PASS target main -> prints MERGE-GUARD-REFUSE ... action=hitl-handoff (intent line)
  PASS target epic/PILOT-10-x + ORCH_AUTOMERGE=1 -> ALLOW (exit 0)
  PASS target origin/main -> REFUSE (normalised, exit 1)
  PASS target refs/heads/main -> REFUSE (normalised, exit 1)
  PASS target master -> REFUSE (default protected set, exit 1)

B. AC2 — refuse is invariant across every ORCH_AUTOMERGE state
  PASS main, ORCH_AUTOMERGE unset -> REFUSE (exit 1)
  PASS main, ORCH_AUTOMERGE='' (empty) -> REFUSE (exit 1)
  PASS main, ORCH_AUTOMERGE=1 -> REFUSE (exit 1)
  PASS main, ORCH_AUTOMERGE=0 -> REFUSE (exit 1)
  PASS epic/*, ORCH_AUTOMERGE unset -> ALLOW (exit 0)

C. operator override + bad input
  PASS custom ORCH_PROTECTED_BRANCHES catches 'trunk' -> REFUSE (exit 1)
  PASS custom set excludes 'master' -> ALLOW (exit 0)
  PASS missing target -> exit 64 (usage, fails closed on bad input)
  PASS unknown subcommand -> exit 64

=== Results ===
  Total:  15
  Passed: 15
  Failed: 0

All merge-target-guard tests passed.
```

**Pass counter**: 15 passed, 0 failed  
**Commit hash**: `c2da5548e7245af43fd0b08cfe32b2b9c4e7350b`

---

## AC Verification

### AC1: Conformance test — main refused, epic allowed
**Status**: ✅ PASS

Evidence from green run:
- `target main + ORCH_AUTOMERGE=1 -> REFUSE (exit 1)` → PASS
- `target main -> prints MERGE-GUARD-REFUSE ... action=hitl-handoff (intent line)` → PASS  
- `target epic/PILOT-10-x + ORCH_AUTOMERGE=1 -> ALLOW (exit 0)` → PASS

The guard emits `MERGE-GUARD-REFUSE target=main automerge=1 action=hitl-handoff` on stdout (machine-greppable intent line). The stderr message explicitly instructs HITL handoff. Exit 0 for `epic/*` targets confirms automerge remains permitted on epic branches.

### AC2: Guard is invariant across all ORCH_AUTOMERGE states
**Status**: ✅ PASS

Section B of the test suite covers all four states:
- `ORCH_AUTOMERGE` unset → REFUSE ✅
- `ORCH_AUTOMERGE=''` (empty) → REFUSE ✅
- `ORCH_AUTOMERGE=1` → REFUSE ✅
- `ORCH_AUTOMERGE=0` → REFUSE ✅

The implementation confirms this: `cmd_check()` in `scripts/merge-target-guard.sh` never reads `ORCH_AUTOMERGE` for the protection decision — it only inspects the target branch against `ORCH_PROTECTED_BRANCHES`.

### AC3: QA evidence cites the green run per ABS-453 rules
**Status**: ✅ PASS

This document contains:
- The command run: `bash tests/test-merge-target-guard.sh`
- The pass/fail counter: `15 passed, 0 failed`
- The commit hash: `c2da5548e7245af43fd0b08cfe32b2b9c4e7350b`

---

## Scope Completeness

All five changed files inspected:

| File | Change | Assessment |
|------|--------|------------|
| `scripts/merge-target-guard.sh` | NEW — guard implementation | ✅ Correct; fail-closed; never reads ORCH_AUTOMERGE for decision; normalises `origin/main` / `refs/heads/main`; shared `ORCH_PROTECTED_BRANCHES` contract |
| `tests/test-merge-target-guard.sh` | NEW — 15-assert conformance suite | ✅ Fully covers AC1 + AC2; bad-input / fail-closed cases included |
| `agent_providers/claude_code/prompts/rte.md` | Duty step 4 added | ✅ MANDATORY mechanical guard instruction; references guard script + HITL handoff |
| `harness/claude/agents/rte.md` | Mirror of above | ✅ Parity with provider prompt (mirror drift compliant) |
| `docs/sop/ORCHESTRATOR_SOP.md` | ORCH_AUTOMERGE scope + guard docs | ✅ Epic-branch-only scope documented; ORCH_PROTECTED_BRANCHES knob documented |

---

## System Architect Advisory Follow-ups (Non-blocking, recorded for traceability)

1. **MEDIUM** — guard invocation is still prose in the duty step; a truly seat-independent enforcement (Bash-permission deny routing `bb`/`glab` merge commands through the guard) is a distinct future enabler.
2. **LOW** — the epic-less-lane duty-step arg wording uses `$EPIC_BRANCH` when the parentless story has no epic branch; future clarity improvement.

Neither constitutes an AC violation or regression.

---

## Verdict

**✅ APPROVED** — All three ACs are met. Green run: 15/15 at commit `c2da5548`. No design flag → releasing to Story Acceptance.
