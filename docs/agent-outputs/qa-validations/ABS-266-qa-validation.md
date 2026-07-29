# QA Validation Report — ABS-266

**Ticket**: ABS-266 — Harness: STATION-GUARD drags merged stories backward; `Needs PO Decision` has no post-merge exit  
**QAS seat**: qas  
**Date**: 2026-07-14  
**Commit**: 966df43  
**Branch**: ABS-266-auto  

---

## Scope (post PO scope decision)

| Defect | Status |
|---|---|
| Defect 1: STATION-GUARD drags merged stories backward | **IN SCOPE** |
| Defect 2: ABS-74 rework counter counts orchestrator redirects | **OUT OF SCOPE** — owned by ABS-267 (Done); NOT tested here |
| Defect 3: `Needs PO Decision` has no post-merge forward exit | **IN SCOPE** |

---

## Acceptance Criteria Verification

### AC1 ✅ PASS — Merged story released to `Docs` is NOT pulled backward by STATION-GUARD

**What was fixed:**  
`forward_skip_illegitimate()` in `scripts/orchestrator.sh` now exempts any landing where `$2 = "Docs"` from the pre-merge station-order check. `Docs` carries `entered_when: Story merged (v3)` in `profiles/neutral/adapters/statuses.yaml`, so a landing in `Docs` is by definition post-merge, while station order is a pre-merge concern.

**Code verified:**  
```bash
# Line 1692 in scripts/orchestrator.sh
if [ "$2" = "Docs" ]; then return 1; fi
```
Placement is AFTER the `fi/ti > 0` guard (`Docs` has `chain_index = 11`, not 0), so the new guard is **reachable** for all valid in-chain from-statuses.

**Narrowness confirmed:**  
- `In Test -> Done` and `Merging -> Done` are still flagged (ABS-136 Befund 6 intact)
- `done_pr_gate()` (ABS-211) still enforces merge evidence at `Done` separately

**Test evidence (from `tests/test-station-guard.sh`):**  
```
ABS-266 — the MERGE BOUNDARY: a Docs landing is never dragged backward

  PASS  AC1: In Progress -> Docs (the ABS-234 hop) -> exempt, merged story never dragged back
  PASS  In Test -> Docs (post-merge landing) -> exempt
  PASS  Design -> Docs (skips the whole implementation range) -> still exempt (merge boundary)
  PASS  merge boundary beats a full flag set — a merged story is never rebuilt
  PASS  regression: In Test -> Done STILL flagged (Befund 6 intact — Docs is the only exemption)
  PASS  regression: Merging -> Done STILL flagged (skips the Docs seat)
  PASS  AC1: merged story released to Docs -> guard no-ops (rc 1), story STAYS at Docs
  PASS  no guard intent on the post-merge Docs landing
  PASS  AC1: NO adapter writes — the merged story is not transitioned backward
```

**Note on mock-adapter masking:** The system-architect flagged (and QAS independently confirmed) that the mock adapter *refuses* the illegal `Docs -> In Review` drag, so resting status alone would look fine even without the fix. The tests correctly assert on **guard rc** (`rc=1` = guard no-ops, story stays) and **zero adapter writes** — not just on resting status. This is the correct assertion strategy per the handoff warning.

---

### AC2 — OUT OF SCOPE

Per PO scope decision (2026-07-13T22:00:32Z): Defect 2 is owned by ABS-267 (Done). No rework-counter code was touched in commit 966df43. NOT tested here.

---

### AC3 ✅ PASS — `Needs PO Decision` has a legal post-merge forward exit (`Docs`) in statuses.yaml

**What was fixed:**  
`Docs` added to the `next:` table of `Needs PO Decision` in `profiles/neutral/adapters/statuses.yaml`.

**YAML verified:**
```yaml
  - name: Needs PO Decision
    ...
    next:
      - Backlog
      - Ready for Development
      - PO Triage
      - Grooming
      - Stories In Flight
      - Design
      # ABS-266: post-merge forward exit...
      - Docs        ← NEW
      - Blocked
```

