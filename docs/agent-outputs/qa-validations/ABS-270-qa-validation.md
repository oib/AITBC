# QA Validation Report — ABS-270

**Ticket**: ABS-270 — Runner/Status-Modell: kein Rest-Zustand für „Story korrekt, PR offen, wartet auf Mensch"
**Commit under review**: ed8cb27
**Branch**: ABS-270-auto
**Validated by**: qas
**Date**: 2026-07-15
**Verdict**: ✅ APPROVED

---

## Files Changed (ed8cb27)

| File | Change |
|------|--------|
| `scripts/orchestrator.sh` | +136 lines — `docs_pr_gate`, `merge_wait_release`, `parked_at_merge_gate`, `#PATH_DECISION` block |
| `profiles/neutral/adapters/statuses.yaml` | +38 lines — `Docs→Ready for Merge`, `Ready for Merge→Docs`, `Done→Merging` edges |
| `tests/test-merge-wait.sh` | +291 lines — 49-test suite covering AC1–AC6 |
| `tests/orchestrator.d/ABS-285-env-scrub.sh` | +4 lines — env-scrub registration |

---

## Acceptance Criteria — Full Verification

### AC1 — No ABS-132 Stuck-Loop escalation to `Needs PO Decision`

**Status**: ✅ PASS

Verified at three levels:
1. **Architecture** (direct source inspection): `is_reconcilable_status "Ready for Merge"` → false (orchestrator.sh:1167/1196 fall-through), so the ABS-132 no-move counter has nothing to count; `is_legit_rest_status "Ready for Merge"` → true (orchestrator.sh:1246), so the stuck detector never fires.
2. **Tests**: 3-sweep simulation over an open-PR story produces zero transitions and zero adapter calls. `assert_not_contains "$calls" "Needs PO Decision"` — explicit gate.
3. **Test output**: lines "sweep 1/2/3: PR still open → release is a no-op (the story keeps resting)" — all PASS.

### AC2 — Zero overfluous seat spawns

**Status**: ✅ PASS

- `map_action 'Ready for Merge'` → `NOOP -` (orchestrator.sh:921) — no seat spawned, ever.
- 3-sweep test: `STUB_CALLS` is empty after 3 reconcile passes.
- The park itself emits `INTENT MERGE-WAIT` (not `SPAWN`) — the tech-writer is never asked.

### AC3 — Done gate intact (ABS-192 regression blocked)

**Status**: ✅ PASS

- `done_pr_gate` is untouched; its redirect `Done → Merging` is now a legal edge in `statuses.yaml` (previously missing, causing the adapter to silently drop the redirect in real-mode — the latent ABS-211 gap).
- Test: `assert_contains "$calls" "TRANSITION ABS-192 Merging"` — unmerged-PR Done still lands in Merging, NOT in Done.
- Adapter-level test using the real `mock-tracker.sh` confirms `Done → Merging` is accepted.

### AC4 — On merge, story auto-resumes to Done without manual step

**Status**: ✅ PASS

- `merge_wait_release` runs in reconcile BEFORE the reconcilable-status filter; on a MERGED PR it transitions `Ready for Merge → Docs`, uses `--expect-from` compare-and-set (ABS-198 race safety).
- Test: `assert_contains "$calls" "TRANSITION ABS-253 Docs"` on merge event.
- Second-pass Docs landing passes `docs_pr_gate` (PR is merged) → tech-writer spawns normally.
- No further adapter writes (no park/release ping-pong).

### AC5 — #PATH_DECISION documented

**Status**: ✅ PASS

Block at `scripts/orchestrator.sh:1862–1892`:
- **CHOSEN**: option 1 (Docs-station precondition) — explained via the three axes (NOOP/not-reconcilable/legit-rest).
- **REJECTED**: option 2 (still spawns the tech-writer every cycle) and option 3 (treats a legit rest as escalation) — concrete reasons given. Option 3's useful half (human notification) is retained in the implementation.

### AC6 — Wait is visible as "waiting on human merge", not as stuck

**Status**: ✅ PASS

- Tracker transition reason: `"MERGE-WAIT: implementation PR … not merged … — waiting on human merge; resting at the human-owned merge gate until it lands (ABS-270)"`.
- Gate-results comment body explicitly states `"WAITING ON A HUMAN MERGE (human-only #2, ADR-A-0005)"`.
- Status `Ready for Merge` is self-describing (human-owned gate, widely known in the pipeline).
- `notify` fires once with `"waiting on human merge: $ticket is pipeline-green and its PR … is $state — merge it and the runner finishes the story on its own"`.
- Test asserts: `assert_contains "$calls" "waiting on human merge"` — PASS.

---

## Test Suite Results

| Suite | Result | Count |
|-------|--------|-------|
| `tests/test-merge-wait.sh` | ✅ ALL PASS | 49/49 |
| `tests/test-done-gate.sh` | ✅ ALL PASS | 32/32 |
| `tests/test-station-guard.sh` | ✅ ALL PASS | 105/105 |
| `tests/test-mock-tracker.sh` | ✅ ALL PASS | 166/166 |
| `tests/test-epic-join-resting.sh` | ✅ ALL PASS | 21/21 |
| `tests/test-path-a-solo-pipeline.sh` | ✅ ALL PASS | 28/28 |
| `tests/test-claim-dispatch.sh` | ✅ ALL PASS | 25/25 |

**Total: 426/426 PASS, 0 FAIL**

---

## Lint / Syntax

| Check | Result |
|-------|--------|
| `bash -n scripts/orchestrator.sh` | ✅ CLEAN |
| `bash -n tests/test-merge-wait.sh` | ✅ CLEAN |
| shellcheck SC1087 count (7 == 7) | ✅ UNCHANGED |
| shellcheck non-SC1087 findings | ✅ UNCHANGED (pre-existing, baseline-identical) |

---

## Non-Blocking Observation (from SA, forwarded for PO awareness)

A story parked at `Ready for Merge` whose PR is later DECLINED (closed without merge) will rest there indefinitely with no escalation. This is:
- Consistent with the human-owned gate semantics (Path-A stories already rest there awaiting a human).
- Strictly better than the pre-fix behaviour (which mis-escalated to the PO, who has no merge authority).

Not a defect against any AC. Flagged for future runbook documentation if needed.

---

## Definition of Done

- [x] All 6 ACs met and test-covered
- [x] 49/49 primary tests PASS
- [x] 426/426 regression tests PASS  
- [x] bash -n CLEAN
- [x] Zero new shellcheck findings
- [x] #PATH_DECISION documented (options chosen + rejected)
- [x] No RLS / auth / migration / frontend surface (shell runner only)
- [x] Evidence committed on branch ABS-270-auto

**Verdict: APPROVED for Story Acceptance**
