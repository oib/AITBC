# QA Validation Report — PILOT-2

**Ticket**: PILOT-2 — Wait-state invariant: refuse/repair Merging->Docs jump (ready for Merge mandatory)  
**Validator**: QAS  
**Date**: 2026-07-20  
**Branch**: `PILOT-2-auto`  
**Commit validated**: `a7479516b625c27660ab26fad584d8a1f49ef0a7`  
**Verdict**: ✅ **APPROVED**

---

## Acceptance Criteria — Verdict

| # | Criterion | Result |
|---|-----------|--------|
| AC1 | Conformance test: handoff declaring Docs with current=Merging leads to repair to Ready for Merge with a gate-results comment; status history contains Ready for Merge. | ✅ PASS |
| AC2 | Existing wait-state suites (test-ready-for-merge-gate.sh, wrong-entry-guard) stay green. | ✅ PASS |
| AC3 | QA evidence cites the green run per ABS-453 rules. | ✅ PASS |

---

## Green-Run Proof (ABS-453)

All suites run independently by QAS against commit `a7479516b625c27660ab26fad584d8a1f49ef0a7` on branch `PILOT-2-auto`.

### Full orchestrator suite

```
Command: bash tests/test-orchestrator.sh
Commit:  a7479516b625c27660ab26fad584d8a1f49ef0a7
Branch:  PILOT-2-auto

=== Test Results (aggregated over 4 shards) ===

  Total:  1266
  Passed: 1266
  Failed: 0

  ALL TESTS PASSED
```

Includes `tests/orchestrator.d/PILOT-2-merging-docs-waitstate.sh` (all 17 PILOT-2 assertions included in the 1266 total).

### test-ready-for-merge-gate.sh

```
Command: bash tests/test-ready-for-merge-gate.sh
Commit:  a7479516b625c27660ab26fad584d8a1f49ef0a7
Branch:  PILOT-2-auto

=== Test Results ===

  Total:  40
  Passed: 40
  Failed: 0

  ALL TESTS PASSED
```

### test-wrong-entry-guard.sh

```
Command: bash tests/test-wrong-entry-guard.sh
Commit:  a7479516b625c27660ab26fad584d8a1f49ef0a7
Branch:  PILOT-2-auto

=== Test Results ===

  Total:  13
  Passed: 13
  Failed: 0

  ALL TESTS PASSED
```

---

## AC1 Detail — Conformance Test Coverage

`tests/orchestrator.d/PILOT-2-merging-docs-waitstate.sh` covers the following cases:

| Case | Description | Assertion |
|------|-------------|-----------|
| (1) Declared Docs @ Merging, PR=OPEN | Unmerged declared jump is repaired | Status=Ready for Merge; WAIT-STATE REPAIR comment; Merging→Ready for Merge edge in history |
| (2) Self-moved to Docs, PR=OPEN | Exact PILOT-1 pilot shape is repaired | Status=Ready for Merge; INTENT MERGING-DOCS-WAITSTATE; NO "skip current=Docs" log |
| (3) MERGED declared exit (ADR-A-0014) | Auto-merge happy path passes untouched | Status=Docs; no INTENT; no WAIT-STATE REPAIR comment |
| (4) MERGED self-moved exit (ADR-A-0014) | Auto-merge self-move passes untouched | Status=Docs; no INTENT; no WAIT-STATE REPAIR comment |
| (5) No FORGE_CMD | Placeholder/no-forge env falls open | Gate returns NOOP |
| (6) Clean target-less Merging handoff | ABS-133 default not intercepted | Status=Ready for Merge via ABS-133 (not wait-state gate); no INTENT; no WAIT-STATE REPAIR |
| (7) Non-Merging seat | Gate is Merging-only | Gate returns NOOP |

All 7 cases (17 total assertions) PASS.

---

## Implementation Review Summary

The fix in `scripts/orchestrator.sh` (`merging_docs_waitstate_gate`) is merge-state-aware, mirroring the `docs_pr_gate` idiom:

- Probes `story_pr_state` (already defined at `orchestrator.sh:2749`)
- `MERGED` or `NONE` → falls through (ADR-A-0014 auto-merge exit is legal; direct-to-branch is legal)
- No `FORGE_CMD` → fails open (parity with `docs_pr_gate`/`done_pr_gate`)
- `OPEN` (PR exists but unmerged) → refuses/repairs: posts `WAIT-STATE REPAIR` gate-results comment, transitions to `Ready for Merge`
- Wired into `apply_handoff_transition` before the noop/skip branches
- No `statuses.yaml` changes needed (repair edges already exist)

The iteration-1 Stage-1 defect (merge-state blindness, ADR-A-0014 tension) is fully resolved. The gate narrows its fire condition to the actual PILOT-1 defect: an unmerged Merging-seat jump to Docs.

---

## Flags Check

Ticket labels: `[orchestrator-ready]` — no `design` flag.  
Exit target: **Story Acceptance**.

---

## Final Verdict

**APPROVED** — All ACs met, all suites green, ABS-453 green-run proof attached, no `design` flag. Advancing to Story Acceptance.