**Parser safety confirmed:** The `allowed_next()` awk block-walker in `mock-tracker.sh` correctly handles comment lines (`^[ ]*#`) without truncating the next-table. Proven by test (test-mock-tracker.sh AC3 assertion), not by inspection alone.

**Test evidence (from `tests/test-mock-tracker.sh`):**
```
=== Test 8c: Needs PO Decision — post-merge forward exit (ABS-266) ===

  PASS  AC3: Needs PO Decision -> Docs is a LEGAL transition (statuses.yaml next-table)
  PASS  AC4: post-merge escalation routes FORWARD to Docs
  PASS  escalated story resumes at Docs, not re-implementation
  PASS  AC4: routed forward WITHOUT ever laundering through Blocked (no Blocked hop in the history)
```

---

### AC4 ✅ PASS — Post-merge escalation can be routed forward without passing through `Blocked`

Verified by `test-mock-tracker.sh` Test 8c:  
- Story escalated from post-merge stage to `Needs PO Decision`  
- Transitioned directly to `Docs` (rc=0, status=Docs)  
- History contains **no `-> Blocked` hop**  

---

## Test Suite Results

| Suite | Count | Pass | Fail | Notes |
|---|---|---|---|---|
| `test-station-guard.sh` | 105 | **105** | 0 | +7 new ABS-266 assertions |
| `test-mock-tracker.sh` | 166 | **166** | 0 | +4 new ABS-266 assertions |
| `test-orchestrator.sh` | 740 | **718** | 22 | Pre-existing; 3 independent runs, consistent result |

**Orchestrator baseline note:** Three independent QAS runs yielded 718/740 pass, 22 fail — consistent across all runs. The system-architect reported 704/36 at review time (a discrepancy of +14 pass / -14 fail). The discrepancy is not blocking: (a) the system-architect independently verified both arms (pre-fix and post-fix) as identical; (b) all three of my runs are consistent at 718/22, confirming no new failures from the ABS-266 change; (c) zero failing assertions reference `Docs`, `STATION-GUARD`, `forward_skip_illegitimate`, or `Needs PO Decision`. The 22 failures are pre-existing.

---

## Definition of Done Checklist

| DoD Item | Status |
|---|---|
| Regression tests green for Defect 1 | ✅ test-station-guard.sh 105/105 |
| Regression tests green for Defect 3 | ✅ test-mock-tracker.sh 166/166 |
| `statuses.yaml` next-table updated | ✅ `Docs` added to `Needs PO Decision` |
| No merged story in ABS-229 requires manual TDM resume (structural fix verified) | ✅ exemption reachable + narrow |

---

## Independent Code Review Findings

1. **Exemption is live (not dead code):** `chain_index(Docs) = 11` (line 1581). The `fi/ti > 0` early return is not hit for `Docs` as a landing target, so the new guard `if [ "$2" = "Docs" ]; then return 1; fi` is reachable.
2. **Safety net intact:** `done_pr_gate()` (ABS-211) still fail-closes at `Done` and redirects to `Merging` when PR is not MERGED. Exempting `Docs` from *station order* does not weaken *merge evidence* enforcement — different mechanisms.
3. **Scope discipline:** No rework-counter code was modified (Defect 2 correctly excluded per PO decision).

---

## Pre-existing Failures (not introduced by ABS-266)

The system-architect and QAS both independently confirmed that `test-orchestrator.sh` failures are pre-existing and unrelated to ABS-266. Specifically:
- `test-agent-def-overlay.sh`, `test-wrong-entry-guard.sh`, `e2e-workflow-v3.sh` are noted as pre-existing on clean HEAD in the handoff

---

## Verdict

**APPROVED** — All in-scope acceptance criteria PASS. Test suites green on the primary suites (105/105, 166/166). Orchestrator baseline consistent (718/22 in 3 independent runs, no new failures). Implementation is correct, narrow, and reachable. Safety nets intact.

**Commit**: 966df43  
**Transition**: `In Test → Story Acceptance`  
