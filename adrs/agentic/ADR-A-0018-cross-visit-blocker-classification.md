---
id: ADR-A-0018
title: Cross-visit blocker classification and loop-breaker for recurring environment denials
status: accepted
scope: agentic
date: "2026-07-11"
accepted_by: "Raphael Sahann (POPM)"
accepted_date: "2026-07-11"
---

## Context

The ABS-132 respawn/no-move and ABS-74 crash escalations are **per-visit**: each counts
consecutive failures *within one resting episode* at one status, and any transition resets the
window (`nomove_count` / `crash_count` re-arm on the next `Transition:` line). That is correct for
a ticket wrestling with its own logic. It is blind to a ticket that keeps hitting the *same
external wall* across different statuses.

Three observed failure modes share that blind spot:

- **ABS-181** cycled `Enrichment → Needs PO Decision → Enrichment` **5×** on the same persistent
  wall. Each visit was a fresh episode, so no per-visit counter ever tripped; the loop only ended
  when an operator noticed.
- **ABS-168** burned **4 dispatches** against the same CLI `.claude` write-protection denial
  (~$1–3.5 per attempt) before a human parked it. The denial was deterministic — retrying could
  never succeed — yet the runner kept re-spawning because each attempt looked new.
- The **follow-up-budget dead-end**: an exhausted `ORCH_FOLLOWUP_BUDGET` leaves a JOIN/gate check
  waiting *silently* (>1h observed) with no ticket, no notification, no operator signal.

The common defect: the runner has no **cross-visit memory** of *why* a ticket keeps failing, and no
distinction between a **deterministic** blocker (retrying is pure cost) and a **transient** one
(retrying is the fix). Environment-policy denials are deterministic; the per-visit machinery treats
them as if they might resolve, so it pays the full cost budget to relearn the same denial.

This ADR decides the **classification taxonomy, cross-visit memory, thresholds, escalation-budget
semantics, and NOTIFY dedup** that let the runner break these loops. It is a decision record, not an
implementation; ABS-199 carries the code and tests.

## Decision

### (a) Blocker-class taxonomy and mechanical derivation

Every failed dispatch is classified into exactly one class, derived **mechanically** from the crash
diagnostic already captured (`attempt_diag`, ABS-151) and the `gate-results` markers — never from
free prose:

| Class | Signal source | Retry semantics |
|-------|---------------|-----------------|
| `environment-denial` | diagnostic matches a tool-policy / permission denial (e.g. `.claude` write-protection, permission-mode `dontAsk` deny, allowlist reject) | **Deterministic** — retrying cannot succeed |
| `transient` | diagnostic matches network / rate-limit / auth / non-zero-exit-without-denial / empty-handoff crash | **Recoverable** — retry is the remedy (existing ABS-118 backoff / ABS-74 crash path) |
| `logic` | a parsed handoff that bounces on a test/gate failure (rework path, ABS-132 no-move with a real bounce reason) | **Ticket-owned** — the seat must fix its own work |

Derivation is a single classifier `blocker_class <diag> <marker>` returning one token. Precedence
when signals overlap: `environment-denial > transient > logic` (a permission denial that also
produced a non-zero exit is still a denial). An unmatched diagnostic defaults to `transient` — the
**safe** default, because it keeps the existing recover-and-retry behaviour rather than parking a
ticket that might have been recoverable.

**Every class names an EFFECT (PILOT-69 — a classification without a named effect is incomplete).**
A taxonomy that only labels but never acts is log-noise; the original ADR wired an effect for
`environment-denial` (the §c cross-visit auto-park) but left `transient` recorded-and-ignored, so a
transient infra abort still drove the iteration/rework counters that never consulted the class
(PILOT-32). The effect of each class is now explicit:

- `environment-denial` → §c cross-visit loop-breaker (auto-park to Blocked on the 2nd same-class visit).
- `transient` → **budget-neutral for the iteration and rework counters**: a backward transition
  whose reason denotes a transient/infrastructure abort consumes no iteration
  (`scripts/hooks/iteration-guard.sh`, ABS-555) and no rework unit (`rework_count()`,
  `ORCH_REWORK_INFRA_RE`, PILOT-69) — retrying is the remedy, not a defect to punish.
- `logic` → **ticket-owned**: the seat must fix its own work; it flows the existing per-visit
  ABS-132 no-move / rework path unchanged.

