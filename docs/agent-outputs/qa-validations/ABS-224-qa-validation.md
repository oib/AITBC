# QA Validation Report — ABS-224

**Branch**: `ABS-224-auto` | **Commit**: `886b7db` | **Date**: 2026-07-12 | **Actor**: qas

## Verdict: APPROVED (AC1–AC4, AC6) | AC5 OPERATOR-BLOCKED

AC5 must be resolved (operator decision recorded on ticket) before **Done**.

---

## AC Validation

| AC | Criterion | Status | Evidence |
|----|-----------|--------|----------|
| AC1 | Seat commit on local main aborted mechanically; human commits pass | ✅ PASS | `test-local-main-guard.sh`: 7 direct hook cases + 3 end-to-end real-git cases all PASS |
| AC2a | `_common-rules.md` rule 6: work on story branch, artefacts on story branch, never local main | ✅ PASS | Rules 6 & 7 present in `harness/claude/agents/_common-rules.md`, source edited (not governor `.claude/`) |
| AC2b | `_common-rules.md` rule 7: claim protocol — pull ticket to In Progress before first file | ✅ PASS | Rule 7 explicitly states "BEFORE touching the first file" with ABS-213 Befund cited |
| AC3 | Orchestrator warns (intent + notify) when local main is ahead of origin/main | ✅ PASS | `check_local_main_drift` called in `reconcile()`; test: `INTENT LOCAL-MAIN-DRIFT` + `ahead=1` emitted; in-sync → silent |
| AC4 | Regression test covers guard + kill switch | ✅ PASS | `tests/test-local-main-guard.sh` 24/24 assertions: guard blocks, kill switch (`ORCH_PROTECT_LOCAL_MAIN=0`) allows; installer removes guard when off |
| AC5 | Stray commits dc8449f/cccfbd5 resolved (preserved or discarded, decision documented) | ⏳ OPERATOR-BLOCKED | Commits remain dangling objects; local main already in sync with origin (drift=0); operator has been asked to decide — no code can resolve this |
| AC6 | Reconcile sweep warns when ticket sits in "Ready for Development" past N min with active lock | ✅ PASS | `check_claim_protocol` per-ticket in sweep; test: aged lock → WARN; throttled to 1 per episode; `ORCH_CLAIM_WARN_MINUTES=0` disables |

---

## Test Results

### `tests/test-local-main-guard.sh` (AC1, AC3, AC4, AC6)
```
Total:  24 | Passed: 24 | Failed: 0
ALL TESTS PASSED
```

**Coverage by section:**
- AC1/AC4 (direct hook): seat on main → BLOCKED (3 marker variants); seat on story branch → allowed; human on main → allowed; kill switch off → allowed
- AC1 end-to-end: real `git commit` with `ORCH_SEAT=qas` on local main → rejected (exit 1); human commit → allowed; seat on `ABS-1-auto` → allowed
- AC4 kill switch: installer removes guard when off; foreign hook left untouched (fail-open)
- AC3 drift: `LOCAL-MAIN-DRIFT` intent emitted with `ahead=1`; in-sync → silent; kill switch → no-op
- AC6 claim: aged lock + RfD → WARN; same episode throttled; status change clears episode; no lock → silent; minutes=0 → disabled

### `tests/test-harness-parity.sh` (governor-pin integrity)
```
Total:  6 | Passed: 6 | Failed: 0
ALL TESTS PASSED
```
Confirms editing `harness/claude/agents/_common-rules.md` (source) while `.claude/` shows old text is correct under ABS-94 governor-pin model.

### `tests/test-orchestrator.sh` (regression)
```
Total: 618 | Passed: 611 | Failed: 7
```
7 failures: harness-path provenance (2 cases, env-specific to stable vs. worktree checkout) and model-label/max-turns (5 cases, env-specific config). None touch the ABS-224 changes (`provision_local_main_guard`, `check_local_main_drift`, `check_claim_protocol`, pre-commit hook, spawn seam, `_common-rules.md`). Zero regressions introduced by this diff.

---

## Static Analysis

| Check | Files | Result |
|-------|-------|--------|
| `shellcheck -S warning` | `scripts/hooks/pre-commit-local-main-guard.sh`, `tests/test-local-main-guard.sh` | ✅ Clean (no warnings) |
| `bash -n` | All 4 modified scripts | ✅ Clean |

---

## Implementation Spot-Checks

**Guard placement (AC1, scope candidate 1):** Hook installs into `git-common-dir/hooks` via `provision_local_main_guard` at orchestrator startup, NOT in governor-generated `.claude/`. Worktrees share the common hooks dir, so one install covers main checkout and every worktree. ✅

**Seat-context propagation:** `orchestrator-spawn-claude.sh` exports `ORCH_SEAT="$ROLE"`, `ORCH_TICKET`, `ORCH_PROTECT_LOCAL_MAIN` before launching the claude process, so every Bash-tool subprocess a seat runs inherits the markers the guard reads. ✅

**Kill switch pattern (ABS-111):** `ORCH_PROTECT_LOCAL_MAIN` (default `1`) gates both the installer/remover and the drift check — toggling off truly disables the full mechanism. ✅

**Idempotency:** `provision_local_main_guard` detects its own install via the `ABS-224-local-main-guard` marker; re-runs do not re-clobber. Foreign hooks left untouched (fail-open, documented in code). ✅

**WARN-only detection (AC3, AC6):** Both `check_local_main_drift` and `check_claim_protocol` emit `intent` + `notify` with no auto-transition — the status chain remains seat-led. ✅

**AC5 state:** `git cat-file -t dc8449f` → `commit`; `git cat-file -t cccfbd5` → `commit`. Both are dangling objects in the object store, on no branch, not on origin. Local main drift = 0 (already in sync with origin/main before this ticket). The operator decision (preserve vs. discard) is surfaced on the ticket in the `be-developer` gate-results comment. No implementer action possible or appropriate.

---

## Closing Gate Note

**Before Done:** The operator must record their decision on ABS-224 for AC5 (whether to preserve the dangling QA-report content by landing it on a branch, or to discard it). This is a governance record, not a code change. POPM enforces at the Story Acceptance / closing gate.
