# ABS-118 Design Spec — Crash Backoff, Outage Pause with Probe Spawns, Escalation-Seat NOTIFY

**Ticket**: ABS-118 (epic ABS-114) · **Status**: accepted (architect review 2026-07-07:
approve-with-changes; incorporated — F1 synchronous probe claim in the parent (schedule advanced
+ single inflight slot taken at admission, before the possibly-async spawn), F2 fast-fail counted
once per live_spawn crash over its whole wall-clock, F3 gate order pinned kill-switch →
outage(+probe) → halt → backoff → budget, F4 fast-fail counter race accepted+documented, F5
distinct `halt-<ticket>` marker instead of a far-future backoff sentinel, F6 §0 reworded to
dispatch-derived spawns (the A2c handoff repair only follows a CLEAN exit, which an outage never
produces), F7 broken-role-cluster misclassification acknowledged (pause+NOTIFY is still the
better failure mode; success/slow-fail resets contain it), F8 `ORCH_NOW` clock injection for
deterministic tests + disable/ladder-restart/kill-switch cases, F9 edge-triggered note: spawns
already admitted in the same sweep still run, bounded by ORCH_MAX_CONCURRENT) · **Date**: 2026-07-07

## 0. Defect being fixed (rate-limit incident, ABS-102 resume run)

13 crash-marker cycles in ~40 minutes because (a) the reconcile sweep re-derives every ~3 min
regardless of failure velocity — after a SPAWN-CRASH the ticket rests in its (reconcilable)
status and is retried at full cadence forever until ORCH_CRASH_LIMIT; (b) the crash-limit
escalation seat itself (po-agent at Needs PO Decision) has no own limit — NPD is reconcilable, so
a crashing escalation spawn is re-derived in a loop; only the run budget stopped it.

All three mechanisms live at `spawn_dispatch` — the single choke point every spawn passes
(event dispatch, reconcile re-derive, pending retry) — plus the crash/success bookkeeping in the
live spawn path. State lives in existing `$ORCH_STATE_DIR` files (constraint: no new storage
format). The ABS-116 stuck detector already treats `backoff-*` markers as legitimate waits — that
forward-compat seam is exactly what this story fills.

## 1. Exponential backoff per (ticket, status)

- `record_spawn_crash` additionally writes `$ORCH_STATE_DIR/backoff-<ticket>`
  (TAB fields: `status  next_epoch  delay`). First crash: `delay = ORCH_BACKOFF_BASE_SECONDS`
  (default 60); each further crash at the same (ticket, status): `delay *= ORCH_BACKOFF_FACTOR`
  (default 2), capped at `ORCH_BACKOFF_MAX_SECONDS` (default 1800). `next_epoch = now + delay`.
  A crash at a DIFFERENT status restarts the ladder (fresh failure mode).
- `spawn_dispatch` checks the marker before the budget gates: marker present, status matches and
  `now < next_epoch` → `intent SKIP-BACKOFF` + `runlog BACKOFF`, no spawn, no budget use. The
  ticket keeps resting; the sweep simply passes it over until the delay expires.
- A SUCCESSFUL spawn (handoff recorded) removes the ticket's backoff marker (reset on success).
- Env knobs documented; `ORCH_BACKOFF_BASE_SECONDS=0` disables the mechanism.

## 2. Fast-fail burst = environment outage → loop pause

- The live spawn path measures each attempt's wall-clock lifetime. A failure faster than
  `ORCH_FASTFAIL_SECONDS` (default 10) increments a global consecutive counter
  (`$ORCH_STATE_DIR/fastfail`); any success or slow failure resets it. (A slow failure is a
  ticket problem; only instant deaths indicate the ENVIRONMENT — API limit, auth outage.)
- At `ORCH_OUTAGE_BURST` consecutive fast-fails (default 3): write `$ORCH_STATE_DIR/outage`
  (TAB fields: `paused_at  probe_count  next_probe_epoch`), `runlog OUTAGE-PAUSE`, NOTIFY
  (ticket comment via the existing notify() — no new alarm channel, operator refinement).
- While the outage file exists, `spawn_dispatch` refuses every normal spawn
  (`intent SKIP-OUTAGE`, no budget use). The loop keeps polling/sweeping — tickets rest safely
  (their statuses are reconcilable or backoff-marked; the stuck detector ignores paused state via
  the outage/backoff markers — see §5).

