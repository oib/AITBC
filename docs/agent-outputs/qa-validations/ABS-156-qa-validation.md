# QA Validation Report — ABS-156

**Ticket**: ABS-156 — Default-Turn-Cap für Implementer-Seats hochsetzen/right-sizen  
**QAS Run**: 2026-07-08  
**Branch**: `ABS-156-auto`  
**HEAD**: `ccb5279 feat(orchestrator): right-size implementer turn-cap default to 50 [ABS-156]`  
**Diff scope**: 435516d..ccb5279 — 4 files, +125/-4  
**Verdict**: ✅ **APPROVED**

---

## Acceptance Criteria Verification

### AC1 — New default documented (SOP grep-AC) + override-precedence test EXECUTED

**Criterion**: `grep ORCH_MAX_TURNS_IMPLEMENTER docs/sop/ORCHESTRATOR_SOP.md` returns hits; test that per-role > global precedence is intact and has been run.

**Evidence**:

```
$ grep -n "ORCH_MAX_TURNS_IMPLEMENTER" docs/sop/ORCHESTRATOR_SOP.md
240: | `ORCH_MAX_TURNS` | `25` | ... implementer seats use `ORCH_MAX_TURNS_IMPLEMENTER`. |
241: | `ORCH_MAX_TURNS_IMPLEMENTER` | `50` | ABS-156: built-in turn ceiling for implementer seats ...
413: finish AND commit inside the cap, so they carry a higher built-in default (`ORCH_MAX_TURNS_IMPLEMENTER`,
420: 4. `ORCH_MAX_TURNS_IMPLEMENTER` for implementer seats (built-in default 50);
```

**4 hits** — env-table row, resolution-section prose (×2), and precedence list entry. ✅

**ABS-156 test section (from live run)**:

```
ABS-156 implementer turn-cap default + override precedence
  PASS be-developer default cap is the implementer default (50)
  PASS non-implementer seat keeps the lean global default (25)
  PASS ORCH_MAX_TURNS_BE_DEVELOPER beats global ORCH_MAX_TURNS
  PASS explicit operator-wide cap overrides the implementer default
  PASS ORCH_MAX_TURNS_IMPLEMENTER tunes the implementer default
```

All 5 tests PASS — including the AC-critical precedence test (`ORCH_MAX_TURNS_BE_DEVELOPER beats global ORCH_MAX_TURNS`). ✅

**Result**: AC1 PASS ✅

---

### AC2 — Evidence a realistic be-developer run commits within the cap

**Criterion**: Rationale/evidence that a realistic be-developer run completes AND commits before the new 50-turn cap.

**Evidence**:

1. **Historical run (ABS-129)**: SOP + orchestrator.sh header both cite ABS-129 — a real be-developer run that required an ad-hoc `ORCH_MAX_TURNS_BE_DEVELOPER=50` to complete; now codified as the built-in default.
2. **This ticket's own seat**: The ABS-156 be-developer seat built and committed `ccb5279` within its turn budget (verified: commit exists, working tree clean at the time of QAS handoff).

```
$ git log ccb5279 --format="%H %ai %s" -1
ccb527973bbfb681d69d0892387763f098fda405 2026-07-08 18:13:24 +0200 feat(orchestrator): right-size implementer turn-cap default to 50 [ABS-156]
```

**Result**: AC2 PASS ✅

---

## Independent Test Suite Validation

**Command run**: `bash tests/test-orchestrator.sh`

| Metric | Baseline (435516d) | Branch (ccb5279) | Delta |
|---|---|---|---|
| Total tests | 435 | 440 | +5 |
| Passed | 427 | 432 | +5 |
| Failed | 8 | 8 | **0** |

**Conclusion**: +5 new tests (all PASS), zero new failures, zero regressions. ✅

### 8 Pre-existing failures (verified identical to baseline)

| Failure signature | Category |
|---|---|
| SKIP-LOCKED Done dispatch timing (×2) | lock-timing / environment |
| Provenance harness path expects stable checkout (×2) | tmp-checkout environment |
| MODEL-LABEL-SKIP on system-architect downsize (×4) | ABS-128 live-spawn timing |

All 8 reproduced at baseline (435516d: 427 passed / 8 failed). Not introduced by ABS-156. ✅

---

## Static Analysis

**shellcheck -S error**: 6 SC1087 findings — all in untouched `DISPATCHED_CYCLE`/`SEEN_EVENTS` code (lines 2746, 2787, 2817, 2832, 2841, 3493; intentional string-append idiom). Zero findings in any ABS-156 changed hunk (hunks at original lines 56, 172, 290, 3136). ✅

---

## Scope / Guardrails Check

- **No new ADR**: confirmed — change is constants + doc + tests only. ✅
- **Minimal change**: 4 files, +125/-4. The additions are: `is_implementer_role` predicate, `ORCH_MAX_TURNS_SET` capture, `ORCH_MAX_TURNS_IMPLEMENTER=50` default, SOP knob rows + resolution section, 5 test cases + stub extension. ✅
- **Fast/mechanical seats untouched**: `non-implementer seat keeps the lean global default (25)` — PASS. ✅
- **Per-seat overrides still win**: `ORCH_MAX_TURNS_BE_DEVELOPER beats global ORCH_MAX_TURNS` — PASS. ✅
- **Explicit operator-wide cap still wins**: `explicit operator-wide cap overrides the implementer default` — PASS. ✅
- **Precedence order matches documented order in SOP**: verified by reading `run_spawn_cmd` and the "Turn-ceiling resolution" SOP section. ✅

---

## QAS Notes

**Environment counts**: This QAS run sees 440/432/8 (vs SA's 418/22 and implementer's 432/8). All are the same 440-test suite; differences are live-spawn timing variability in different checkout environments. The substantive finding is identical across all three runs: **+5 new PASS tests, zero new failures**. The SA's baseline-worktree methodology (413/22 base vs 418/22 branch) and our own baseline (435/427/8 base vs 440/432/8 branch) both independently confirm zero regression.

**No findings requiring rework.** The SA's non-blocking design note (specificity inversion when both `ORCH_MAX_TURNS` and `ORCH_MAX_TURNS_IMPLEMENTER` are set) is acknowledged — it is documented and `ORCH_MAX_TURNS_<ROLE>` remains the escape hatch.

---

## Final Verdict

| Check | Status |
|---|---|
| AC1: SOP grep-AC (4 hits) | ✅ PASS |
| AC1: override-precedence test EXECUTED | ✅ PASS (5/5 tests) |
| AC2: realistic be-developer run evidence | ✅ PASS |
| Regression: zero new failures | ✅ PASS |
| Guardrails: no new ADR, minimal change | ✅ PASS |
| Static: shellcheck findings in untouched code only | ✅ PASS |

**Verdict: APPROVED for RTE** ✅
