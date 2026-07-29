# QA Validation Report — ABS-398

**Ticket**: ABS-398 — Degraded merge-base rebase check for the jira/mock profile + behaviour docs  
**Reviewer**: QAS (In Test gate)  
**Branch**: `ABS-398-auto`  
**Commit**: `91f351d`  
**Date**: 2026-07-17  
**Verdict**: ✅ APPROVED

---

## Scope Reviewed

3 files, +214/-0 lines (commit `91f351d`):

| File | Kind |
|------|------|
| `scripts/rebase-gate-check.sh` | New — git-only degraded rebase-gate (executable) |
| `profiles/neutral/adapters/git.md` | Updated — "Degraded rebase-gate" section added |
| `tests/test-rebase-gate-check.sh` | New — real-repo integration tests (executable) |

---

## Acceptance Criteria Verification

### AC1 — Seat can determine rebase-needed vs clean via `git merge-base` (PASS)

The `readiness` subcommand wraps `git merge-base --is-ancestor <epic> <story>`:
- exit 0 = epic tip contained in story branch = `clean`
- exit 1 = epic has advanced past story = `rebase-needed`

**Evidence — test section A** (run independently by QAS):

```
PASS  clean story (contains the epic tip) -> readiness exit 0 (clean)
PASS  stale story (epic advanced past it) -> readiness exit 1 (rebase-needed)
```

### AC2 — Behaviour documented: trigger point, block condition, rebase-record path (PASS)

`profiles/neutral/adapters/git.md` "Degraded rebase-gate (jira/mock profile)" section covers:

| Required element | Present? | Location |
|-----------------|----------|----------|
| Trigger point | ✅ | "at Story-Acceptance exit, immediately before the transition — after QAS" (line 44) |
| Block condition | ✅ | "rebase-needed blocks … unless the same move documents a rebase" (line 54) |
| Rebase-record path | ✅ | "rebase onto epic tip, re-run readiness to confirm clean, then transition with 'rebased …' in the reason" (line 60) |

### AC3 — Degraded path reaches the same accept/reject as native gate (PASS)

Three native-gate cases pinned in test section B — all match the native guard (ABS-397):

| Case | Native outcome | Degraded outcome | Test result |
|------|---------------|-----------------|-------------|
| clean | ACCEPT | ACCEPT (exit 0) | PASS |
| rebase-needed + no documented rebase | REJECT | REJECT (exit 1) | PASS |
| rebase-needed + 'rebased' in reason | ACCEPT | ACCEPT (exit 0) | PASS |

---

## Test Results

### Direct test run (`tests/test-rebase-gate-check.sh`)

```
=== degraded rebase-gate (jira/mock, ABS-398) ===

A. readiness — clean vs rebase-needed via git merge-base (AC1)
  PASS  clean story (contains the epic tip) -> readiness exit 0 (clean)
  PASS  stale story (epic advanced past it) -> readiness exit 1 (rebase-needed)

B. gate — same accept/reject outcome as the native guard (AC3)
  PASS  clean -> gate ACCEPT (exit 0)
  PASS  rebase-needed + no documented rebase -> gate REJECT (exit 1)
  PASS  rebase-needed + 'rebased' in the reason -> gate ACCEPT (exit 0)

C. bad input fails closed
  PASS  unknown epic ref -> exit 64 (fails closed, not a false clean)
  PASS  missing args -> exit 64

=== Results ===
  Total:  7
  Passed: 7
  Failed: 0

All rebase-gate-check tests passed.
EXIT_CODE: 0
```

**7/7 PASS** — verified independently by QAS.

### End-to-End documented recipe drive

QAS independently drove the documented procedure against a real throwaway git repo:

```
Step 1: gate with plain reason (no 'rebased')
  stderr: REJECT: merge_readiness=rebase-needed and no documented rebase — rebase onto
          epic/ABS-000-integration, then retry (record 'rebased ...' in the move)
  exit: 1   ✅ REJECT as expected

Step 2: git rebase  exit: 0  (rebase succeeds)
Step 2b: readiness after rebase
  stdout: clean: story-branch already contains the tip of epic/ABS-000-integration (no rebase needed)
  exit: 0  ✅ clean after rebase

Step 3: gate with 'rebased' in reason
  stdout: ACCEPT: merge_readiness=clean
  exit: 0  ✅ ACCEPT after rebase
```

Recipe produces the documented REJECT → rebase → ACCEPT flow correctly.

---

## Additional Checks

| Check | Result |
|-------|--------|
| Script executable bit | ✅ `-rwxr-xr-x` |
| Test file executable bit | ✅ `-rwxr-xr-x` |
| Bad-ref fails closed (exit 64, not false clean) | ✅ (test section C, 2/2 PASS) |
| Primitive reuses `git merge-base --is-ancestor` from `merge-status.sh on-target` | ✅ verified |
| `tests/run-all.sh` picks up test via `test-*.sh` glob | ✅ glob confirmed in run-all.sh line 42 |
| Scope held (ABS-395 native webhook / ABS-397 native guard out of scope) | ✅ |

---

## Non-Blocking Note (inherited from architecture review, not a bounce)

The evidence match in `cmd_gate` is `grep -qiE 'rebased'` (no word boundary), while the native
guard and the doc's stated equivalence use `/\brebased\b/i`. The divergence fires only in the
fail-open direction on contrived substrings (e.g. "rebasedness"). The reason is authored by the
trusted QAS/PO seat — real-world risk is negligible. A one-flag `grep -iwE` change would restore
exact fidelity. Logged for a future touch; does not affect this ticket's verdict.

---

## Final Verdict

| Criterion | Result |
|-----------|--------|
| AC1 (readiness via `git merge-base`) | ✅ PASS |
| AC2 (behaviour documented: trigger / block / rebase-record) | ✅ PASS |
| AC3 (degraded reaches same accept/reject as native) | ✅ PASS |
| 7/7 tests pass (independent QAS run) | ✅ PASS |
| E2E documented recipe drives correctly | ✅ PASS |
| Fails closed on bad refs | ✅ PASS |

**QAS Verdict: APPROVED for Story Acceptance**  
(No `design` flag — routing directly to Story Acceptance, not Design Test.)
