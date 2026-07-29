# QA Validation — ABS-594

**Ticket**: ABS-594 — Stable-Checkout parks on development branches; guard checks only prefix  
**Validator**: QAS  
**Date**: 2026-07-27  
**Branch**: ABS-594-auto  
**HEAD at validation**: cf859028380190e04e5ad420ea5d627d3195be0a  
**Verdict**: ✅ APPROVED

---

## AC Verification

### AC1 — Exact-tag guard; prefix match documented as insufficient

`orchestrator.sh:7347` calls `git describe --exact-match --tags HEAD`. The failure message at line 7356 names the prefix-match failure explicitly:

```
"A prefix match (git describe --tags -> 'vX-N-g...') is INSUFFICIENT and is exactly
what let unpublished code run on 2026-07-26."
```

**Result: PASS**

### AC2 — Dirty-tree refusal

`orchestrator.sh:7350` runs `git status --porcelain`. A non-empty result triggers `die` at line 7358–7359, naming "uncommitted or untracked changes". The test at line 58–64 of `PILOT-81-harness-release-guard.sh` adds an untracked file and confirms exit 1 with message "working tree is DIRTY".

**Result: PASS**

### AC3 — Guard runs in the runner, not only in the launcher

`check_harness_release` is called at `orchestrator.sh:10970`, inside `main()`. That is the runner entry point, not any operator-launcher script. Consumer installs have no launcher; the runner-side call covers them.

**Result: PASS**

### AC4 — Seat-parking vector identified and closed

`docs/sop/ORCHESTRATOR_SOP.md:208-217` identifies the root cause: seats committed in the main checkout instead of their runner-provisioned worktrees. Three mechanical layers close it: ABS-224 pre-commit guard forbids commits to `main`; PILOT-66 post-checkout guard warns/restores when a seat moves the main checkout's HEAD; PILOT-81 preflight refuses the next start if the checkout is off-tag or dirty.

**Result: PASS**

### AC5 — Regression test: 3 scenarios all behave correctly

```
Command: SUITE_INCLUDE_ONLY="PILOT-81-harness-release-guard.sh" bash tests/test-orchestrator.sh
Commit:  cf859028
```

```
PASS  PILOT-81 AC5: story-branch harness => start refused (exit 1)
PASS  PILOT-81 AC1: refusal names the exact-tag failure
PASS  PILOT-81 AC6: HARNESS-VERSION stamped to run.log even on refusal
PASS  PILOT-81 AC5: dirty harness on tag => start refused (exit 1)
PASS  PILOT-81 AC2: refusal names the dirty tree
PASS  PILOT-81 AC5: clean harness on tag => start allowed (exit 0)
PASS  PILOT-81 AC5: allowed start logs OK
PASS  PILOT-81 AC6: HARNESS-VERSION line written to run.log
PASS  PILOT-81 AC6: run.log records the resolved release tag
PASS  PILOT-81 kill switch: ORCH_HARNESS_RELEASE_GUARD=0 => legacy start allowed

Total: 10  Passed: 10  Failed: 0
```

**Result: PASS (10/10)**

### AC6 — HARNESS-VERSION written to run.log on every live start

`orchestrator.sh:7353` calls `runlog HARNESS-VERSION` before any pass/fail branch — so a refused start is as auditable as an accepted one. The test at lines 51–52 and 75–78 confirms the `HARNESS-VERSION` line and the `tag=v9.9.9` value appear in `run.log`.

**Result: PASS**

---

## Summary

| AC | Description | Result |
|----|-------------|--------|
| AC1 | Exact-tag guard; prefix documented insufficient | ✅ PASS |
| AC2 | Dirty-tree refusal | ✅ PASS |
| AC3 | Guard in runner (not launcher) | ✅ PASS |
| AC4 | Seat-parking vector closed with 3 mechanical layers | ✅ PASS |
| AC5 | Regression test 10/10 green | ✅ PASS |
| AC6 | HARNESS-VERSION telemetry in run.log | ✅ PASS |

All 6 acceptance criteria pass. No `design` flag on ticket. Transition target: **Story Acceptance**.
