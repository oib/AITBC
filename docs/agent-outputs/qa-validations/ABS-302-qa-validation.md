# QA Validation Report — ABS-302

**Ticket**: ABS-302 — Kleinbefunde bundle: kind-header parsing, umlaut-safe Jira writes, operator-reaching notifications, account-switch session invalidation
**QAS Actor**: qas
**Date**: 2026-07-15
**Branch**: `ABS-302-auto` @ `4d593e2`
**Verdict**: ✅ **APPROVED**

---

## Summary

All 4 acceptance criteria validated. 13/13 ABS-302 assertions PASS. All Iteration-1 review issues (system-architect bounce at `6591e24`) are confirmed resolved in the final commit `4d593e2`.

---

## Test Evidence

### Isolated ABS-302 Suite Run

Command: `bash /tmp/run-abs302-test.sh` (sourced `tests/orchestrator.d/ABS-302-kleinbefunde.sh` into minimal harness identical to `tests/test-orchestrator.sh`)

```
Running ABS-302 standalone test...

=== ABS-302 Kleinbefunde bundle (kind-header / umlaut / account-switch / PushNotification) ===

  [AC1] kind: header correctness
DEMO-1: comment added
  PASS ABS-302 AC1: kind: gate-results preserved on round-trip (not silently notification)
  PASS ABS-302 AC1: kind: notification not present when gate-results was written
  PASS ABS-302 AC1: jira-tracker.sh parser has recovery path for header on non-first line

  [AC2] umlaut-safe Jira writes (--data @file) + äöüß round-trip via jira-tracker.sh
  PASS ABS-302 AC2: no inline '-d <body>' curl calls in scripts/jira-tracker.sh
  PASS ABS-302 AC2: --data-binary/@file present in jira-tracker.sh (1 uses)
  PASS ABS-302 AC2: jira-tracker.sh round-trip preserves äöüß byte-identical (adf_wrap + adf_to_text)

  [AC3] account-switch invalidates cached sessions
  PASS ABS-302 AC3: session file removed after account switch
  PASS ABS-302 AC3: run.log contains ACCOUNT-SWITCH event
  PASS ABS-302 AC3: ACCOUNT-SWITCH line names the stored account
  PASS ABS-302 AC3: ACCOUNT-SWITCH line names the current account (dir fallback)

  [AC4] PushNotification rule in operator SOP
  PASS ABS-302 AC4: ORCHESTRATOR_SOP.md PushNotification mentioned
  PASS ABS-302 AC4: ORCHESTRATOR_SOP.md osascript (macOS dialog) mentioned
  PASS ABS-302 AC4: ORCHESTRATOR_SOP.md session-local watcher rule mentioned

=== ABS-302 Test Results ===
  Total:  13
  Passed: 13
  Failed: 0
  ALL TESTS PASSED
EXIT=0
```

### jira-tracker.sh Test Suite

Command: `bash tests/test-jira-tracker.sh`

```
=== Test Results ===
  Total:   136
  Passed:  136
  Skipped: 1
  Failed:  0
  ALL TESTS PASSED
```

---

## Acceptance Criteria Checklist

### AC1 — `kind:` header written correctly, never silently `notification`

- [x] Round-trip test: comment posted with `--kind gate-results`, read back — kind is `gate-results`, NOT `notification` → **PASS**
- [x] Parser recovery path confirmed: `grep -c 'recovered kind=' scripts/jira-tracker.sh` → `1` (non-zero) → **PASS**
- [x] Implementation: `post_structured_comment` constructs `[kind: $kind | actor: $actor]` as line 1 of every comment body
- [x] Implementation: parser `adf_to_text` (lines 754–785) recovers `kind`/`actor` from a non-first-line `[kind:…]` header via a linear scan, adopting the recovered values — never silently falls through to `kind: notification`
- [x] Iteration-1 issue resolved: unreachable writer guard removed from current code (not present in `4d593e2`)

### AC2 — All Jira write paths use `--data @file`; `äöüß` round-trip

- [x] Grep for inline `-d '<body>'` returns zero lines (excluding comments and `tr -d` uses) → **PASS**
- [x] `--data-binary "@$bodyfile"` present at `scripts/jira-tracker.sh:342` → **PASS**
- [x] `äöüß` round-trip via `adf_wrap` + `adf_to_text` with JIRA_CURL offline shim → **PASS**
- [x] Iteration-1 issue resolved: round-trip test was absent in `6591e24`, present and passing in `4d593e2`

