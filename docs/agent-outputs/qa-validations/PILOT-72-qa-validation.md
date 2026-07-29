# QA Validation — PILOT-72

**Verdict**: APPROVED  
**Date**: 2026-07-27  
**Commit under test**: `07b3809f`  
**Branch**: `PILOT-72-auto`  
**Actor**: qas

---

## Acceptance Criteria Validation

| # | Criterion | Verdict | Evidence |
|---|-----------|---------|----------|
| AC1 | Idempotency hangs on the cause (fact fingerprint), not the Blocked entry. A Re-Block with unchanged dep facts does not re-release. | **PASS** | `PILOT-72 AC1/AC4: no re-release after a no-change Re-Block (fact fingerprint unchanged)` — 2/2 assertions green |
| AC2 | A demonstrable dependency change (status move) re-enables exactly one further release; unchanged facts leave the ticket in Blocked. | **PASS** | `PILOT-72 AC2: a dependency status change (Docs -> Done) re-enables one release` — 4/4 assertions green |
| AC3 | After `ORCH_BLOCKED_RELEASE_CHURN_CAP` release episodes, sweep stops releasing and raises a visible Attention-Event (NOTIFY), not silent. | **PASS** | `PILOT-72 AC3: churn cap escalates instead of releasing` + `PILOT-72 AC3: escalation is a visible Attention-Event (NOTIFY), not silent` — 4/4 assertions green |
| AC4 | Falsification fixture: unmet dep + 'no change' re-block => exactly ONE release, no further. | **PASS** | `PILOT-72 AC4: first release fires when all depends_on satisfied` — sweep-1 releases, sweep-2 and sweep-3 silent |
| AC5 | Cost assert: the fixture triggers at most one spawn per fact state. | **PASS** | `PILOT-72 AC5: exactly one release (one spawn) per fact state — no churn` — `rel_total=1` across three sweeps |

---

## Test Run Results

### Run command and commit
```
SUITE_INCLUDE_ONLY=PILOT-72-blocked-release-churn.sh bash tests/test-orchestrator.sh
Commit: 07b3809fc3a5f7364443429eb9a5c5e7cd751b59 (PILOT-72-auto)
```

### PILOT-72 fixture (new)
```
Total: 15  Passed: 15  Failed: 0
```

All 15 assertions green. Coverage across 3 fixture blocks:
- Block 1 (AC4/AC5): no-change re-block yields exactly 1 release across 3 sweeps
- Block 2 (AC2): Docs→Done status move re-enables exactly 1 further release
- Block 3 (AC3): churn cap fires at `ORCH_BLOCKED_RELEASE_CHURN_CAP=1`, raises NOTIFY, leaves ticket Blocked

### ABS-296 fixture (updated — regression guard + PILOT-72 pin)
```
SUITE_INCLUDE_ONLY=ABS-296-blocked-auto-release.sh bash tests/test-orchestrator.sh
Total: 26  Passed: 26  Failed: 0
```

The fixture gained 2 new PILOT-72 assertions (new Blocked entry no longer re-releases when dep facts unchanged) and dropped 2 old ones that pinned the churn-loop behaviour. Net count unchanged at 26. All green.

### Baseline comparison
```
Base commit: 1a8889e8 (merge-base of PILOT-72-auto and origin/main)
ABS-296 on base: 26/26 PASS (measured in isolated worktree)
ABS-296 on branch: 26/26 PASS — no new failures
PILOT-72 fixture: new file, no baseline to compare
```

Zero regressions in ABS-296. No other orchestrator test is touched by this commit.

---

## Implementation Review Notes

`blocked_release_fact_fingerprint()` builds the idempotency key from each dependency's current status (via `ticket_status`), sorted for order-independence, joined as `dep=STATUS` tuples. The marker embeds `fact=[...]` so `has_blocked_auto_release_marker` can grep globally (not anchored to the current Blocked entry). A Re-Block that doesn't move any dep status produces an identical fingerprint → the grep still hits → no re-release.

`blocked_auto_release_count()` counts `BLOCKED-AUTO-RELEASED=` occurrences across all comments (not just the current entry), giving a lifetime release counter. The churn-cap check fires when `rel_n >= ORCH_BLOCKED_RELEASE_CHURN_CAP` and uses `blocker_notified` to deduplicate the NOTIFY. The ticket stays Blocked; no further auto-release happens.

Architect's non-blocking observation: a status-only fingerprint doesn't detect a commit arrival without a status move. The churn cap backstops this: after N release episodes with facts changing only via commits (not status moves), the cap fires and notifies the operator. Per the architect's review, this is acceptable scope.

---

## Verdict

**APPROVED for Story Acceptance.**

All 5 acceptance criteria pass. No regressions in ABS-296. Implementation reuses `ticket_status`, `runlog`, `intent`, `notify`, `blocker_notified` — no new parallel mechanisms. The fix is structurally correct: the unbounded 13-cycle/12-spawn/$9.53 loop is closed.
