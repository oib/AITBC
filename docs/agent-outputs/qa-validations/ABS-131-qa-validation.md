# QA Validation Report — ABS-131

**Ticket:** ABS-131 — Worktree-Provisioning: settings.local.json + lokale Freigaben reisen in den Spawn-Worktree
**QAS seat:** qas
**Date:** 2026-07-08
**Commit:** `db19e93` on branch `ABS-131-auto`
**Branch:** ABS-131-auto (working tree clean)
**Files changed:** 3 files, +167 insertions, 0 deletions

---

## Validation Method

Tests run **from the ABS-131 worktree** (`tmp/ABS-131-work`), per SA reviewer note:
> "The test suite must run *from the ABS-131 worktree*. The main checkout sits on the ABS-138 branch and does NOT contain this diff — a naive run there shows 0 ABS-131 lines."

Command: `bash tests/test-orchestrator.sh 2>&1 | grep -A 2 "ABS-131"`
Independent run (not trusting handoff claims): **confirmed by direct execution**.

---

## Acceptance Criteria Verification

| AC | Criterion | Result | Evidence |
|----|-----------|--------|----------|
| AC1 | Provisioning copies `settings.local.json` into `tmp/<ticket>-work/.claude/` (executed test, not grep) | ✅ PASS | `PASS ABS-131: settings.local.json provisioned into the worktree .claude/` + `PASS ABS-131: operator's own grants are preserved in the copy` |
| AC2 | Missing source = graceful no-op with log event, no crash (executed test) | ✅ PASS | `PASS ABS-131: absent source logs a no-op event` + `PASS ABS-131: worktree still provisioned when source is absent (no crash)` |
| AC3 | Extra-allow mechanism tested (default + override) | ✅ PASS | `PASS ABS-131: default extra-allow (Write(scripts/**)) merged in` + `PASS ABS-131: default extra-allow (Edit(harness/**)) merged in` + `PASS ABS-131: override grant Write(custom/**) applied` + `PASS ABS-131: override grant Bash(echo:*) applied` + `PASS ABS-131: override REPLACES the default (no scripts/** leak)` |
| AC4 | ORCHESTRATOR_SOP section updated (grep-AC) | ✅ PASS | `grep "Local permissions travel\|ORCH_WORKTREE_EXTRA_ALLOW" docs/sop/ORCHESTRATOR_SOP.md` → subsection §"Local permissions travel into the worktree (ABS-131)" at line 373 + env-knob table row at line 254 |

**All 4 ACs: PASS**

---

## Test Suite Results

| Category | Tests | Status |
|----------|-------|--------|
| ABS-131 suite (copy-present, no-op, default extra-allow, override) | **9/9 PASS** | ✅ |
| Pre-existing FAILs (run.log/telemetry/provenance — sandbox artifacts) | **17 FAIL** | ⚠️ Pre-existing, unrelated |
| All other tests | ~307 PASS | ✅ |

**Total: 316 PASS, 17 FAIL (all 17 FAILs are pre-existing self-hosting-sandbox artifacts)**

Pre-existing failures are in:
- `run.log` event assertions (no run.log exists in the ABS-131-work sandbox)
- Telemetry tool-counting tests
- Session-invalidation log assertions
- Provenance `harness=<stable repo>` tests (stable governs dev, not the worktree)

These are **identical to the baseline** established before this diff. **Zero regressions** from ABS-131.

---

## Implementation Spot-Check

### `provision_worktree_settings()` — Correctness

- **Phase 1 (copy):** `[ -f "$src" ] && cp "$src" "$dst"` with log; else log no-op. Never crashes. ✅
- **Phase 2 (merge):** `[ -n "${ORCH_WORKTREE_EXTRA_ALLOW:-}" ] || return 0` (empty = skip); `command -v jq` guard; atomic `tmp + mv` with `jq unique` dedup. ✅
- **Scope guard:** Never writes to `$ORCH_STATE_ROOT/.claude/` — only `$wt/.claude/`. ✅
- **Call site:** `[ "$rc" -eq 0 ] && provision_worktree_settings "$wt"` in `ensure_worktree()` AFTER `git worktree add` — only on a freshly-provisioned tree (reuse short-circuits at `[ -d "$wt" ] && return 0`). ✅

### `#PATH_DECISION` resolved (per SA)

Both options shipped: hardcoded safe default (`Write/Edit scripts/**+harness/**`) AND `ORCH_WORKTREE_EXTRA_ALLOW` override (empty disables). Documented in code comment, SOP, and env-knob table. ✅

### Security

Live loop lives in main checkout, not `tmp/<ticket>-work` → `Write(harness/**)` in the worktree cannot alter the running governor. Explicitly noted in code comment and SOP. ✅

---

## Scope Compliance

| Scope Item | Status |
|-----------|--------|
| Provisioning copies settings.local.json into worktree | ✅ Implemented |
| Extra-allow configurable (default + `ORCH_WORKTREE_EXTRA_ALLOW` override) | ✅ Implemented |
| SOP documentation updated | ✅ Done |
| Cleanup behavior documented | ✅ "discarded with the worktree, no cleanup step needed" |
| **Out:** Main-checkout allowlist NOT modified | ✅ Verified (only `$wt/.claude/` written) |
| **Out:** settings.local.json NOT committed | ✅ Gitignored in worktree |

---

## Verdict

**✅ APPROVED for RTE**

All 4 acceptance criteria met via independent test execution. 9/9 ABS-131 tests PASS. Zero regressions (17 pre-existing sandbox failures unchanged from baseline). Implementation is best-effort, scope-compliant, and security-sound. SOP documentation complete.

**Next:** RTE opens PR for branch `ABS-131-auto` → merge to epic integration branch.

---

## Handoff Record

```
role: qas
ticket: ABS-131
exit-state: Ready for Human Acceptance
transition: In Test -> Ready for Human Acceptance (2026-07-08)
verdict: APPROVED

AC/DoD: all 4 PASS (verified independently from ABS-131 worktree)
Tests: 9/9 ABS-131 PASS | 316 total PASS | 17 pre-existing FAILs (sandbox artifacts)
Regressions: 0
Comment posted: gate-results on ABS-131
Report: docs/agent-outputs/qa-validations/ABS-131-qa-validation.md

next: Orchestrator/RTE opens PR for branch ABS-131-auto -> epic integration branch
```
