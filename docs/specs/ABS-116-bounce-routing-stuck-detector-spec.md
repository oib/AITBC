# ABS-116 Design Spec — Backward-into-In-Progress Routing + Generic Stuck Detector

**Ticket**: ABS-116 (epic ABS-114) · **Status**: accepted (architect review 2026-07-07: approve-with-changes, findings F1–F9 incorporated below) · **Date**: 2026-07-07

## 0. Defect being fixed

In the ABS-102 resume run, the system-architect reviewer bounced ABS-108 `In Review → In Progress`.
That edge is legal in statuses.yaml, but the runner treats `In Progress` as NOOP everywhere:
`map_action` maps it to NOOP (the implementer sets it on start) and `is_reconcilable_status`
excludes it (agents legitimately rest there while working). Result: dispatch deadlock — the ticket
lay untouched until the operator two-hop-rerouted it via Blocked.

Operator refinement (binding): option (b) — make the RUNNER robust instead of relying on reviewer
prompt discipline (option (a) failed in run 1); statuses.yaml stays untouched (option (c) is a
state-machine breaking change). Additionally: a GENERIC stuck detector so unknown future deadlock
patterns become visible instead of resting silently. The detector NOTIFIES only — it never routes
(ADR-A-0004: escalate to the human rather than act autonomously).

## 1. Part 1 — backward transition into In Progress spawns the implementer

Direction comes from the EVENT, not the status: the adapter's `events` output carries
`from:`/`to:` per status change, and `parse_event` already extracts `ev_from`. The dispatch seam
gains the `from` parameter (`dispatch <ticket> <to> [<from>]`):

- `process_events` passes `ev_from` through.
- `reconcile()` passes nothing (a resting status has no direction) — `In Progress` at rest stays
  non-reconcilable exactly as today; a dropped bounce event is the stuck detector's case (part 2).

In `dispatch`, before the `map_action` mapping is applied: when `to == "In Progress"` AND `from`
is a chain status with `chain_index(from) > chain_index("In Progress")` (a backward move from any
later stage — In Review, In Test, Design Test, …), the NOOP mapping is overridden to `SPAWN -`
(implementer, role from ticket §2.2). Everything downstream is the EXISTING path: role resolution
via `resolve_implementer_role`, re-read guard, depends gate, §5 safety gates, and the ABS-111
resume seam (a stored implementer session is resumed, else fresh spawn — exactly what a rework
bounce to Ready for Development gets). A `runlog BOUNCE-REROUTE` line records the override with
`from=<gate>`.

Single-flight/regression guarantees:
- Forward entry (`Ready for Development → In Progress`, chain 2 → 3) stays NOOP — direction check
  fails, no spawn on normal work start.
- Creation events (`from: null`) and non-chain `from` (Blocked, Needs PO Decision, unknown) stay
  NOOP: a `Blocked → In Progress` unblock-resume returns the ticket to the status it left with the
  agent's session intact — not a bounce. (`chain_index` returns 0 for all of these.)
- The §5.2 single-flight lock and the per-cycle `DISPATCHED_CYCLE` guard apply unchanged — the
  bounce spawn cannot double with a reconcile-derived spawn. A cap-deferred bounce keeps its
  `from` across the pending-set retry (the pending entries carry it).
- The §5.5 iteration guard does not run here (`is_bounce_status` covers In Review/In Test — the
  guard governs GATE spawns). No unguarded ping-pong window opens (architect F5): the loop is
  BOUNDED because every iteration necessarily passes the guarded In Review gate, where ABS-115's
  authoritative CLI-mode derivation counts the accumulated marker+backward pairs and refuses the
  gate spawn at cap (plus the cumulative ticket budget, default 9). Additionally the §3.2 rework
  counter applies to the In Progress respawn itself (architect F6): `chain_index("In Progress")=3`
  is a chain status, so a bounce respawn at `ORCH_REWORK_LIMIT` escalates to Needs PO Decision
  instead of spawning — exactly like the Ready-for-Development bounce path.
- `chain_index` keeps story (1–12) and epic (21–29) ranges disjoint; an epic-range `from` cannot
  reach In Progress anyway (no such edge in statuses.yaml) — noted defensively (architect F9).
- `Needs PO Decision → In Progress` needs no handling: statuses.yaml has no such edge (NPD's
  `next:` lists only sanctioned reset targets), and `chain_index("Needs PO Decision")=0` would
  keep NOOP regardless. `from: null` creation events likewise (mock creates always enter Backlog).

Event collapse under polling (architect F4): the adapter's `events` are snapshot diffs, so a
round-trip inside one poll interval emits no event. Both outcomes are covered: net-resting in a
RECONCILABLE status → the reconcile sweep re-derives the seat; net-resting in In Progress (or any
unowned status) → the stuck detector (part 2) surfaces it. Nothing silts up silently; the window
requires an LLM round-trip faster than the poll interval and is practically negligible.

Rejected alternative: extending `map_action` with a direction-aware row — `map_action` is keyed on
destination only and used by pending-retry paths that have no `from`; a targeted pre-mapping
override in `dispatch` keeps the table's contract intact (ADR-A-0010).

## 2. Part 2 — generic stuck detector (NOTIFY-only)

Sweep definition and cadence (architect F1): the detector runs inside `reconcile()`, next to
`check_stall_rules` and BEFORE the `is_reconcilable_status || continue` filter — only there does
the runner see non-reconcilable resting tickets at all. "Sweep" therefore means RECONCILE pass,
and the effective cadence is `ORCH_RECONCILE_EVERY_N_CYCLES` (default 10) ×
`ORCH_POLL_INTERVAL` (default 10s) ≈ 100s; the default `ORCH_STUCK_SWEEPS=3` ≈ 5 minutes of
unowned rest before the NOTIFY — long enough that no normal seat turnaround trips it.

