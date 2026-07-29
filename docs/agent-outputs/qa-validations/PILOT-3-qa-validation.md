# QA Validation Report — PILOT-3

**Ticket**: PILOT-3 — Drift guard: compare against active push remote, one WARN for stale origin  
**Branch**: `PILOT-3-auto`  
**Commit**: `0e182504c8535c92b4eb11768881c9869ee2a018`  
**QAS run date**: 2026-07-21  
**Verdict**: ✅ **APPROVED**

---

## Acceptance Criteria Validation

### AC1 — Conformance test: two remotes, sweep silent vs active remote; one WARN/run on freshness removal

**Command run**:
```
bash tests/test-local-main-guard.sh
```

**Result**: `31 passed, 0 failed` — ALL TESTS PASSED

**Key PILOT-3 test cases (within the 31-test suite)**:
| Test | Result |
|------|--------|
| in sync with ACTIVE remote → no drift despite stale origin +2 | ✅ PASS |
| ORCH_MAIN_REMOTE override → compares vs active remote | ✅ PASS |
| ahead of ACTIVE remote → WARN fires | ✅ PASS |
| drift measured vs ACTIVE remote (gitlab, +1), not stale origin (+3) | ✅ PASS |
| WARN names the active remote it compared against | ✅ PASS |
| same run → exactly one WARN per run, no per-sweep spam | ✅ PASS |
| a new run re-warns once for a standing drift | ✅ PASS |

**Commit hash**: `0e182504c8535c92b4eb11768881c9869ee2a018`

**Status**: ✅ AC1 MET

---

### AC2 — Live evidence: pilot runner sweep log shows spam gone

**Pre-fix evidence (historical)**:
- `.orchestrator-backend/run.log`: **563** `INTENT-LOCAL-MAIN-DRIFT` lines (one per sweep, ~10min cadence)
- `.orchestrator-v3pilot/run.log`: **745** `INTENT-LOCAL-MAIN-DRIFT` lines

**Post-fix live demonstration** (run against real repo state, commit `0e182504`):

**Scenario A — active push remote (ORCH_MAIN_REMOTE=gitlab, ahead=0 vs local main)**:
```
=== PILOT-3 live AC2 demonstration ===
Active push remote: ORCH_MAIN_REMOTE=gitlab
gitlab/main ahead count vs local main: 0
origin/main ahead count vs local main: 287

--- Sweep 1 ---
[no output — drift check silent]
--- Sweep 2 ---
[no output — drift check silent]
--- Sweep 3 ---
[no output — drift check silent]

=== Result: LOCAL-MAIN-DRIFT lines emitted: 0 ===
```
**Spam gone: 0 drift lines across 3 sweeps.**

**Scenario B — throttle verification (origin stale by 287, no override)**:
```
=== PILOT-3 throttle verification (no ORCH_MAIN_REMOTE; @{push}=origin/main, ahead=287) ===

--- Sweep 1 (expect: 1 WARN) ---
INTENT LOCAL-MAIN-DRIFT ticket=- role=- to=- note=ahead=287 branch=main remote=origin/main head=803a6cb2...

--- Sweep 2 (same run; expect: SILENT) ---
[silent — throttled: one WARN per run ✓]

--- Sweep 3 (same run; expect: SILENT) ---
[silent — throttled: one WARN per run ✓]

=== Throttle result: WARN count = 1 across 3 sweeps (was 3 pre-fix) ===
```
**Throttle works: 1 WARN per run vs previous 1 WARN per sweep.**

**Status**: ✅ AC2 MET

---

### AC3 — QA evidence cites the green run per ABS-453 rules

**Green-run command**:
```
bash tests/test-local-main-guard.sh
```

**Pass/fail counter**: `31 passed, 0 failed`

**Commit hash it ran against**: `0e182504c8535c92b4eb11768881c9869ee2a018`

**Supplementary test**:
```
bash tests/test-run-id.sh
```
**Result**: `Passed: 10 / 10 — All tests passed`

**Commit hash**: `0e182504c8535c92b4eb11768881c9869ee2a018`

**Status**: ✅ AC3 MET — green-run proof attached per ABS-453

---

## Additional Checks

| Check | Result |
|-------|--------|
| `bash -n scripts/orchestrator.sh` | ✅ PASS (syntax clean) |
| Branch is `PILOT-3-auto` (ABS-482 compliance) | ✅ CONFIRMED |
| Evidence commit staged only under `docs/agent-outputs/` | ✅ CONFIRMED |
| Architecture review (stage 1) | ✅ APPROVED (architect comment, 2026-07-21T07:42:39Z) |

---

## Implementation Summary

**Changed files**: `scripts/orchestrator.sh` (83 lines changed), `tests/test-local-main-guard.sh` (50 lines added, new)

**Key design**:
- `resolve_active_main_ref()`: resolves via `ORCH_MAIN_REMOTE` override → `branch@{push}` → `origin` fallback — all offline, no network calls
- `check_local_main_drift()`: state file keyed on `ORCH_RUN_ID` ensures exactly one WARN per run; per-head fallback when run-id separation is off
- `ORCH_MAIN_REMOTE=gitlab` in operator env → silence vs stale origin (Bitbucket down since 2026-07-16)

---

## Verdict

**ALL THREE ACCEPTANCE CRITERIA MET.**

- AC1: 31/31 conformance tests green on commit `0e182504` ✅
- AC2: Live demonstration shows 0 drift lines (with ORCH_MAIN_REMOTE=gitlab) and 1 WARN/run throttle (without override) vs pre-fix spam of 563–745 lines ✅
- AC3: Green-run proof attached per ABS-453 (31/31 + 10/10, commit hash cited) ✅

**QAS Verdict: APPROVED — no design flag → releasing to Story Acceptance**
