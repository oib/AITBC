# QA Validation Report — ABS-325

**Ticket**: ABS-325 — v3 Fastlane: Auswurf statt Parkung — Auto-Rückstufung in die Normal-Lane  
**Branch**: `ABS-325-auto`  
**Commit**: `89aadb1`  
**QAS Run Date**: 2026-07-16  
**Validator**: qas  

---

## Verdict: ✅ APPROVED

All 6 acceptance criteria PASS. Full orchestrator suite 1050/1050 green. No flags in ticket labels → transition to Story Acceptance.

---

## Pre-Flight Checks

| Check | Result |
|-------|--------|
| `bash -n scripts/orchestrator.sh` | ✅ CLEAN |
| `bash -n tests/orchestrator.d/ABS-325-fastlane-eject.sh` | ✅ CLEAN |
| Commit `89aadb1` exists on `ABS-325-auto` | ✅ VERIFIED |
| Implementation files: `scripts/orchestrator.sh` (+166), `tests/orchestrator.d/ABS-325-fastlane-eject.sh` (+169) | ✅ VERIFIED |

---

## Test Suite Results

**Full Orchestrator Suite**: `bash tests/test-orchestrator.sh`
- **Total: 1050 / Passed: 1050 / Failed: 0**
- Exit code: 0
- Run method: parallel (4 shards), ABS-325 assertions in final shard

**Run-all validation**: `bash tests/run-all.sh tests/test-orchestrator.sh`
- Result: `ALL 1 FILES PASSED`
- Exit code: 0

---

## Acceptance Criteria — Per-Criterion Verification

### AC1: Red tests at iteration ≥2 → eject to normal lane (no Blocked/Human-Wait)
**Evidence**: 4 dry-run assertions in `ABS-325-fastlane-eject.sh`:
- `INTENT FASTLANE-EJECT ticket=$F role=- to=Ready for Development` ✅ PASS
- `trigger=red-tests` named in ejection ✅ PASS  
- No `INTENT STALL-RAISE` for ejected ticket ✅ PASS (AC5 cross-check)
- No `INTENT REWORK-LIMIT` for ejected ticket ✅ PASS (AC5 cross-check)

*All 4 AC1 assertions confirmed via 1050/1050 total count (prior suite baseline + 24 new ABS-325 = 1050).*

### AC2: Diff-budget overrun → eject to normal lane
**Evidence**: 4 assertions (LIVE diff budget + control):
- `PASS ABS-325 AC2: a diff-budget overrun ejects the fastlane ticket` ✅
- `PASS ABS-325 AC2: the ejection names the diff-budget trigger` ✅
- `PASS ABS-325 AC2: a within-budget diff does not eject (the combined gate runs)` ✅
- `PASS ABS-325 AC2: a within-budget fastlane ticket stays on the collapsed chain` ✅

### AC3: Protected path touched → eject
**Evidence**: 2 assertions:
- `PASS ABS-325 AC3: touching a protected path ejects the fastlane ticket` ✅
- `PASS ABS-325 AC3: the ejection names the protected-path trigger` ✅

### AC4: Firing station guard → eject (not STATION-GUARD redirect)
**Evidence**: 4 assertions + normal-lane control:
- `PASS ABS-325 AC4: a firing station guard ejects the fastlane ticket` ✅
- `PASS ABS-325 AC4: the ejection names the guard trigger` ✅
- `PASS ABS-325 AC4: the in-lane STATION-GUARD redirect is replaced by ejection` ✅
- `PASS ABS-325 AC4: a normal-lane ticket keeps the STATION-GUARD redirect` ✅ (control)
- `PASS ABS-325 AC4: a normal-lane ticket is never ejected` ✅ (control)

### AC5: Never Blocked / never human-wait; ejection-reason comment recorded
**Evidence**: 5 LIVE assertions (lane set + comment + status checks):
- `PASS ABS-325 AC5: the ejected ticket is demoted to the normal lane` ✅
- `PASS ABS-325 AC5: an ejection-reason comment is recorded on the ticket` ✅
- `PASS ABS-325 AC5: the ejected ticket never enters Blocked` ✅
- `PASS ABS-325 AC5: the ejected ticket never waits on a human (Needs PO Decision)` ✅
- `PASS ABS-325 AC5: the ejected ticket never waits on a human (RfHA)` ✅

### AC6: Per-ticket attribution — ejected member does not eject bundle-mates
**Evidence**: 3 LIVE assertions:
- `PASS ABS-325 AC6: the triggering bundle member A is ejected to normal` ✅
- `PASS ABS-325 AC6: the still-eligible bundle-mate B keeps lane=fastlane (per-ticket attribution)` ✅
- `PASS ABS-325 AC6: B carries no ejection — only the offending ticket is demoted` ✅

---

## Additional Verification

### Kill-switch
- `PASS ABS-325: knob=0 emits no ejection` ✅ — `ORCH_FASTLANE_EJECT=0` correctly disables ejection

### Guardrail Cluster 5 (ejection bypasses no gate)
Verified by System Architect in Stage 1 review: `fastlane_eject` re-transitions to `Ready for Development` (ADR-A-0002 impl-fix re-entry), normal chain (QAS, review, PO acceptance, epic-integration full-suite, merge-token, human merge) proceeds unmodified. ✅

### Implementation Quality
- `fastlane_eject_gate` placed BEFORE `station_guard` in `dispatch()` ✅
- Reuses established primitives: `rework_count` (ABS-74), `handoff_commits/commits:` (ABS-255), `forward_skip_illegitimate`, `fastlane_skip` dry-run/live split ✅
- Fail-open error handling (no git / no repo / no claimed hash → no-op) ✅
- `Ready for Development` proven legal backward edge from all chain stations 1..9 per `statuses.yaml` (architect verified) ✅
- ABS-66 data-flow traced: `update lane`, inline `--body` comment, inline `--reason` transition — all confirmed CAPABLE in live adapter ✅

---

## DoD Checklist

- [x] All 6 ACs verified with specific test evidence
- [x] 24 assertions covering all ACs (10 dry-run + 14 live)
- [x] Full orchestrator suite 1050/1050 green (independent QAS run)
- [x] `bash -n` clean on both files
- [x] Pattern compliance: reuses ABS-74/ABS-255/ADR-A-0002 primitives (no new state)
- [x] Guardrail cluster 5: ejection bypasses no gate
- [x] Kill-switch `ORCH_FASTLANE_EJECT=0` tested
- [x] System Architect Stage 1 review APPROVED
- [x] No `design` flag in ticket labels → exit to Story Acceptance

---

## Final Verdict

**APPROVED for Story Acceptance.**

> QAS validation complete for ABS-325. All 6 ACs PASS. 1050/1050 test suite green. 24 ABS-325-specific assertions verified. Evidence posted to tracker. Approved for RTE.
