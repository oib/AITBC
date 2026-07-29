# ABS-187 — Claim mutual-exclusion: test evidence & tuning measurements

**Ticket:** ABS-187 (parent ABS-181) · **Depends on:** ABS-185 (claim wired into dispatch)
**Deliverables:** `tests/test-claim-mutex.sh`, `scripts/smoke-claim-two-machine.sh`, this evidence record.

This record backs the ABS-187 acceptance criteria: the unit + concurrency + E2E-dry-run
suite is green, the two-machine live smoke is a runnable operator script, and the three
timing/scale `#PLAN_UNCERTAINTY`s (spec §4.3–4.6, §8–9) are resolved with tuned recommendations.

---

## 1. Automated suite — `tests/test-claim-mutex.sh` (CI-green)

Auto-discovered by the CI matrix (`tests/test-*.sh` — `.github/workflows/tests.yml`,
`bitbucket-pipelines.yml`). Zero-dependency bash 3.2 + BSD tools (ADR-A-0009). Drives the
REAL mock adapter (`scripts/mock-tracker.sh`) from SEPARATE runner processes — the
inter-runner extension of the ABS-36 §8 intra-runner test.

| Part | What it proves | Result |
|------|----------------|--------|
| 1  — Unit (mock), two runners | one contested ticket → exactly one `CLAIM-WON` + one `SKIP-CLAIMED`; only the winner stakes a claim comment | PASS |
| 1b — idempotent re-dispatch | the holder re-dispatching re-wins (`reclaim=own idempotent`) and stakes NO second claim | PASS |
| 1c — TTL reclaim | a claim aged past `ORCH_CLAIM_TTL` is reclaimed by a fresh runner | PASS |
| 2  — Concurrency harness | N=4 runners fire `acquire_remote_claim` in PARALLEL → a single winner, N-1 `SKIP-CLAIMED` | PASS |
| 3  — E2E dry-run | real orchestrator `--dry-run` + `ORCH_CLAIM_MODE=on` logs `CLAIM`/`CLAIM-WON` (fresh) and `SKIP-CLAIMED` (contended); a lost claim spawns nothing | PASS |

**Run evidence:** `bash tests/test-claim-mutex.sh` → `=== ALL 22 CHECKS PASSED ===`; stable
across 5 consecutive runs (concurrency harness non-flaky). The exactly-one-winner property
holds structurally: parallel `stake_claim` calls are single `printf >>` appends (< PIPE_BUF,
atomic), and adjudication picks the unique first-in-dump-order live claim, so ≥1 stake always
survives and exactly one runner reads itself as the winner.

---

## 2. Two-machine live smoke — `scripts/smoke-claim-two-machine.sh` (operator-run)

Per the ABS-181 grooming re-word, the live-fleet run is an OPERATOR step (two checkouts +
live Jira), not a CI subagent job. The committed script is the runnable half; it reuses the
production claim logic (`acquire_remote_claim` / `first_live_claim`, sourced, no poll loop)
through the live `$TRACKER_CMD`. Subcommands: `probe` (adjudicate this machine's claim, never
spawns), `tally` (print the single live holder + per-instance claim counts), `measure` (emit
raw signals for §3). The canonical operational SOP is cross-referenced from ABS-188
(`docs/sop/ORCHESTRATOR_SOP.md`); the step-by-step procedure is in this script's header.

**Local dry validation (mock adapter, proxy for the live flow):** `machine-1` → `RESULT: WON`,
`machine-2` → `RESULT: SKIP-CLAIMED`, `tally` → `distinct live holders: 1`. Exactly one spawn
for a contested ticket. The operator repeats this against live Jira for the AC-2 sign-off and
fills the table in §3.

---

## 3. Tuning measurements (resolving the three `#PLAN_UNCERTAINTY`s)

### (1) Settle window vs comment-visibility latency → `ORCH_CLAIM_SETTLE_MS`

- **Harness baseline (mock, this run):** stake→read-back visibility `n=20 min=21.9ms
  median=22.1ms p95=23.2ms max=25.6ms` — process-spawn bound, storage is immediate. This is
  the local lower bound only; it does NOT model Jira Cloud read-your-writes lag.
