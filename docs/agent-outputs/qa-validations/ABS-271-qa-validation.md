# QA Validation Report — ABS-271

**Ticket**: ABS-271 — Path-B-Intake: vorbefüllte Epics erreichen ihr DoR-Entry-Gate nie (Routing-Kante fehlt)
**Date**: 2026-07-14
**Validator**: qas
**Branch**: ABS-271-auto
**HEAD commit**: e6fd074
**Base**: epic/ABS-278-v2252-hotfix-consumer-feedback

---

## Verdict: ✅ APPROVED

All AC1–AC5 criteria met. No new test failures or shellcheck warnings introduced.

---

## Acceptance Criteria — Verification

| AC | Description | Result | Evidence |
|----|-------------|--------|----------|
| **AC1** | Pre-filled epic reaches DoR-Check before children released | ✅ PASS | `test-intake-classification.sh`: 3-sweep live drive — EPIC-JOIN-REST parks epic, STATION-GUARD redirects to Ticket Review, qas DoR batch spawns. Confirmed all 11 AC1-related assertions green. |
| **AC2** | Audit comment is honest — no "routed to Path-B entry gate" claim | ✅ PASS | `route_intake()` now posts: "does NOT transition the epic there — STATION-GUARD enforces it". Test asserts `assert_not_contains "$dump" "routed $EC to 'Path-B entry gate'"` — PASS. |
| **AC3** | Child with DoR violation (missing testable ACs) is not waved through | ✅ PASS | Negative fixture seeded: "Child WITHOUT testable ACs (DoR violation)". Both children still delivered to the qas DoR batch review. `test-intake-classification.sh` asserts `INTENT SPAWN ticket=$EC role=qas to=Ticket Review` — PASS. |
| **AC4** | Enrichment → Ticket Review (decomposed epics) unchanged — regression | ✅ PASS | `test-station-guard.sh`: AC4 cases green (legal hop NOT touched, gate-passed epic NOT dragged back). `test-intake-classification.sh`: decomposed path and gate-already-passed path both PASS. `test-epic-join-resting.sh`: 21/21. |
| **AC5** | PATH_DECISION documented — chosen variant + rejected alternative | ✅ PASS | `specs/ABS-103-workflow-v3.1-flexible-intake-spec.md` §6.1: CHOSEN (STATION-GUARD reuse) and REJECTED ("just add the missing edge" — inert) both documented with concrete rationale. |

---

## Test Suite Results (run from ABS-271-auto worktree `tmp/ABS-271-work`)

| Suite | Result | Count |
|-------|--------|-------|
| `test-station-guard.sh` | ✅ ALL PASS | **116 / 116** |
| `test-intake-classification.sh` | ✅ ALL PASS | **37 / 37** |
| `test-epic-join-resting.sh` | ✅ ALL PASS | **21 / 21** |
| `test-path-a-solo-pipeline.sh` | ✅ ALL PASS | **28 / 28** |
| `test-orchestrator.sh` | ⚠️ 23 FAIL (PRE-EXISTING) | 733 / 756 |

### Pre-existing failures — independently verified

`test-orchestrator.sh`: **23 failures on ABS-271-auto == 23 failures on base branch HEAD** (both give `Total: 756, Passed: 733, Failed: 23`). These are the model-label/label-propagation assertions documented by the implementer and confirmed by the system-architect to be ABS-290 baseline failures — not caused by this change.

---

## Static Analysis

| Check | Result |
|-------|--------|
| `bash -n scripts/orchestrator.sh` | ✅ PASS |
| `bash -n scripts/mock-tracker.sh` | ✅ PASS |
| `shellcheck scripts/orchestrator.sh` (SC warning count) | ✅ 26 on ABS-271-auto == 26 on baseline — **no new warnings** |

---

## Key Implementation Points Verified

### The Core Defect (reproduced)
A pre-filled epic (`epic-with-children`) gets no forward seat-move out of `Backlog`, so ABS-214's `epic_join_rest_complete` parks it `Backlog -> Stories In Flight` — directly past the `Ticket Review` DoR gate. `STATION-GUARD` was blind to this hop because `Backlog` is `chain_index 0` and index-0 sources are exempt. Verified live on mock tracker in sweep 1 of `test-intake-classification.sh`.

### The Fix (verified)
`prefilled_epic_entry_index()` computes Enrichment's chain index as the guard-side source for a pre-filled epic, so any subsequent forward hop past `Ticket Review` reads as a skip of a mandatory station and the guard redirects it back. Three predicates protect correctness:
1. `epic_passed_dor_gate` — gate already run → skip (ABS-214 JOIN-rest intact)
2. `epic_visited_grooming` — decomposed epic → skip (the critical discriminator)
3. child-count > 0 — non-empty epic → apply clamp

### Discriminator Test (mutation-checked)
`epic_visited_grooming` is confirmed load-bearing: both regression cases (direct hop and adapter-reachable park path) fail **without** the discriminator and pass **with** it. Station-guard suite mutation-checked as part of the Iteration-1 rework.

### AC2 Honesty Verified
`route_intake()` audit comment in `scripts/orchestrator.sh:3526-3543`: the head string "Ticket Review (DoR gate)" replaced the old "Path-B entry gate", and `intake_mechanic("epic-with-children")` now states explicitly the classification does NOT transition the epic. Tested by 4 assertions in `test-intake-classification.sh`.

### Dead Edge Removed
The `PO Triage -> Ticket Review` edge (fca602c, Iteration 1) is gone. The `statuses.yaml` header block now describes the **actual** repair route (`Backlog -> Stories In Flight -> [STATION-GUARD] -> Ticket Review`) and labels it a repair, not a designed happy path. Only the `Stories In Flight -> Ticket Review` edge remains (required by the adapter's next-table enforcement).

### Architecture Review Findings — all resolved
| Finding (Iteration 1) | Status |
|-----------------------|--------|
| CRITICAL: `prefilled_epic_entry_index` cannot distinguish pre-filled from decomposed | ✅ Fixed: `epic_visited_grooming` discriminator |
| MEDIUM: Dead `PO Triage -> Ticket Review` edge | ✅ Removed |
| MEDIUM: Test gap — no guard test for skipped Enrichment | ✅ Closed: 116-assertion station-guard suite |

---

## Residual Items (out of scope — accepted by system-architect)

1. **Child-release gap**: A po-agent seat that releases children in the same breath as parking the epic still front-runs the gate at the child level — the epic gets pulled back, but those children may already sit in `Ready for Development`. Closing this needs a child-release gate on the story chain, explicitly excluded from this ticket's scope. Recorded in spec §6.1; recommend a follow-up ticket.
2. **`TRACKER_CMD` scrub gap / `--live` refusal guard**: Any seat sandbox-driving the runner can sweep production Jira if `TRACKER_CMD` is not scrubbed. Self-reported by the implementer (not buried); safety defect, but explicitly out of scope here. Follow-up ticket recommended.

Both items accepted as out-of-scope by the system-architect in the Stage 2 approval.

---

## Flags Check

`flags: none` — no `design` flag present → exit target is **Story Acceptance**.

---

**Final Verdict**: ✅ **APPROVED** — All AC1–AC5 PASS, test suites green (pre-existing failures attributed and verified on baseline), no new shellcheck warnings, `bash -n` clean. Approved for RTE.