### AC3 — Account-switch invalidates cached sessions; runlog records change

- [x] Session file removed after account switch (stored ≠ current) → **PASS**
- [x] `run.log` contains `ACCOUNT-SWITCH` → **PASS**
- [x] `ACCOUNT-SWITCH` line names stored account → **PASS**
- [x] `ACCOUNT-SWITCH` line names current account (dir fallback when no `.claude.json`) → **PASS**
- [x] `current_claude_account()` at line 5429 reads `oauthAccount.accountUuid` from `.claude.json` when present, composed as `uuid@configdir` — correctly detects CLI account switches even in the same config dir
- [x] Fallback to config-dir path when `.claude.json` absent or has no UUID (pre-login / enterprise-SSO) — documented accurately in SOP
- [x] `check_account_switch()` called at startup line 5897
- [x] Iteration-1 issue resolved: `current_claude_account()` was dir-only in `6591e24`; uses `accountUuid` in `4d593e2`

### AC4 — PushNotification rule documented in operator SOP

- [x] `docs/sop/ORCHESTRATOR_SOP.md` contains `PushNotification` → **PASS**
- [x] `docs/sop/ORCHESTRATOR_SOP.md` contains `osascript` → **PASS**
- [x] `docs/sop/ORCHESTRATOR_SOP.md` contains `session-local` → **PASS**
- [x] Changelog entry at `docs/sop/ORCHESTRATOR_SOP_CHANGELOG.md` references ABS-302 and v1.7

---

## Scope of Changes (ABS-302 commits only)

Files modified (confirmed via `git diff 4b9ffaa..HEAD --name-only`):
- `docs/sop/ORCHESTRATOR_SOP.md` — AC4 additions
- `docs/sop/ORCHESTRATOR_SOP_CHANGELOG.md` — v1.7 changelog
- `scripts/jira-tracker.sh` — AC1 parser recovery + AC2 (already used `--data-binary`)
- `scripts/orchestrator.sh` — AC3 `current_claude_account()` + `check_account_switch()`
- `tests/orchestrator.d/ABS-302-kleinbefunde.sh` — new test file (13 assertions)

**`tests/test-orchestrator.sh` was NOT modified** by ABS-302 commits — confirmed.

---

## Pre-Existing Suite Failures (Not ABS-302)

The full `tests/test-orchestrator.sh` suite has pre-existing failures unrelated to ABS-302:
- **ABS-101** section: SKIP-UNLABELLED behavior tests (4 failures)
- **ABS-92** section: harness provenance path assertions (2 failures)

These exist in the base commit `4b9ffaa` and were not introduced by any ABS-302 commit. They are outside ABS-302 scope.

The **jira-tracker test suite** (136/136) passes cleanly.
The **ABS-302 specific suite** (13/13) passes cleanly.

---

## Iteration-1 Review Issues — All Resolved

| Issue | Status |
|-------|--------|
| Test-id capture from title (`grep '[A-Z]+-[0-9]+'` matched own ticket id) | ✅ Fixed: `\| tail -1` in `4d593e2` |
| AC1 defect still live (misplaced kind header → silent `notification`) | ✅ Fixed: parser recovery path in `5ff221f` |
| AC2 `äöüß` round-trip test absent | ✅ Fixed: test present and PASS in `928dc6d` |
| Unreachable writer guard (dead code) | ✅ Removed (not in `4d593e2`) |
| `current_claude_account()` dir-only (can't detect same-dir account switch) | ✅ Fixed: `accountUuid@configdir` in `5ff221f` |

---

## Definition of Done

- [x] All 4 ACs tested → PASS
- [x] All 13 ABS-302 assertions PASS (exit 0)
- [x] jira-tracker.sh test suite: 136/136 PASS
- [x] No regressions introduced (ABS-302 commits: 5 files, zero touch on `tests/test-orchestrator.sh`)
- [x] Implementation follows in-repo idiom (`ORCH_*` kill-switch, `runlog` audit trail, per-story test include)
- [x] ADR-A-0010 (minimal change): surgical fixes only, no structural change
- [x] No `design` flag → no Design Test gate needed

---

**Final Verdict: ✅ APPROVED for Story Acceptance**