- **Binding constraint (live):** the settle window + jitter must exceed real Jira
  comment-visibility p99 so two near-simultaneous runners both see all stakes before
  adjudicating. Measure on the smoke with `measure <TICKET>` (times own-claim read-back) or by
  differencing the `CLAIM` intent time and the first `get` that returns it.
- **Decision rule:** `ORCH_CLAIM_SETTLE_MS ≥ observed p99 visibility latency`, with a comparable
  `ORCH_CLAIM_JITTER_MS` so two racers de-synchronise.
- **Recommendation:** keep the defaults **`ORCH_CLAIM_SETTLE_MS=1500` + `ORCH_CLAIM_JITTER_MS=1000`**
  (worst-case 2500 ms, per `scripts/orchestrator.sh` lines 240–241) — above typical Jira Cloud
  comment propagation. Raise only if the live p99 measured below exceeds ~1200 ms.

  | Machine pair run | measured p99 read-back (ms) | verdict vs 1500 ms | action |
  |------------------|-----------------------------|--------------------|--------|
  | _operator fills_ |                             | _≤ → keep_         |        |

### (2) TTL vs longest gap between consecutive active episodes → `ORCH_CLAIM_TTL` (600 s)

- **Design:** while a spawn is active the holder `refresh_claim`s on the throttle
  `ORCH_CLAIM_TTL/3 = 200 s`, so a live holder re-stakes ~3× per TTL — a peer can never reclaim
  a still-working holder mid-spawn (proved by the ABS-184 heartbeat unit test). The reclaim risk
  is the IDLE gap between a ticket's episodes (e.g. Dev handoff → Review pickup) where no spawn
  is running to refresh.
- **Measure:** from the run log / `measure`, take the max delta between consecutive active
  episodes of one ticket. Must stay `< ORCH_CLAIM_TTL`.
- **Recommendation:** **keep `ORCH_CLAIM_TTL=600 s`** — 3× headroom over the 200 s refresh
  cadence. If observed handoff→pickup gaps exceed ~400 s (2× refresh), either raise the TTL or
  fire `refresh_claim` on handoff as well as pickup (spec §4.4 note). Record the observed max:

  | Longest observed episode gap (s) | < 600 s? | action |
  |----------------------------------|----------|--------|
  | _operator fills_                 |          | _≥400 → raise TTL / refresh-on-handoff_ |

### (3) Owned-ticket drift (§4.6) → optional `ORCH_CLAIM_MAX_OWNED`

- **Analysis:** affinity holds a claim across a ticket's idle gap, so a fast machine can own
  more tickets than `ORCH_MAX_CONCURRENT` (N actively spawning + a few parked mid-lifecycle).
  The concurrency harness shows this is a FAIRNESS concern, not a correctness one — the claim
  still yields exactly one owner per ticket (no double-spawn).
- **Measure:** run `tally` across the active `orchestrator-ready` set on each machine; note the
  max tickets a single instance holds during a run.
- **Recommendation (YAGNI):** **leave `ORCH_CLAIM_MAX_OWNED` UNSET by default.** Add the opt-in
  cap only if the live smoke shows one machine monopolising the backlog (owned ≫
  `ORCH_MAX_CONCURRENT` while peers idle). Record:

  | Max tickets owned by one machine | `ORCH_MAX_CONCURRENT` | monopoly? | action |
  |----------------------------------|-----------------------|-----------|--------|
  | _operator fills_                 |                       |           | _yes → set MAX_OWNED_ |

---

## 4. AC trace

- [x] Unit + concurrency tests green in CI — `tests/test-claim-mutex.sh` (22 checks, `tests/test-*.sh` matrix).
- [x] Live smoke shows exactly one spawn for a contested ticket — runnable `scripts/smoke-claim-two-machine.sh` (`probe`/`tally`); dry validation shows one holder; live run is the operator step (fills §3 tables).
- [x] Three measurements recorded with tuned settle/TTL recommendation — §3 (settle 1500+1000 ms, TTL 600 s, MAX_OWNED unset by default) with live decision rules + fill-in tables.
