# QA Validation Report — PILOT-15

**Ticket**: PILOT-15 — Forward-Fix: test-local-main-guard AC3 auf Active-Remote-Muster
**Branch**: PILOT-15-auto
**Commit under test**: `a1cf72d1a0a558d7cf80b5ebbb160fb43a795fb3`
**Validator**: QAS
**Date**: 2026-07-23
**Verdict**: ✅ APPROVED

---

## Evidence: Commit Boundary (AC3)

```
$ git diff --stat HEAD~1 HEAD
 tests/test-local-main-guard.sh | 10 +++++++---
 1 file changed, 7 insertions(+), 3 deletions(-)
```

**AC3**: ✅ PASS — diff touches exclusively `tests/` (single file, test-only, no production code).

---

## Evidence: AC1 — tests/test-local-main-guard.sh (31/31 green)

Command run: `bash tests/test-local-main-guard.sh`
Commit: `a1cf72d1a0a558d7cf80b5ebbb160fb43a795fb3`

```
=== seats never commit to local main (ABS-224) ===

AC1/AC4 — pre-commit guard logic (direct hook invocation)
  PASS seat (ORCH_SEAT) on main -> BLOCKED
  PASS seat on master -> BLOCKED
  PASS seat via ORCH_ROLE on main -> BLOCKED
  PASS seat via ORCH_TICKET on main -> BLOCKED
  PASS seat on story branch ABS-1-auto -> allowed
  PASS HUMAN (no seat env) on main -> allowed (AC1)
  PASS kill switch off -> allowed (AC4)

AC1 — end-to-end: a real seat git commit on local main is aborted
  PASS installer wrote an executable pre-commit hook
  PASS installed hook carries the guard marker
  PASS human commit on local main is allowed (no seat env)
  PASS seat commit on local main is REJECTED by the installed hook (AC1)
  PASS seat commit on the story branch ABS-1-auto is allowed (AC1)

AC4 — kill switch: installer removes its own guard, leaves foreign hooks
  PASS kill switch off -> installer removed the guard hook
  PASS foreign pre-commit hook is left untouched (fail-open)

AC3 — check_local_main_drift warns when local main is ahead of origin
  PASS drift emits a LOCAL-MAIN-DRIFT intent
  PASS drift reports ahead=1
  PASS in-sync local main -> no drift warning
  PASS kill switch off -> drift check no-ops (AC4)

PILOT-3 — drift compares against the ACTIVE push remote, one WARN per run
  PASS in sync with ACTIVE remote -> no drift despite stale origin +2 (PILOT-3)
  PASS ORCH_MAIN_REMOTE override -> compares vs active remote (PILOT-3)
  PASS ahead of ACTIVE remote -> WARN fires (PILOT-3)
  PASS drift measured vs ACTIVE remote (gitlab, +1), not stale origin (+3) (PILOT-3)
  PASS WARN names the active remote it compared against (PILOT-3)
  PASS same run -> exactly one WARN per run, no per-sweep spam (PILOT-3)
  PASS a new run re-warns once for a standing drift (PILOT-3)

AC6 — check_claim_protocol warns on a working, un-pulled ticket
  PASS aged lock in RfD -> claim-protocol WARN
  PASS same episode -> throttled to one WARN
  PASS status moved to In Progress -> no warn, episode cleared
  PASS episode marker cleared when status changes
  PASS no active lock -> no claim warning
  PASS ORCH_CLAIM_WARN_MINUTES=0 -> claim check disabled (AC4)

=== Test Results ===

  Total:  31
  Passed: 31
  Failed: 0

  ALL TESTS PASSED
```

**AC1**: ✅ PASS — 31/31 assertions green at commit `a1cf72d1`.

---

## Evidence: AC2 — Full Suite (ABS-453)

Command run: `bash tests/run-all.sh`
Commit: `a1cf72d1a0a558d7cf80b5ebbb160fb43a795fb3`

**Result**: 81/82 test files PASS, 1 file FAIL (`test-jira-tracker.sh`, 180/182 assertions).

Failing assertions in `test-jira-tracker.sh`:
```
FAIL link invalid type (rc=1)
  expected: ERROR: link: invalid link type 'friend-of' (parent-child|depends-on|origin-review|pr)
  got:      ERROR: link: invalid link type 'friend-of' (parent-child|depends-on|origin-review|pr|relates)
FAIL jira semantic messages diverge from mock source strings
```

**Pre-existing verification**:
- `git diff HEAD~1..HEAD -- tests/test-jira-tracker.sh` → empty (PILOT-15 did NOT touch this file)
- `scripts/jira-tracker.sh` line 1559 emits `relates` in the link-type list (added by PILOT-8, before PILOT-15)
- `tests/test-jira-tracker.sh` line 271 still asserts the old list without `relates` (test debt, different root cause)
- Same assertion exists at parent commit `b9831f68` → failure is pre-existing

**Classification**: Pre-existing, different root cause (link-type `relates` drift, not stale-origin). Out-of-scope per PILOT-15's own guardrail:
> "Out of scope: weitere rote Datei aus dem Gate-Report separat prüfen — NUR wenn dieselbe Ursache (stale origin-Referenz), sonst eigener Befund an den PO."

Filed as separate PO follow-up by the implementer in PILOT-15 comments. System Architect cleared it as "not a bounce reason."

**AC2**: ⚠️ PARTIAL (pre-existing out-of-scope caveat — PILOT-15 changes are not causal). Not a block per ticket guardrail.

---

## AC Checklist Summary

| AC | Description | Result |
|----|-------------|--------|
| AC1 | 31/31 assertions green in test-local-main-guard.sh | ✅ 31/31 PASS |
| AC2 | Full suite green on epic tip (ABS-453) | ⚠️ 81/82 pass — 1 pre-existing failure (test-jira-tracker.sh, different cause, out-of-scope) |
| AC3 | git diff touches exclusively tests/ | ✅ only tests/test-local-main-guard.sh (7+/3-) |

---

## Final Verdict

**APPROVED** — PILOT-15 satisfies its acceptance criteria. AC1 and AC3 are fully met. AC2's sole caveat is the pre-existing `test-jira-tracker.sh` link-type drift (2/182 assertions), which is out-of-scope per PILOT-15's guardrail, confirmed pre-existing at parent b9831f68, a different root cause (relates link-type), and already filed as a separate PO follow-up. The PILOT-15 commit is categorically unrelated to this failure.

Approved for Story Acceptance.
