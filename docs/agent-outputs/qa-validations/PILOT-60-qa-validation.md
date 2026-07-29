# QA Validation — PILOT-60

**Branch**: PILOT-60-auto  
**Commits**: `ee328369` `8dc38a79` `dac45295` `df0c1313`  
**HEAD**: df0c1313da6ec219c1a3de9a361bf649f476ea53  
**Verdict**: ✅ APPROVED

---

## Files changed (7 across 4 commits)

| File | Purpose |
|---|---|
| `scripts/lib/run-with-timeout.sh` | new — portable watchdog; prefers `timeout -k 5`/`gtimeout -k 5`, falls back to bash-native |
| `scripts/pre-release-check.sh` | sources watchdog; each suite runs under 900s budget; overrun exits 124 as named TIMED OUT; stale warning removed |
| `tests/run-all.sh` | same integration; `run_with_timeout` + `_rwt_kill_tree` exported to parallel workers |
| `tests/test-release-gate-timeout.sh` | new — falsification suite (14 assertions covering AC1/AC2/AC3) |
| `tests/test-signal-trap-hygiene.sh` | new — standing signal-trap audit (2 assertions); sources sandbox-guard |
| `tests/test-fixture-integrity.sh` | split EXIT trap from INT/TERM; sources sandbox-guard (df0c1313 fix) |
| `docs/agent-outputs/qa-validations/PILOT-60-qa-validation.md` | this report |

---

## AC verification

### AC1: per-suite timeout in pre-release-check.sh and run-all.sh

Both scripts source `scripts/lib/run-with-timeout.sh` and call `run_with_timeout "$SUITE_TIMEOUT"` for every suite. Default budget: 900s (overridable via `PRE_RELEASE_SUITE_TIMEOUT` / `RUN_ALL_SUITE_TIMEOUT`). Overrun returns 124, logged as `TIMED OUT (exceeded Xs budget)`. The stale `"without a per-suite timeout"` warning is gone from both scripts. The latent `timeout 120` in pre-release-check.sh is replaced.

**AC1: PASS**

### AC2: signal-trap audit — all INT/TERM traps exit; none combined with EXIT

```
$ bash tests/test-signal-trap-hygiene.sh
=== signal-trap hygiene: no returning INT/TERM handler ===
  PASS every INT/TERM trap under scripts/ and tests/ exits (and is split from EXIT)
=== self-check: the guard catches a known-bad trap ===
  PASS 'trap ... EXIT INT TERM' is recognised as the antipattern

=== Test summary ===
PASS 2/2 tests passed
```

Standing guard scans `scripts/` and `tests/` on every run. `_rwt_kill_tree` uses only `pgrep -P` (ABS-243 compliant).

**AC2: PASS**

### AC3: hanging fixture reported by name as FAIL within budget; no survivor

```
$ bash tests/test-release-gate-timeout.sh
=== AC1: run_with_timeout — own rc in time, 124 on overrun ===
  PASS AC1: passes through the command's own exit code (7)
  PASS AC1: a command that finishes within budget returns 0
  PASS AC1: an overrunning command returns 124 (GNU timeout code)
  PASS AC1: the timeout fires within budget + grace (2 <= 15)
=== AC2: a timed-out command leaves no surviving descendant ===
  PASS AC2: the hanging child run returns 124
  PASS AC2: no descendant survives the timeout (tree reaped)
=== AC3: run-all.sh names a hanging fixture as a timeout FAIL ===
  PASS AC3: run-all exits non-zero on a hanging suite (rc=1)
  PASS AC3: run-all names the offending suite
  PASS AC3: run-all labels the overrun as a timeout
  PASS AC3: run-all completes within budget + grace (no hang) (2 <= 20)
  PASS AC3: run-all leaves no surviving suite process
=== AC3: pre-release-check.sh is pinned to the shared watchdog ===
  PASS AC3: pre-release-check sources the watchdog helper
  PASS AC3: pre-release-check runs suites under the budget
  PASS AC3: the 'no per-suite timeout' warning is gone

=== Test summary ===
PASS 14/14 tests passed
```

**AC3: PASS**

---

## Sandbox-guard compliance (df0c1313)

`test-signal-trap-hygiene.sh` and `test-fixture-integrity.sh` both mention `backend-shipper.sh` in comments, triggering the mechanical sandbox-guard-check. Commit `df0c1313` adds the required `source sandbox-guard.sh` to both files.

```
$ bash tests/test-sandbox-guard.sh   (excerpt)
...
== CI check passes on the real repo ==
  PASS sandbox-guard-check exits 0 on repo
  PASS reports OK
...
sandbox-guard: 12/12 passed, 0 failed
```

```
$ bash tests/test-fixture-integrity.sh   (excerpt)
...
=== Test Results ===
  Total:  8
  Passed: 8
  Failed: 0
  ALL TESTS PASSED
```

---

## Test run proof

```
commit: df0c1313da6ec219c1a3de9a361bf649f476ea53
branch: PILOT-60-auto
test-release-gate-timeout.sh:   14/14 passed
test-signal-trap-hygiene.sh:     2/2 passed
test-fixture-integrity.sh:       8/8 passed
test-sandbox-guard.sh:          12/12 passed
```

No design flag. No RLS, DB, or auth surface touched.

---

**Verdict: APPROVED — releasing to Story Acceptance**  
QAS iteration: 0 of 3  
