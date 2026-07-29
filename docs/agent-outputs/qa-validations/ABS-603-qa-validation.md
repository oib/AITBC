# QA Validation — ABS-603

**Ticket**: ABS-603 — Suite-Budget hat nur 12 % Reserve  
**Commit**: e5693642 on `refs/remotes/gitlab/ABS-603-auto`  
**QAS run date**: 2026-07-27  
**Verdict**: **APPROVED**

---

## AC Verification

### AC1 — Reserve measured and documented; no guessed value

**PASS**

`docs/release/SUITE-BUDGET.md` documents two measured datapoints:
- Isolated: 790 s (Pilot 8, commit `7d7d3a72`, TEST_JOBS=4, 1455/1455 assertions)
- Under one parallel seat: > 900 s (same-day incident, concurrent RTE run of the tentpole)

The 1800 s budget is derived from those figures with explicit rationale ("two 4-job runs contending for a 4-core box roughly halve each other's CPU → loaded runtime ~1200–1600 s; budget clears that band with margin"). `measure-suite-budget.sh --both` re-measures both modes at each release so the history table in SUITE-BUDGET.md stays current rather than quoting stale numbers.

### AC2 — Budget holds under parallel load OR staged runner evaluated

**PASS**

`scripts/pre-release-check.sh` line: `SUITE_TIMEOUT="${PRE_RELEASE_SUITE_TIMEOUT:-1800}"` — default raised from 900 s to 1800 s.

`tests/staged-suite.sh` is evaluated in SUITE-BUDGET.md §"Evaluation of the staged runner" as the durable structural fix: deterministic partition at the tentpole's safe seam, HEAD-bound completeness ledger, each stage individually under the 10-min tool-call cap. The document explains why ABS-603 does not wire it in yet (a larger plumbing change) and identifies the reserve sensor as the trigger to adopt it before the next red-line.

### AC3 — Gate distinguishes "budget-overrun" from "test failure"

**PASS**

`scripts/lib/suite-budget.sh` `classify_suite` returns `ops-overbudget` for rc 124 (watchdog kill). In `pre-release-check.sh` that maps to `check_ops` (OPS counter), which emits a `◑` (cyan) line and a non-blocking summary:

```
Operational: N — a suite ran over its wall-clock budget.
This is a load/infrastructure signal, NOT a broken test; it does not block release.
```

A real test failure (`rc ≠ 0`, `rc ≠ 124`) maps to `check_fail` (FAIL counter, exit 1). The summary header shows `Passed: N  Failed: N  Warnings: N  Operational: N` as four distinct columns. An OPS-only run exits 0.

### AC4 — Sensor fires when reserve < 25 %

**PASS**

`RESERVE_WARN_PCT="${SUITE_RESERVE_WARN_PCT:-25}"` in `pre-release-check.sh`. When `classify_suite` returns `pass-low-reserve`, the gate emits:

```
⚠  test-orchestrator: LOW RESERVE — <elapsed>s of <budget>s (N% left, < 25% threshold); see docs/release/SUITE-BUDGET.md
```

Unit tests in `tests/test-suite-budget.sh` cover the boundary: exactly 25 % reserve → `pass`; 24 % reserve → `pass-low-reserve`. The current Pilot-8 isolated figure (790 s / 1800 s = 56 % reserve) clears the threshold; the sensor fires when growth closes the gap to under 450 s remaining.

### AC5 — Measurement repeated each release; growth curve recorded

**PASS**

`docs/release/PRE-RELEASE-CHECKLIST.md` §1 now includes a mandatory step:

```
bash scripts/measure-suite-budget.sh --both --record
```

`measure-suite-budget.sh --record` inserts a table row between `SUITE-BUDGET-HISTORY:BEGIN` / `END` markers in `docs/release/SUITE-BUDGET.md`. The initial Pilot-8 row is already seeded. Future release commits carry an appended row, keeping the growth curve visible without manual tracking.

---

## Test Evidence

```
$ bash tests/test-suite-budget.sh
  Passed: 12  Failed: 0
PASS: test-suite-budget (12 assertions)
```

Run at: commit `e5693642`, 2026-07-27.

```
$ bash -n scripts/lib/suite-budget.sh && echo OK
OK
$ bash -n scripts/measure-suite-budget.sh && echo OK
OK
$ bash -n scripts/pre-release-check.sh && echo OK
OK
$ shellcheck scripts/lib/suite-budget.sh scripts/measure-suite-budget.sh
(no output — clean)
```

---

## Additional Checks

- **ABS-243 kill-scope**: `measure-suite-budget.sh` starts the competitor with `&`, captures PID via `$!`, and cleans up with `wait "$competitor_pid"`. No name-pattern kill. ✓
- **ABS-317 harness parity**: no `harness/claude/` files touched — rule not applicable. ✓
- **Policy lib shared**: `scripts/pre-release-check.sh` sources `scripts/lib/suite-budget.sh` and `tests/test-suite-budget.sh` sources the same file — gate and tests agree by construction. ✓
- **Commit present on remote**: `refs/remotes/gitlab/ABS-603-auto` contains `e5693642`. ✓

---

## Verdict

All 5 ACs met. Test suite 12/12 green. Implementation is clean, unit-tested, and non-over-engineered (staged-suite.sh intentionally not wired in — scope-appropriate).

**APPROVED → Story Acceptance**