### (b) Cross-visit memory — a marker file under `work/.orchestrator/`

Cross-visit memory persists as a **per-ticket marker file** `work/.orchestrator/blocker-<ticket>`,
alongside the existing `backoff-<ticket>` / `halt-<ticket>` / `outage` markers (§ ABS-118). Each
line records `class seat visit-status timestamp`. The file is created on the first classified
failure and deleted on real forward progress (§d).

**Rejected: parsing Jira/tracker comments as the primary source.** The comment history *is* written
(crash/no-move markers already land there for audit), but it must not be the authority for the
loop-breaker:

- Comment reads are **network round-trips** subject to the very rate-limit/outage failures this
  mechanism guards against — the loop-breaker would depend on the thing it protects.
- The tracker is **adapter-swappable** (ADR-A-0007); comment shape is not a stable contract.
- The local marker is O(1), atomic, and lives with the other runtime state the reconciliation sweep
  already owns and cleans.

The tracker comment stays the **human-readable audit trail**; the marker file is the **machine
authority**. They are written together, exactly as the existing crash/no-move markers already pair a
`gate-results` comment with local state.

### (c) Threshold semantics — 2nd same-class visit auto-parks

When a dispatch fails with class `environment-denial`, the runner appends to
`blocker-<ticket>` and counts prior lines with the **same `(class, seat)`**:

- **1st occurrence:** record the marker; let the existing per-visit path run (ABS-118 backoff for a
  genuinely transient-looking first hit, or immediate record for a clean denial).
- **2nd occurrence of the same `(class, seat)` across ANY visits:** the loop-breaker fires —
  transition the ticket to **Blocked** (a human-owned rest state, *not* the reconcilable Needs PO
  Decision the per-visit path uses), **suppress re-spawn**, and emit exactly one operator NOTIFY (§e).

This is deliberately distinct from the **per-visit ABS-132 `ORCH_RESPAWN_LIMIT`** (consecutive
no-moves *within one episode*, escalating to Needs PO Decision). ABS-132 stays unchanged and remains
the backstop for logic loops inside a single status. The cross-visit rule adds a **second,
orthogonal axis**: same *class+seat* across *different* episodes. The threshold is 2 (not 3) because
a deterministic denial cannot improve on retry — the first retry already proved recurrence, and a
third dispatch is pure wasted budget (the ABS-168 lesson).

Classes `transient` and `logic`, and any *different* `(class, seat)` pair, do **not** trip the
cross-visit park; they continue on the per-visit ABS-132 / ABS-118 paths. Only a repeated,
identical, deterministic wall auto-parks.

### (d) Escalation-budget semantics and reset rule

Independent of blocker class, a ticket that makes **N rounds without status progress** is itself a
stuck signal. A per-ticket **escalation budget** (`ORCH_ESCALATION_BUDGET`, default 3) counts
resting episodes that end without the ticket's `chain_index` advancing. On exhaustion: one NOTIFY +
transition to Blocked, same dedup as §e.

**Terminal-status exemption (ABS-301):** the budget counter **skips** any status that carries
`terminal: true` in `profiles/neutral/adapters/statuses.yaml`. A terminal status has no legal
forward edge. The self-improvement retro at `Epic Done` posts proposals without transitioning;
that is the correct completion signal. The sweep reads `terminal: true` from the YAML file, not a
hardcoded name list. Evidence: ABS-217 (`Epic Done` falsely parked), ABS-245 (mid-Epic-Integration park).

**Terminal-status exemption extended to the ABS-132 respawn limiter (ABS-339):** the same
`terminal: true` guard now also short-circuits `record_nomove` (the per-visit HANDOFF-NOMOVE
counter, ABS-132) — not just the cross-visit budget above. A NOMOVE on a terminal status posts no
`HANDOFF-NOMOVE` marker (so `nomove_count` never rises), records an auditable `HANDOFF-NOMOVE-EXEMPT`
run.log line, and returns early — skipping the `RESPAWN-LIMIT → Needs PO Decision` escalation. Before
this fix, a terminal ticket accumulated NOMOVE markers **across roles** (`nomove_count` keys on
status, not seat: a self-improvement retro NOMOVE + a bsa follow-up-watcher NOMOVE summed to the
limit at one `Epic Done`) and was escalated to `Needs PO Decision` — a status with **no legal edge
back** to the terminal state, so the sweep re-derived endlessly (~$0.6–1.0/cycle) until a manual
operator restore. Evidence: ABS-111/126/279 (2026-07-16), ABS-181/190 (2026-07-13).

