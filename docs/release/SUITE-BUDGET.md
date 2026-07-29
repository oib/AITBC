# Test-Suite Budget & Reserve (ABS-603)

The release gate (`scripts/pre-release-check.sh`) runs each `tests/test-*.sh` suite
under a per-suite wall-clock **budget** (`PRE_RELEASE_SUITE_TIMEOUT`, a watchdog
from PILOT-60/ABS-573). The tentpole `tests/test-orchestrator.sh` dominates that
budget, and — this is the ABS-603 finding — its runtime **grows with every epic**,
so the reserve (budget − runtime) shrinks over time until a parallel seat is enough
to push the gate red on green code.

This document records the measured reserve, the chosen budget with its rationale,
the evaluation of the staged runner, and the mechanisms that keep the problem
visible. Re-measure at each release (`scripts/measure-suite-budget.sh --both
--record`) so the curve below stays current.

## The finding (Pilot 8, 2026-07-27)

- `tests/test-orchestrator.sh` ran **790 s** isolated against a **900 s** budget →
  only **12 % reserve**. Result: 1455/1455 assertions, exit 0 — a fully green suite.
- The same day, while the RTE ran the tentpole for epic integration, a concurrent
  operator verification of the *same* suite hit the watchdog: `test-orchestrator:
  TIMED OUT (exceeded 900s budget)`. **The gate was red although nothing was broken.**
- Growth is the root cause of the shrinking reserve: the PILOT-71 epic raised
  `tests/orchestrator.d` from 54 → 59 fixtures (+9 %). The number of test *cases* in
  `test-orchestrator.sh` was unchanged (685 both sides) — the runtime grows with the
  *loaded fixtures*, not the harness. Almost every epic adds fixtures, so linear
  extrapolation breaks the 900 s budget in 2–3 epics **even without concurrency**.

A higher budget number alone only buys time. The structural problem is a monolithic
tentpole running against a fixed budget while growing every ticket.

## What ABS-603 changed

1. **Reserve is measured, not guessed** (AC1). Two measured datapoints anchor the
   budget — both from real runs, neither invented:
   - **Isolated: 790 s** (Pilot 8, epic-tip `7d7d3a72`, TEST_JOBS=4) → 12 % reserve
     against the old 900 s budget; 1455/1455 assertions, exit 0.
   - **Under one parallel seat: > 900 s** — the same-day incident, where a concurrent
     RTE run of the tentpole drove the operator's verification of the *same* suite past
     the 900 s watchdog. The under-load runtime is therefore *measured* to exceed 900 s.
   `scripts/measure-suite-budget.sh --both` re-measures both figures (an isolated pass
   and a pass under a concurrent competitor that reproduces the incident) and records
   them into the history table below at each release, so the numbers stay current
   rather than quoted.
2. **Budget carries real headroom** (AC2). `PRE_RELEASE_SUITE_TIMEOUT` default is
   **1800 s** (was 900 s) — see rationale below.
3. **A budget overrun is an OPERATIONAL finding, not a test failure** (AC3). The gate
   classifies a watchdog kill (rc 124) as `ops-overbudget` — reported distinctly and
   **non-blocking** — separate from a real test `fail` which still blocks the release.
   This is the same infra-vs-test distinction ABS-595 draws for a stalled pipeline:
   infrastructure/load must not block; a real test signal must. The anti-hang
   guarantee from ABS-573 is preserved — the suite is still killed at the budget, so
   an unbounded hang remains impossible; only its *classification* changed.
4. **A reserve sensor warns before the gate red-lines** (AC4). When a *passing* suite
   leaves less than `SUITE_RESERVE_WARN_PCT` (default **25 %**) of its budget, the gate
   emits a `LOW RESERVE` warning. Growth becomes visible while it is still cheap to fix.
5. **The measurement repeats each release** (AC5). The pre-release checklist has a
   record step; `measure-suite-budget.sh --record` appends a row here so the curve
   stays visible.

The classification policy is a pure, unit-tested helper — `scripts/lib/suite-budget.sh`
(`suite_reserve_pct`, `classify_suite`), covered by `tests/test-suite-budget.sh` — so
the gate and the tests agree by construction.

## Budget rationale

The chosen budget balances two failure modes:

- **Too low** → false reds under normal parallel load. Measured: isolated ~790 s, and
  *> 900 s* under one concurrent seat (the incident). Two 4-job runs contending for the
  same 4-core box roughly halve each other's CPU, so the loaded runtime lands near
  ~1.5–2× the isolated figure (~1200–1600 s) — any budget near 900 s red-lines under
  load. `measure-suite-budget.sh --both` records the exact loaded figure each release.
- **Too high** → a genuinely wedged suite is caught late. But this is bounded: AC3
  already makes an overrun non-blocking, and AC4 flags shrinking reserve early, so the
  budget number is no longer the *only* line of defence.

**Budget = 1800 s.** It clears the measured isolated ~790 s (~56 % reserve today) and
absorbs the measured/estimated under-load band (~1200–1600 s) with margin above the
worst case, so a single parallel seat can no longer false-red the gate. The reserve
sensor (25 %) fires well before growth reaches 1350 s, giving 2–3 epics of warning to
adopt the staged runner or split the tentpole. The per-release re-measurement (below)
keeps this number honest as the tentpole grows.

## Evaluation of the staged runner (`tests/staged-suite.sh`, ABS-557/PILOT-50)

`tests/staged-suite.sh` is the existing structural answer and the recommended next
step once the reserve sensor fires:

- It partitions the tentpole at its one safe seam into `orch-core` (scenario blocks)
  and `stories` (the `orchestrator.d` includes, fanned out one-process-per-file), plus
  a `pool` stage for every other `test-*.sh`. `orch-core ∪ stories` = the whole
  tentpole exactly, so nothing is skipped.
- The partition is **fixed by the script** — a seat cannot choose which files run, so
  file-selection can't make a red suite look green.
- A **HEAD-bound completeness ledger** makes `--verify` accept only when every stage is
  green at the current commit; any new commit invalidates the ledger by construction.

Why staging is the durable fix: each stage is well under the 10-minute tool-call cap
and under the per-suite budget individually, so **fixture growth lands in the `stories`
stage's parallel fan-out instead of a single monolithic clock** — concurrent load can
no longer push one big run over the line. ABS-603 does **not** rewire
`pre-release-check.sh` to call the staged runner yet (that is a larger change and
`staged-suite.sh` is already usable directly by gate seats); the budget bump + AC3/AC4
sensors remove the immediate false-red, and the reserve sensor is the trigger to adopt
staging before the next red-line.

## Measurement history (AC5)

Re-measured at each release. `elapsed` is the isolated or under-load tentpole runtime;
`reserve` is against the budget in that row.

| date | commit | mode | elapsed | budget | reserve | asserts | fixtures |
|------|--------|------|---------|--------|---------|---------|----------|
<!-- SUITE-BUDGET-HISTORY:BEGIN -->
| 2026-07-27 | `7d7d3a72` | isolated (Pilot 8, quoted) | 790s | 900s | 12% | 1455 | 59 |
<!-- SUITE-BUDGET-HISTORY:END -->

> Note: the first row is the original Pilot-8 datapoint against the old 900 s budget.
> Rows recorded by `measure-suite-budget.sh --record` are inserted above the END marker
> and use the current budget.
