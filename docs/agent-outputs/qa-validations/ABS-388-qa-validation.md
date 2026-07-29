# QA Validation Report — ABS-388

**Ticket:** ABS-388 — Align shipper ORCH_STOP_FILE default with orchestrator.sh under self-hosting (ORCH_STATE_ROOT)
**QAS Actor:** qas
**Date:** 2026-07-17
**Branch:** ABS-388-auto
**Commits reviewed:** 7241b8e (implementation), 0ce5d52 (doc-only fix)
**Verdict:** APPROVED

---

## Acceptance Criteria Results

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| AC1 | With `ORCH_STATE_ROOT != REPO_ROOT` and `ORCH_STOP_FILE` unset, shipper's computed stop-file path equals `orchestrator.sh`'s computed path | **PASS** | `ORCH_STOP_FILE="${ORCH_STOP_FILE:-$ORCH_STATE_ROOT/work/.orchestrator-stop}"` byte-identical at shipper:80 and orchestrator.sh:462; test `ABS-388 AC1` PASS |
| AC2 | `stop-run` in self-hosting mode writes the stop file at `$ORCH_STATE_ROOT/work/.orchestrator-stop` | **PASS** | Test `ABS-388 AC2` (2 assertions): file lands at ORCH_STATE_ROOT path; old REPO_ROOT path absent |
| AC3 | Explicit `ORCH_STOP_FILE` env var still overrides the default (backward-compatible) | **PASS** | Test `ABS-388 AC3` (2 assertions): override file written; default path not used |
| AC4 | Single-repo mode (`ORCH_STATE_ROOT == REPO_ROOT`) behaviour unchanged — existing suite passes | **PASS** | `ORCH_STATE_ROOT="${ORCH_STATE_ROOT:-$REPO_ROOT}"` preserves single-repo default; full suite 23/23 PASS |
| AC5 | Deploy runbook documents the self-hosting matching-`ORCH_STOP_FILE` requirement | **PASS** | `grep "ABS-388" docs/sop/ORCHESTRATOR_SOP.md` → 2 hits (§stop-switch note + env-var table); false "ORCH_STATE_ROOT to both" sentence deleted in 0ce5d52 |

---

## Test Run Output

```
=== ABS-388 AC1: shipper & orchestrator ORCH_STOP_FILE defaults are identical ===
  PASS ABS-388 AC1: ORCH_STOP_FILE default derives from ORCH_STATE_ROOT in both scripts
  PASS ABS-388 AC4: ORCH_STATE_ROOT defaults to REPO_ROOT (single-repo mode unchanged)
=== ABS-388 AC2: self-hosting stop-run writes at $ORCH_STATE_ROOT/work/.orchestrator-stop ===
  PASS ABS-388 AC2: stop file lands at the ORCH_STATE_ROOT-derived path orchestrator.sh watches
  PASS ABS-388 AC2: executed receipt names the ORCH_STATE_ROOT-derived path
=== ABS-388 AC3: explicit ORCH_STOP_FILE overrides the ORCH_STATE_ROOT default ===
  PASS ABS-388 AC3: explicit ORCH_STOP_FILE override is written (backward-compatible)
  PASS ABS-388 AC3: ORCH_STATE_ROOT default NOT used when override is set

=== Test summary ===
PASS 23/23 tests passed
```

---

## Additional Gate Checks

| Check | Result |
|-------|--------|
| `bash -n` (shipper + test file) | PASS |
| `shellcheck -S error` (shipper) | PASS |
| `orchestrator.sh` untouched | PASS — not in diff (ABS-354 no-new-stop-path) |
| ADR-A-0010 minimal-change | PASS — one default line changed, no new mechanism |
| ABS-66 data-flow | PASS — `exec_stop_run` → `$ORCH_STOP_FILE`; orchestrator watches same var |
| Iteration 1 MEDIUM finding (false ORCH_STATE_ROOT-to-both sentence) | RESOLVED — deleted in 0ce5d52 |
| Residual inaccuracy in env-var table row | NONE — row refers only to matching ORCH_STOP_FILE (accurate) |

---

## Runbook Accuracy Spot-Check

The architect's Iteration 1 MEDIUM finding is confirmed resolved:

- **Deleted (commit 0ce5d52):** *"Exporting the same `ORCH_STATE_ROOT` to both processes also works, since both then derive the identical default."*
- **Retained (correct):** Primary guidance instructs operator to export a **matching `ORCH_STOP_FILE` to both** — both scripts honor `${ORCH_STOP_FILE:-...}`, so this is accurate and fail-safe.
- `orchestrator.sh` derives `ORCH_STATE_ROOT` unconditionally from `ORCH_TARGET_REPO`/`$REPO_ROOT` (`:436/:453/:455`); no residual text implies it reads env `ORCH_STATE_ROOT`.

---

## Flags

`flags: none` → no `design` flag → exit to **Story Acceptance**.

---

## Verdict

**APPROVED** — All 5 ACs PASS. 23/23 tests green. `bash -n`, `shellcheck -S error` clean. Runbook accurate (Iteration 1 MEDIUM resolved). Code change is ADR-A-0010 minimal-change, byte-identical to `orchestrator.sh:462`. `orchestrator.sh` untouched. Story released to Story Acceptance.