**Operator recovery for already-escalated terminal tickets (ABS-339 AC2):** a ticket parked at
`Needs PO Decision` by the pre-fix false escalation is recovered by a single manual tracker
transition back to its terminal state, *after* verifying the terminal evidence:
`$TRACKER_CMD get <id>` shows the completion signal (epic: all children Done + retro proposals
posted; story: PR merged), then
`$TRACKER_CMD transition <id> "Epic Done" --actor operator --reason "false terminal-state
escalation (ABS-339); restoring terminal rest after verifying completion evidence"`. No autonomous
back-edge `Needs PO Decision → Epic Done` is added: the po-agent seat correctly refuses to reopen a
finished epic, and reopening a terminal ticket is a product decision reserved to a human
(ADR-A-0004). Once restored, this fix prevents re-escalation.

**Reset rule:** the counter (and the `blocker-<ticket>` marker file) resets to zero on **real
forward progress only** — a transition whose target has a strictly greater `chain_index` than the
ticket's high-water mark for this run. A *bounce* (backward transition, e.g. review → Ready for
Development) does **not** reset it; otherwise a ticket could bounce-and-retry forever and never
exhaust the budget. This mirrors `nomove_count`'s "any transition re-arms" only for *forward* moves,
closing the cross-visit bounce loop that ABS-181 exhibited.

**Ratchet fix (ABS-301):** `join_check_epic` (`Stories In Flight → Epic Integration`,
chain_index 26→27) and `epic_join_rest_complete` (`Backlog → Stories In Flight`) now call
`escalation_note_progress` so the high-water mark tracks the epic's progress. Before this fix,
an epic's escalation state could read `3\t0` (count 3, high-water 0) even after reaching
`Epic Integration`, parking the epic on the next stall round. Evidence: ABS-245 (state file
`3\t0` at `Epic Integration`).