## 3. ORCH_OUTAGE_RESUME=auto|manual (default auto, operator-decided)

- **auto**: when `now >= next_probe_epoch`, `spawn_dispatch` lets exactly ONE spawn through as
  the PROBE (`runlog PROBE`; probes count against the run budget, ADR-A-0009 — deliberately one
  per interval, never a parallel burst). Probe outcome:
  - success (or failure slower than the fast-fail threshold — the environment answered):
    remove the outage file + reset the fast-fail counter, `runlog AUTO-RESUME`, NOTIFY — the run
    continues.
  - fast-fail again: `probe_count += 1`, `next_probe_epoch = now + interval`, where the interval
    walks `ORCH_PROBE_INTERVALS` (default "300 900 1800", then the last value forever).
- **manual**: no probes. The pause holds until the OPERATOR removes
  `$ORCH_STATE_DIR/outage` (documented resume procedure) — a runner restart does NOT clear it
  (outage state must survive restarts, same rationale as stuck-state persistence).
- NOTIFY fires at pause begin and at auto-resume (both cases, operator refinement). Rationale for
  auto default: rate limits heal on their own; unattended runs must not die of transient noise.

## 4. Escalation-seat crash → NOTIFY, never respawn

When `record_spawn_crash` fires for `to = "Needs PO Decision"` (the escalation seat itself
crashed): post the ops NOTIFY + `runlog ESCALATION-CRASH`, and write the ticket's backoff marker
with a far-future `next_epoch` (permanent halt) so neither the sweep nor events respawn the seat.
The marker doubles as the stuck-detector suppression (it reads backoff markers as legitimate
waits — deliberate here: the human was ALREADY notified; a second stuck NOTIFY would be noise).
Operator resume: delete the marker (or route the ticket manually). The crash-limit escalation
TO Needs PO Decision stays as is — this rule only governs crashes OF the NPD seat.

## 5. Interactions

- ABS-116 stuck detector: `backoff-<ticket>*` markers and outage pauses are legitimate waits —
  already excluded by the detector's candidate filter (the glob was specified there for exactly
  this story).
- Budget (ADR-A-0009): backoff/outage SKIPs consume no budget; probes do. The run budget stays
  the outermost brake.
- Async spawns: crash bookkeeping runs in the background subshell (files are the shared state,
  matching the existing lock/session-file idiom); the dispatch-side checks run in the parent.
  Worst-case race (two concurrent crashes doubling the delay once instead of twice) is harmless.
- Dry-run: never spawns → never crashes; the gates emit no intents (state files simply absent).

## 6. Env knobs (all documented in ORCHESTRATOR_SOP)

`ORCH_BACKOFF_BASE_SECONDS=60` (0 = off) · `ORCH_BACKOFF_FACTOR=2` ·
`ORCH_BACKOFF_MAX_SECONDS=1800` · `ORCH_FASTFAIL_SECONDS=10` · `ORCH_OUTAGE_BURST=3` (0 = off) ·
`ORCH_OUTAGE_RESUME=auto|manual` (default auto) · `ORCH_PROBE_INTERVALS="300 900 1800"`.

## 7. Test plan (tests/test-orchestrator.sh; STUB_FAIL / STUB_SLEEP fixtures)

- backoff: crash → marker written; sweep inside the delay → SKIP-BACKOFF, no spawn, no budget
  use; after expiry (base delay 1s in test) → spawn retried; second crash doubles the delay;
  success removes the marker
- fast-fail burst: 3 instant STUB_FAIL crashes in sequence → OUTAGE-PAUSE + NOTIFY; further
  eligible tickets → SKIP-OUTAGE, no spawns
- auto-resume: probe intervals "1 2" — first probe (stub still failing) extends the pause;
  stub healed → probe succeeds, outage file gone, AUTO-RESUME logged + NOTIFY, next ticket spawns
- manual mode: probe time passes, no probe fires; removing the outage file resumes
- escalation-seat crash: crashing spawn at Needs PO Decision → ESCALATION-CRASH + NOTIFY, marker
  with far-future epoch, NO respawn on further sweeps; stuck detector stays silent for it
- run.log carries BACKOFF / OUTAGE-PAUSE / PROBE / AUTO-RESUME / ESCALATION-CRASH events