`#PATH_DECISION` — NOTIFY-only vs auto-recover (architect F3): for the one precisely
identifiable case (lock-less rest in In Progress) an auto-respawn would even be mostly idempotent
(re-read guard). The operator chose NOTIFY-only (binding): the generic detector by definition
does NOT know the remedy for the pattern it finds, so it escalates to the human instead of acting
(ADR-A-0004). This is also the validated boundary to ABS-62: the stall rules RAISE (transition to
Needs PO Decision) because their remedy is known (Backlog stall → PO triage); the stuck detector
only notifies because its remedy is unknown. Auto-recover remains a candidate follow-up once
run.log data shows the NOTIFY pattern is dominated by crashed implementers. The primary real
trigger is exactly that (architect F2): an implementer that crashes AFTER setting In Progress
rests there forever — In Progress is not reconcilable, so ABS-74's crash escalation never
re-derives; the detector is the only net under that case.

A ticket is STUCK when the sweep sees it resting, for `ORCH_STUCK_SWEEPS` consecutive sweeps
(default 3, `0` disables), in a status that nobody owns:

- NOT reconcilable (`is_reconcilable_status` false — reconcile would re-derive a seat otherwise),
- NOT in the legit-rest allowlist `is_legit_rest_status`: Backlog (ABS-62's territory), Blocked,
  Ready for Merge, Ready for Human Acceptance*, Done, Epic Done, Stories In Flight (JOIN rule),
  Ready for Epic Acceptance — the states §5.1 documents as legitimate resting places
  (*RfHA is reconcilable, listed defensively),
- with NO in-flight spawn (single-flight lock dir absent — an implementer legitimately rests in
  In Progress while its session runs), and
- with NO pending backoff/pause marker (`$ORCH_STATE_DIR/backoff-*` glob — forward-compat seam for
  ABS-118, whose backoff states must read as legitimate waits; documented contract, the glob is
  simply empty until ABS-118 lands).

Today the effective set is `{In Progress}` plus any unknown status — deliberately generic so a
future edge (new status, new NOOP row) surfaces instead of resting silently.

Mechanics (state in `$ORCH_STATE_DIR/stuck-state`, TAB-separated `ticket status count notified`
rows — existing state dir, no new storage format):
- Sweep sees ticket in candidate status: same status as the stored row → `count+1`; different or
  absent → fresh row (`count=1, notified=0`). Non-candidate status → row removed (episode over).
- `count >= ORCH_STUCK_SWEEPS && notified == 0` → exactly one NOTIFY comment on the ticket
  (existing `notify()`: `kind: notification`, actor orchestrator, naming status + sweep count +
  "no seat owns this status; not routing — human/PO attention needed") + `runlog STUCK-DETECT`
  event + row marked `notified=1`. Further sweeps in the same episode are silent (SKIP-UNLABELLED
  throttle pattern, ABS-111 D12) — but the run.log records a throttled `STUCK-DETECT` line each
  time for the timing analysis.
- Ticket leaves the status and falls back later → fresh episode, may NOTIFY again (that is a NEW
  stuck situation, not spam).

No auto-routing, no transition — the detector is eyes, not hands (ADR-A-0004). The dry-run mode
emits `INTENT NOTIFY` lines only, like every other NOTIFY.

Accepted edge cases (architect F7/F8):
- DEPENDS-WAIT tickets rest in Ready for Development/Design — both reconcilable, hence never
  candidates (no false positive).
- A cap-deferred In-Progress bounce sits in the pending set WITHOUT a lock; under a permanently
  saturated concurrency cap spanning ≥3 reconcile sweeps it could be flagged. Accepted as a rare,
  harmless false positive (drain_pending retries every cycle; and a NOTIFY on a cap-starved
  ticket is arguably signal, not noise).
- Unlike the in-memory D12 throttle, `stuck-state` PERSISTS across runner restarts — deliberate:
  stuck stays stuck; a restart must not re-fire the episode NOTIFY. Orphan rows for
  deleted-outside-the-lifecycle tickets are never cleaned (normal lifecycle removes rows when the
  ticket becomes owned/legit-rest); declared negligible.

## 3. Test plan (tests/test-orchestrator.sh)

Part 1:
- reviewer bounce `In Review → In Progress` event → implementer spawn intent (role from ticket),
  `BOUNCE-REROUTE` in run.log
- forward `Ready for Development → In Progress` event → NOOP (no spawn; single-flight regression)
- `Blocked → In Progress` return → NOOP (unblock is not a bounce)
- backward bounce respects the depends gate and re-read guard (stale event → SKIP-STALE)
- e2e dry-run: the ABS-108 scenario end-to-end — bounce lands, implementer re-spawn intent, no
  operator rerouting

Part 2:
- fixture ticket resting in In Progress without a lock: sweeps 1..N-1 silent, sweep N produces
  exactly ONE NOTIFY + STUCK-DETECT; sweep N+1 silent (episode throttle)
- lock dir present → never counted (working implementer is not stuck)
- backoff marker file present → never counted (ABS-118 forward-compat)
- legit-rest statuses (Blocked, Ready for Merge, Stories In Flight fixtures) → never counted
- ticket leaves and re-enters the status → counter reset, fresh episode can NOTIFY again
- `ORCH_STUCK_SWEEPS=0` disables the detector entirely