**Refined stall definition — work-credit signal (ABS-311):** the budget must count a round that
advanced **neither the status NOR any verified work**; absence of a status transition *alone* is not
a stall. A no-move round is *not* counted when it produced verified work — a seat that legitimately
needs several spawns to finish long work (RTE shepherding PRs / running a smoke bisect at
`Epic Integration`) is otherwise mechanically indistinguishable from a stuck one. The signal is
**evidence-bound, not self-asserted** (`escalation_work_credit`): *source A* is a handoff carrying
`commits:` hashes the runner **verified** for existence + ref-reachability (ADR-A-0024 / ABS-255) —
strong and unbounded, it cannot be forged; *source B* is an explicit `progress:` handoff marker with
no commits (the artefact-free round, e.g. a bisect) — weak and self-asserted, so credited at most
`ORCH_ESCALATION_WORK_BUDGET` times per ticket per run, after which the stall counter resumes and a
seat that only *asserts* progress is still parked. Hashes that **fail** verification are no evidence
and count as a stall (real-stall detection preserved). Credit **pauses** the counter — it withholds
the increment, it never resets to zero; only forward progress resets (the ratchet above stays
intact). Off by default (`ORCH_ESCALATION_WORK_CREDIT=0` = today's behaviour byte-for-byte). Rejected
alternatives: a blanket `Epic Integration` status exemption (re-opens the genuine-stall hole), an
unbounded seat heartbeat (self-asserted and forgeable → immortal seat), and wall-clock credit (proves
elapsed time, not progress). Evidence: ABS-245 (RTE falsely parked mid-`Epic Integration` while
working).

### (e) NOTIFY-once dedup

Auto-park (§c) and budget-exhaustion (§d) each emit **exactly one** operator NOTIFY. Dedup key:
`(ticket, class, seat)` for the blocker park, `(ticket, "escalation-budget")` for the budget park.
Before sending, the runner checks `blocker-<ticket>` for a `NOTIFIED <key>` line; if present it
parks **silently** (marker already recorded, human already told). This guarantees the operator gets
one actionable signal per distinct dead-end — never the 5× spam of ABS-181, never the >1h silence of
the follow-up-budget dead-end.

The follow-up-budget dead-end (§Context) is folded into §d/§e: an exhausted `ORCH_FOLLOWUP_BUDGET`
that blocks a JOIN/gate check now emits a **naming** one-shot NOTIFY (which epic, which gate, which
budget) and parks the blocked ticket to Blocked, instead of waiting silently.

## Consequences

- A recurring deterministic wall (ABS-168-class permission denial) costs **at most one retry**, then
  parks with a single operator signal — bounded blast radius, no relearning the same denial.
- A cross-visit cycle (ABS-181-class Enrichment↔NPD loop) is broken at the 2nd identical visit rather
  than running until an operator notices.
- No silent dead-ends: every exhausted budget that stalls a gate names itself once.
- Transient and logic failures are **untouched** — the existing ABS-118 backoff and ABS-132/ABS-74
  per-visit escalations remain the path, so no recoverable ticket is parked prematurely (the
  `transient` default protects the ambiguous case).
- New runtime state: one `blocker-<ticket>` marker file per stuck ticket under `work/.orchestrator/`,
  cleaned on forward progress — same lifecycle discipline as `backoff-<ticket>`.
- Blocked (human-owned) is the park target, distinct from Needs PO Decision (reconcilable); this
  avoids the v3 pitfall where a reconcilable park re-spawns the escalation seat (ABS-118 lesson).
- **Cap/rework escalation of DEMONSTRABLY-FINISHED work parks to Blocked, not Needs PO Decision
  (PILOT-69 AC1).** A ticket that reached the acceptance/merge tier (`reached_merge_tier`) passed its
  implementation, review, security and test gates — its work is finished. Parking such a ticket in
  Needs PO Decision was the mechanic that made a finished story unmergeable: the iteration-cap and
  rework escalations routed there, and (before ABS-555) Needs PO Decision had no edge to Merging.
  `escalate_rework` / `block_for_iteration_cap` now park finished work in Blocked, whose exhaustive
  resume-to-origin list includes Merging, so a human/TDM routes it straight to the merge seat. Not
  demonstrably-finished work keeps the Needs PO Decision park (a fresh product decision is owed).
  This complements the PILOT-49/ABS-555 `Needs PO Decision → Merging` PO-mediated escape edge; it
  does not remove it.

## Alternatives considered

1. **Lower the per-visit ABS-132 `ORCH_RESPAWN_LIMIT` to 1.** Rejected: it conflates two different
   loops. Per-visit no-moves are often legitimate logic churn within a status; cross-visit
   recurrence is a different signal. Tightening the per-visit knob would falsely park healthy tickets
   while still missing the cross-status cycle (ABS-181 never tripped it).
2. **Jira-comment history as the cross-visit source of truth.** Rejected — see §b: network-dependent,
   adapter-unstable, and circularly dependent on the outage class it must survive.
3. **A global blocklist of known-bad seats/classes.** Rejected: over-engineered and stateful across
   tickets; a denial that is deterministic *for one ticket's deliverable* may be irrelevant to
   another. Per-ticket memory is the minimal correct scope (Ponytail / ADR-A-0010).
4. **Never auto-park; always escalate to a human seat.** Rejected: that is today's behaviour and is
   exactly what burned the ABS-168 budget — the human seat itself costs a dispatch and cannot clear a
   deterministic environment denial.

## Related Decisions

- [ADR-A-0007](ADR-A-0007-adapter-model.md) — adapter neutrality (why the tracker comment is not the
  machine authority).
- [ADR-A-0010](ADR-A-0010-minimal-change-default.md) — minimal-change / per-ticket-scope discipline.
- [ADR-A-0016](ADR-A-0016-claude-target-apply-path.md) — the `.claude` write-protection that produced
  the ABS-168 `environment-denial` class.

## References

- ABS-199 (this ticket; implementation + `tests/test-orchestrator.sh`).
- ABS-118 crash-backoff / outage-pause spec (`specs/ABS-118-crash-backoff-outage-spec.md`) — the
  marker-file and NOTIFY patterns this ADR extends.
- ABS-132 (transition-on-handoff + endless-respawn escalation), ABS-74 (crash escalation), ABS-151
  (crash diagnostics) — the per-visit machinery this ADR complements.
- Evidence: ABS-181 (5× cross-visit cycle), ABS-168 (4 dispatches on a deterministic denial).
