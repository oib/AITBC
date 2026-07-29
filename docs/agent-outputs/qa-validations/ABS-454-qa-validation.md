# QA Validation Report — ABS-454

**Ticket**: ABS-454 — Retro: ready-for-Merge entry invariant — MR must exist (verify + self-heal)  
**Branch**: `ABS-454-auto`  
**Commit**: `46d50a3` — `feat(orchestrator): self-heal ready-for-Merge entry without an MR [ABS-454]`  
**QAS**: Validated on 2026-07-19  
**Verdict**: ✅ APPROVED

---

## Acceptance Criteria Verification

### AC1 — No-MR at "Ready for Merge" detected and self-healed to "Merging"

**Result: PASS**

Evidence from `tests/test-ready-for-merge-gate.sh`:
- `PASS` gate INTERVENES (rc 0) on a Ready-for-Merge story with no MR
- `PASS` logs the no-MR self-heal intent redirecting to Merging
- `PASS` re-transitions the ticket back to Merging (self-heal, not stall)
- `PASS` the redirect is guarded with `--expect-from` (lost race NOOPs, ABS-198)
- `PASS` posts a naming `gate-results` comment as the orchestrator
- `PASS` audit comment cites ABS-454
- `PASS` comment names the self-heal: the RTE respawn creates the MR
- `PASS` writes an `INTENT-READY-FOR-MERGE-NO-MR` run.log event

Gate implementation verified:
- `ready_for_merge_mr_gate()` wired at BOTH `dispatch()` entry (to='Ready for Merge') AND `reconcile()` sweep (the ABS-416 restart case)
- Self-heal chain: `Ready for Merge → Merging → SPAWN rte` (orchestrator.sh:1186 verified by architect)
- `--expect-from "Ready for Merge"` compare-and-set guard prevents false redirect on human-merge race

### AC2 — OPEN or MERGED MR yields no false alarm

**Result: PASS**

Evidence from `tests/test-ready-for-merge-gate.sh`:
- `PASS` merged MR → no-op (rc 1), the human merge gate keeps resting
- `PASS` no gate intent when the MR is merged
- `PASS` no adapter writes when the MR is merged
- `PASS` open MR (merge-wait park, ABS-270) → no-op (rc 1), not redirected
- `PASS` no writes for a legitimate open-MR merge-wait park (no false alarm)

Semantic correctness: The gate guards `FORGE_CMD` first; inside it, `NONE` unambiguously means "forge configured, no MR" = the defect. `OPEN` = legitimate ABS-270 merge-wait park; `MERGED` = already satisfied. The only state that triggers the self-heal is `NONE`.

### AC3 — Pre-existing suites green

**Result: PASS**

| Suite | Tests | Result |
|-------|-------|--------|
| `test-ready-for-merge-gate.sh` (new, ABS-454) | 23/23 | ✅ ALL PASS |
| `test-done-gate.sh` | 32/32 | ✅ ALL PASS |
| `test-merge-wait.sh` | 49/49 | ✅ ALL PASS |
| `test-mock-tracker.sh` | 181/181 | ✅ ALL PASS |
| `test-status-source-drift.sh` (COPY A-E drift guards) | 9/9 | ✅ ALL PASS |
| `test-backend-status-literal-drift.sh` | 5/5 | ✅ ALL PASS |
| `test-mirror-drift-guard.sh` | 5/5 | ✅ ALL PASS |
| `test-orchestrator.sh` (tentpole, 4 shards) | **1214/1214** | ✅ ALL PASS |

Pre-existing environment failures (unrelated to this change, fail identically on clean HEAD):
- `test-gitattributes-eol.sh` — pre-existing env issue (not caused by this diff)
- `test-wrong-entry-guard.sh` — pre-existing env issue (not caused by this diff)

These failures were present before this commit and are classified as `environment` failures (ABS-454 diff does not touch either test or the features they exercise).

---

## Implementation Review

**Files changed (4)**:

1. `scripts/orchestrator.sh` (+77 lines) — `ready_for_merge_mr_gate()` function + wiring at dispatch entry and reconcile sweep
2. `profiles/neutral/adapters/statuses.yaml` (+7 lines) — `Ready for Merge → Merging` self-heal edge
3. `backend/packages/core/src/workflows/statuses.yaml` (+7 lines) — byte-identical backend mirror
4. `tests/test-ready-for-merge-gate.sh` (+187 lines) — conformance suite

**Pattern compliance**: Gate is a precise peer of `done_pr_gate` / `docs_pr_gate` (post-landing, MODE-aware, idempotent, fail-open placeholder, fail-LOUD on rejected edge — the ABS-284 idiom). Confirmed by both architect review and independent QAS code read.

**No RLS/auth/migration surface** (bash + YAML only).

---

## Additional Guards Verified

- **Backend mirror byte-identical**: `profiles/neutral/adapters/statuses.yaml` and `backend/packages/core/src/workflows/statuses.yaml` diffs are identical (+7 lines, same content)
- **COPY-D drift guard**: `test-status-source-drift.sh` 9/9 PASS confirms the new edge is consistent across all status copies
- **Fail-open correct**: No `$FORGE_CMD` → gate returns 1 (skip), zero adapter writes
- **Fail-loud correct**: Rejected edge → logs + run.log + audit comment + returns 1

---

## Verdict

**APPROVED** ✅

All three acceptance criteria met. New conformance suite 23/23. Pre-existing suites green (1214/1214 tentpole + all sibling suites). Implementation is pattern-compliant, minimal, and well-documented. No design flag on this ticket.

**Exit**: → Story Acceptance (no `design` flag)
