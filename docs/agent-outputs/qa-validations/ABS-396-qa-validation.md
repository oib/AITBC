# QA Validation Report — ABS-396

**Ticket**: ABS-396 — Topological merge-token queue: grant ADR-A-0014 token in depends_on topo-order (not FIFO)
**Validator**: QAS
**Date**: 2026-07-17
**Commit**: 3301142 (33011425632ebf32ec55e23385bd7775907f816a)
**Branch**: ABS-396-auto
**Verdict**: ✅ APPROVED

---

## Acceptance Criteria Verification

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| AC1 | Predecessor wins the merge token even when the dependent story arrives first (opposite arrival order) | ✅ PASS | Section G: "the PREDECESSOR takes the token first, despite arriving second" + "the dependent DEFERS even though the sweep reaches it first" + "the wait names the topological predecessor" + "the dependent never grabs the free token out of topo-order" |
| AC2 | Independent stories retain deterministic ordering (documented tiebreak) | ✅ PASS | Section G: "independent set: the age-first sibling wins the token (documented tiebreak)" + "no topological deferral fires for an independent set (FIFO tiebreak preserved)" |
| AC3 | ADR-A-0014 single-holder + human-merge-to-main invariants unchanged | ✅ PASS | Section G: "single-holder invariant holds — exactly one rte merge seat (human merge-to-main untouched)" + "the predecessor (token holder) gets the rte seat" |

---

## Validation Suite Results

### bash -n (Syntax Check)
```
bash -n scripts/orchestrator.sh → PASS
```

### test-merge-token.sh (Independent QAS run)
```
G. ABS-396 — merge token granted in depends_on TOPOLOGICAL order
  PASS  dependent walked to Merging
  PASS  predecessor walked to Merging
  PASS  the PREDECESSOR takes the token first, despite arriving second
  PASS  the dependent DEFERS even though the sweep reaches it first
  PASS  the wait names the topological predecessor
  PASS  the dependent never grabs the free token out of topo-order
  PASS  single-holder invariant holds — exactly one rte merge seat (human merge-to-main untouched)
  PASS  the predecessor (token holder) gets the rte seat
  PASS  the dependent takes the token once its predecessor has merged
  PASS  the dependent no longer waits once the predecessor left Merging
  PASS  independent set: the age-first sibling wins the token (documented tiebreak)
  PASS  the age-second sibling waits
  PASS  no topological deferral fires for an independent set (FIFO tiebreak preserved)
  PASS  ORCH_MERGE_TOPO=0 -> no topological deferral (plain FIFO grant)
  PASS  FIFO: the age-first (dependent) contender takes the token when topo is off

=== Results ===
  Total:  51
  Passed: 51
  Failed: 0
```

### test-orchestrator.sh (Full suite)
```
=== Results ===
  Total:  1157
  Passed: 1157
  Failed: 0
```

### shellcheck -S error
```
7 error-level findings, ALL at lines 6175, 6639, 6732, 6762, 6777, 6811, 8062
(all pre-existing; new code region is lines 262, 438, 5354–5442)
No new findings introduced.
```

---

## Implementation Review

### New code added (commit 3301142)
- `scripts/orchestrator.sh`: `merge_topo_predecessor_pending()` function (lines 5354–5393) + defer branch in `merge_token_gate()` (lines 5440–5442) + `ORCH_MERGE_TOPO` env var (line 438)
- `tests/test-merge-token.sh`: Section G (15 new assertions covering all 3 ACs)

### Design verification
- Defer correctly placed: AFTER the re-entry MERGE-TOKEN-HOLD branch (current token holders are never deferred) and BEFORE `acquire_merge_token` (only fresh contenders defer) → single-holder invariant preserved
- Degrades to FIFO (not a wedge): absent/unreadable predecessor → FIFO; predecessor not in Merging → FIFO; direct 2-cycle broken by deterministic id order (lower id wins, never a deadlock)
- Kill-switch `ORCH_MERGE_TOPO=0` restores plain FIFO — confirmed by test
- ADR-A-0005 human-merge-to-main boundary untouched: no change to epic PR merge path

---

## Guardrail Checks

| Guardrail | Status |
|-----------|--------|
| Orchestrator/merge-queue change only | ✅ Only `scripts/orchestrator.sh` + `tests/test-merge-token.sh` modified |
| Human merge-to-main boundary (ADR-A-0005) | ✅ Unchanged — confirmed by AC3 test and code review |
| No new feature/cost/credential | ✅ Kill-switch + topo-defer only |
| ADR-A-0014 single-holder invariant | ✅ Asserted by test + code placement analysis |

---

## Flags

Ticket carries no `design` flag → exit target: **Story Acceptance**

---

## Final Verdict

**APPROVED** — All 3 ACs met, all validation checks PASS, no regressions, no new shellcheck issues, guardrails satisfied.
