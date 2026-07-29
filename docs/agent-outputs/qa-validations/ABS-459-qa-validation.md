# QA Validation Report — ABS-459

**Ticket**: ABS-459 — Harden wrong-entry-guard test to be host-independent (hermetic ~/boilerplate-stable subtests)
**Branch**: `ABS-459-auto`
**Commit**: `8cfd5aa43ef35529bb09585520cb8ca0884c860d`
**QAS run date**: 2026-07-19
**Verdict**: ✅ APPROVED

---

## Environment

- Host: macOS (`/tmp -> private/tmp` symlink confirmed)
- Real `~/boilerplate-stable` present on this host: YES (same product)
- `ORCH_ROLE`, `ORCH_PACKET_FILE`, `ORCH_HARNESS_HOME` exported (orchestrator seat simulation): YES for Run 1
- Commit hash at validation time: `8cfd5aa43ef35529bb09585520cb8ca0884c860d`

---

## Scope Verification (AC6)

`git show 8cfd5aa --stat` → only `tests/test-wrong-entry-guard.sh` changed (10 insertions, 2 deletions).

`scripts/session-wrong-entry-guard.sh` last touched by commit `49ffabb` (ABS-92) — **untouched** in this change. ✅

---

## AC Verification

### AC1 — 13/13 on Linux-like clean runner (no ~/boilerplate-stable)

Run with `env -u ORCH_ROLE -u ORCH_PACKET_FILE -u ORCH_HARNESS_HOME` (no ambient markers):

```
bash tests/test-wrong-entry-guard.sh
Total:  13 | Passed: 13 | Failed: 0 | ALL TESTS PASSED
```

The test pins `HOME` to an empty tempdir internally, ensuring no host `~/boilerplate-stable` leaks. ✅

### AC2 — 13/13 on macOS (/tmp -> /private/tmp symlink)

This validation host IS macOS with `/tmp -> private/tmp` (verified via `ls -la /tmp`). Both runs (Run 1 with ambient ORCH_* set, Run 2 clean) produced 13/13 on this host. The guard already uses `pwd -P` throughout — the macOS symlink was confirmed NOT to be the failure cause. ✅

### AC3 — 13/13 with real ~/boilerplate-stable + real HOME + ambient ORCH_HARNESS_HOME

Run 1 conditions:
- `ORCH_ROLE=be-developer` exported
- `ORCH_PACKET_FILE=/tmp/fake-packet.json` exported
- `ORCH_HARNESS_HOME=/Users/sahan/local_projects/agentic-development-boilerplate` (real stable)
- Real `~/boilerplate-stable` present on this host

Result: 13/13, ALL TESTS PASSED. The `env -u ORCH_HARNESS_HOME` scrub in `run_guard` + the convention subtest prevents ORCH_HARNESS_HOME from overriding the test's fixture. ✅

### AC4 — Fire contract unchanged (no assert_exit/assert_contains values relaxed)

```
git show 8cfd5aa | grep "^[+-]" | grep -E "assert_(exit|contains)"
```
Output: **(empty)** — no assertion value lines were added or removed in the commit. ✅

All 13 assertion values confirmed in the test file (lines 106, 120, 123, 133, 143, 153, 162, 172, 176, 192):
- Positive-fire: `assert_exit "$ec" "2"` (×2 — all conditions hold, ~/boilerplate-stable convention)
- Escape-hatch: `assert_exit "$ec" "0" "SAW_GUARD_DISABLE=1 -> exit 0 (escape hatch)"`
- All other guards: `assert_exit "$ec" "0"` (no-op conditions)

Original fire conditions a/b/c/d and SAW_GUARD_DISABLE=1 hatch preserved byte-for-byte. ✅

### AC5 — run-all.sh reports PASS

```
bash tests/run-all.sh test-wrong-entry-guard.sh
=== run-all: 1 files, TEST_JOBS=4 ===
--- phase 2: 1 files (TEST_JOBS x1 each) ---
  PASS test-wrong-entry-guard.sh
=== ALL 1 FILES PASSED ===
```

✅

### AC6 — Scope: only test file changed, guard behavior byte-for-byte equivalent

`git show 8cfd5aa --stat` → `tests/test-wrong-entry-guard.sh | 12 ++++++++++--` (1 file changed).
`scripts/session-wrong-entry-guard.sh` not in commit; last touched by ABS-92 (49ffabb). ✅

---

## Additional Checks

- `bash -n tests/test-wrong-entry-guard.sh` → **CLEAN** ✅
- `bash -n scripts/session-wrong-entry-guard.sh` → **CLEAN** ✅
- No regression in the guard's behavior: spawn-marker exemption subtests (ORCH_ROLE/ORCH_PACKET_FILE) still pass with per-test values applied AFTER env -u scrub. ✅

---

## Summary Table

| AC | Criterion | Result | Evidence |
|----|-----------|--------|----------|
| AC1 | 13/13 on clean runner (no ~/boilerplate-stable) | ✅ PASS | Run 2: 13/13, exit 0, ALL TESTS PASSED |
| AC2 | 13/13 on macOS /tmp→/private/tmp | ✅ PASS | This host IS macOS with /tmp symlink; 13/13 both runs |
| AC3 | 13/13 with real ~/boilerplate-stable + ambient ORCH_HARNESS_HOME | ✅ PASS | Run 1: ORCH_HARNESS_HOME set, real ~/boilerplate-stable present; 13/13 |
| AC4 | Fire contract unchanged (no assertion values relaxed) | ✅ PASS | git show grep empty; all 13 assert_exit values confirmed |
| AC5 | run-all.sh reports PASS | ✅ PASS | `ALL 1 FILES PASSED` |
| AC6 | Scope: only test file changed, guard untouched | ✅ PASS | 1-file diff; guard last touched by ABS-92 |

---

## Verdict

**✅ APPROVED — all 6 ACs PASSED**

- Root cause confirmed independently: ambient `ORCH_ROLE`/`ORCH_PACKET_FILE`/`ORCH_HARNESS_HOME` leakage (not `/tmp` symlink)
- Fix is minimal, targeted (`env -u` at 2 invocation sites), and hermetic
- Guard script untouched; fire conditions a/b/c/d and SAW_GUARD_DISABLE=1 hatch preserved
- No design flag → exit to Story Acceptance
