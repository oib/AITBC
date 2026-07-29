# QA Validation Report — PILOT-20

**Date**: 2026-07-24  
**Ticket**: PILOT-20 — Runner: DECLINED story PR rests at Ready for Merge forever — distinct human escalation  
**Branch**: PILOT-20-auto  
**Commit**: a3ad2612ebacaf53d6d5340587a0dcd0853f1ab3  
**Verdict**: ✅ **APPROVED**

---

## Scope

Pure orchestrator shell code change (`scripts/orchestrator.sh` + tests). No DB/RLS/auth/migration/frontend surface — those criteria are N/A by construction.

**Files changed in PILOT-20 commit (a3ad2612)**:
- `scripts/orchestrator.sh` — `story_pr_state` now surfaces `DECLINED` distinctly; new `merge_wait_declined_gate` sibling gate; wired into `reconcile` sweep
- `tests/test-merge-wait.sh` — PILOT-20 AC1–AC4 cases added (58 lines)
- `tests/test-done-gate.sh` — `story_pr_state` contract assertion updated

---

## Syntax Check

```
bash -n scripts/orchestrator.sh → CLEAN
```

---

## Test Suite Results (Green-run proof — AC5)

All three mandated suites run from the PILOT-20-auto worktree at commit `a3ad2612`:

| Suite | Command | Result |
|---|---|---|
| test-merge-wait.sh | `bash tests/test-merge-wait.sh` | **70/70 PASS** |
| test-done-gate.sh | `bash tests/test-done-gate.sh` | **33/33 PASS** |
| test-epic-join-resting.sh | `bash tests/test-epic-join-resting.sh` | **25/25 PASS** |

---

## Acceptance Criteria Verification

### AC1 — DECLINED PR emits a distinct human escalation exactly once

```
PASS AC1: a declined PR at the merge gate ESCALATES (rc 0)
PASS AC1: intent is a distinct DECLINED escalation, not a release/self-heal
PASS AC1: emits a kind: notification comment to the human
PASS AC1: the notification NAMES the declined PR ref (#173)
PASS AC1: the notification identifies the PR as DECLINED / closed-without-merge
PASS AC1 (option-a default): the story keeps resting at the human-owned gate — no transition
```

**Result**: ✅ PASS — `merge_wait_declined_gate` fires on `DECLINED`, emits `kind: notification` naming the PR ref. `#PATH_DECISION` default honored (notification only, no `Blocked` transition). ADR-A-0005 preserved (runner never merges).

### AC2 — OPEN PR: no escalation, story keeps resting (ABS-270 preserved)

```
PASS AC2: an OPEN (still-awaiting) PR is NOT escalated (rc 1)
PASS AC2: no escalation intent for an open PR
PASS AC2: no adapter writes — the story keeps resting (ABS-270 behavior preserved)
```

**Result**: ✅ PASS — ABS-270 "green awaiting-merge rest" behavior untouched for OPEN state.

### AC3 — MERGED PR: merge_wait_release still releases to Docs

```
PASS AC3: a MERGED PR is not escalated by this gate (merge_wait_release releases it)
PASS AC3: no writes on a merged PR
```

Also corroborated by test-done-gate.sh 33/33 and test-merge-wait.sh MERGED release path assertions.

**Result**: ✅ PASS — ABS-270 auto-resume on MERGED not regressed.

### AC4 — Idempotent: second sweep over already-escalated story is a no-op

```
PASS AC4: a second sweep over an already-escalated declined story is a no-op (rc 1)
PASS AC4: no duplicate notification is emitted on re-invocation
```

Idempotency guard: `grep -qF "MERGE-WAIT DECLINED"` in the ticket dump — established `grep -qF` marker idiom (matches sibling gates L5054/L5451).

**Result**: ✅ PASS

### AC5 — Full suite green (no regression to merge-wait / done / epic-join-resting behavior)

All three suites: **70/70 + 33/33 + 25/25 = 128 assertions, 0 failures**.

**Result**: ✅ PASS

---

## Additional Scoping Verifications (from test output)

```
PASS a declined PR on a ticket NOT at the merge gate is never escalated
PASS no $FORGE_CMD (placeholder) -> no DECLINED signal, no escalation
PASS dry-run still reports the declined-escalation intent (rc 0)
PASS dry-run logs the escalation intent
PASS dry-run makes NO tracker comment calls
```

---

## Architecture Compliance

| Check | Status |
|---|---|
| `merge_wait_declined_gate` follows sibling gate shape | ✅ Pattern-conformant |
| Dump-marker idempotency via `grep -qF` idiom | ✅ Matches established idiom |
| `DECLINED` superset-split of old `OPEN` bucket | ✅ No existing consumer broken |
| ADR-A-0005 (runner never merges) | ✅ Notify-only, no merge action |
| ABS-270 not regressed | ✅ OPEN rests, MERGED auto-resumes |
| Gate wired in reconcile sweep (after ready_for_merge_mr_gate) | ✅ Correct placement |
| `ready_for_merge_mr_gate` fires on NONE only — declined PR still exists, no double-fire | ✅ Disjoint |

---

## Final Verdict

**APPROVED** — All 5 ACs met, 128/128 test assertions passing at commit `a3ad2612`, `bash -n` clean. No design/security/data flags. No regressions to ABS-270, ABS-211, ABS-73. Releasing to Story Acceptance.
