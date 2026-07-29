# QA Validation: ABS-280
**Guard: every tests/fixtures/ file on disk is tracked**
**Date:** 2026-07-14
**Actor:** qas
**Commit under review:** `7dbb450` (`test(fixtures): guard that every tests/fixtures/ file on disk is tracked [ABS-280]`)
**Branch:** `ABS-280-auto` → `origin/ABS-280-auto` (confirmed pushed)
**Diff scope:** 1 file added (`tests/test-fixture-integrity.sh`), 0 modified, 0 deleted

---

## Validation Method

Gating from committed state to avoid repeating the ABS-218 mistake (first QAS pass approved 28/28 from a working tree; defect surfaced at PO Story Acceptance). The guard's own deliverable must survive checkout, so the working tree provides no valid gate signal. I ran `git show 7dbb450:tests/test-fixture-integrity.sh` to read the committed blob before executing.

---

## AC Validation Results

| AC | Criterion | Result | Evidence |
|----|-----------|--------|----------|
| AC1 | Guard asserts every file in `tests/fixtures/` is in the index; exits non-zero + prints offending paths on violation | ✅ PASS | `git ls-files --others -- tests/fixtures/` (no `--exclude-standard` — confirmed in committed blob); 8/8, exit 0 on clean tree; probe run confirmed exit 1 + path printed |
| AC2 | Failure path driven by a test; both sides of boundary asserted | ✅ PASS | Internal: `*.log` probe confirmed ignored via `git check-ignore -q`; guard exits 1 while probe present, exits 0 once removed via `trap cleanup EXIT INT TERM`. Positive side: `tests/fixtures/skill-mining/state/run.log` is tracked and not flagged. External probe I planted independently also detected (`.gitignore:52:*.log`) |
| AC3 | Failure message names cause and fix | ✅ PASS | Observed failure output: cause = `.gitignore:52:*.log  tests/fixtures/.abs280-qas-verify-test.log`; effect = "your local run is GREEN (the file is on disk) but a clean checkout is RED"; fix = targeted negation per `.gitignore:58-59` precedent |
| AC4 | Runs in CI with no CI edit; self-wires through `tests/test-*.sh` glob | ✅ PASS | `.github/workflows/tests.yml:60` uses `TESTS=(tests/test-*.sh)`; `scripts/pre-release-check.sh:98` uses `for test_file in tests/test-*.sh`; `tests/test-fixture-integrity.sh` confirmed in glob output. No CI edit present in diff. |
| AC5 | Passes on current tree (51/51 tracked); `tests/test-skill-mining.sh` stays 28/28 | ✅ PASS | `bash tests/test-fixture-integrity.sh` → **8/8, exit 0** (51 on disk / 51 tracked); `bash tests/test-skill-mining.sh` → **28/28, exit 0**. No fixtures touched. |

---

## Test Output

### tests/test-fixture-integrity.sh (primary)

```
=== tests/fixtures/ index integrity (ABS-280) ===

--- AC1/AC5: every fixture on disk is in the index ---
  PASS all 51 fixture files on disk are tracked (51 in index)
  PASS on-disk count matches index count

--- AC2: the guard fires (it cannot go inert) ---
  PASS the probe is genuinely .gitignore'd (reproduces the ABS-218 blind spot)
  PASS guard detects the swallowed fixture
  PASS guard exits non-zero while the probe is present (AC1)
  PASS the run.log fixture is in the index (the .gitignore:58-59 negation still holds)
  PASS guard does not flag that already-tracked fixture
  PASS guard exits 0 again once the probe is removed (no residue)

=== Test Results ===
  Total:  8
  Passed: 8
  Failed: 0
  ALL TESTS PASSED
```

### tests/test-skill-mining.sh (AC5 guard)

```
Results: Total: 28  Pass: 28  Fail: 0
SKILL-MINING TESTS PASSED
```

---

## AC3 Failure Path Verification (independent probe)

I externally planted `tests/fixtures/.abs280-qas-verify-test.log` and ran the guard:

```
  FAIL fixture files exist on disk but are NOT in the index:
      tests/fixtures/.abs280-qas-verify-test.log
    Cause: a .gitignore pattern is swallowing them. Which one:
        .gitignore:52:*.log    tests/fixtures/.abs280-qas-verify-test.log
    Effect: your local run is GREEN (the file is on disk) but a clean
            checkout is RED — the file never reaches CI or a reviewer.
    Fix:    add a targeted negation to .gitignore, as .gitignore:58-59
            already does for run.log:  !tests/fixtures/<path>
            then: git add -f <path> && git commit
```

AC3 verified. The message names cause, effect, and fix. Cleaned up after probe.

---

## Delivery Verification

- `git log --oneline -1` → `7dbb450 test(fixtures): guard that every tests/fixtures/ file on disk is tracked [ABS-280]`
- `git ls-remote origin ABS-280-auto` → `7dbb450c12d7516a626891e9e96710a2e6eee1a0` (committed and pushed)
- `git diff --name-only ... origin/epic/ABS-278-v2252-hotfix-consumer-feedback...HEAD` → `tests/test-fixture-integrity.sh` (one file only)
- `git status --short` → clean (no residue from test probes)
- Commit message is conventional, cites `[ABS-280]`

---

## Flags

Ticket flags: **none** (no design/security/data surface). Exit target: **Story Acceptance**.

---

## Design Note (forward record)

This guard is always green in CI by construction: a clean checkout cannot hold an untracked fixture, so `git ls-files --others` is empty there. Its protective value lives entirely in the working tree and `pre-release-check.sh`. That is precisely where ABS-218's blind spot sat. The scoping to `tests/fixtures/` is correct (widening to `tests/` would make the guard wrong). Nobody should read this story landing as closing the broader "commits exist on a shipping branch" hole — that belongs in ABS-266.

---

## Verdict

**✅ APPROVED**

All 5 ACs verified from committed state (`7dbb450` at origin). No bounce required. Transitioning to **Story Acceptance**.
