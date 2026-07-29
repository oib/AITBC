---
id: ADR-A-0020
title: Design-first story routing — in-place architect-first role switch at Ready for Development
status: accepted
scope: agentic
date: "2026-07-12"
accepted_by: "Raphael Sahann (Operator)"
accepted_date: "2026-07-12"
---

## Context

Some stories carry a Definition-of-Done precondition that a System-Architect design decision
(an ADR) must exist **before** the build. Today the pipeline has no station that spawns the
architect for that authoring: the dev seat correctly stops-the-line (ABS-199, ABS-204 on
2026-07-10), but the only recovery was an **operator manually spawning Opus architect
subagents** and re-releasing the ticket by hand. ABS-213 exists to formalize that missing
regular path.

The originating Operator-Retro §4 left the sequencing mechanism open ("ADR-Task als
expliziter Pipeline-Schritt **oder** BSA-Vorlauf"). The be-developer seat raised an ADR
Authoring Request (stop-the-line, ABS-213, 2026-07-11) because implementing AC1 forces an
orchestrator **routing-topology** choice in the most contended region of
`scripts/orchestrator.sh` — a decision the execution-only dev role must not improvise.

The human Operator fixed the top-level direction on 2026-07-12:

> **Sequencing mechanism = Option B — in-place role switch** at `Ready for Development` in
> `resolve_implementer_role()` (design-first → `system-architect` first, marker consumed,
> next sweep → `be-developer`). **No new canonical status** — the 26-status model in
> `knowledge/ticket-lifecycle-and-statuses.md` stays untouched (Option A rejected).

This ADR settles the five remaining open points under that direction: detection signal,
Option-B consumption/loop-safety/crash semantics, seat-model pin, AC3 mechanical guard, and
the kill-switch name. It is a decision record; ABS-213 carries the code and tests.

Per ADR-A-0004 (humans own irreversibility) this ADR ships `status: proposed`; acceptance is
human-only. That same rule is the subject of decision (d).

## Decision

### (a) Detection signal — a plain `design-first` label

A design-first story is marked by the exact label **`design-first`**, read via the existing
`ticket_has_label "$dump" "design-first"` predicate (the exact-match, anti-substring reader
added in ABS-101). No new field, no body parsing.

**Rejected: a `flag:design-first` flag.** The flag vocabulary is a *validated closed set*
(`design|security|data|skip-review|skip-test`) enforced in `scripts/jira-tracker.sh` at both
`create` and `update`; adding a member means editing two validators. Worse, flags are the
input to `conditional_flag_for()`, which drives status SKIP-FORWARD — but design-first must
**not** create or gate any status (Option A is rejected). And `design-first` reads as a
near-twin of the existing conditional `design` flag (the `ui-ux-design` station), inviting
confusion. A plain label is the minimal, collision-free carrier (ADR-A-0010): it round-trips
already (ABS-101), needs zero adapter change, and lives in the same `tracker get` dump
`resolve_implementer_role()` already reads — so reading it costs nothing extra.

### (b) Option-B semantics — the label is a one-shot latch consumed by the architect handoff

At `Ready for Development`, `map_action` yields `SPAWN -` and `resolve_implementer_role()`
resolves the ticket-derived implementer. The new rule (gated by (e)):

> Resolve to **`system-architect`** when ALL hold: routing is enabled (§e); the base role
> (frontmatter `role` / `ORCH_DEFAULT_ROLE`) is a **dev implementer**
> (`be-developer|fe-developer|data-engineer`); the ticket has label `design-first`; and the
> ticket does **not** have label `design-first-done`. Otherwise resolve to the base role
> unchanged.

**Consumer = the architect seat's terminal handoff (not the runner, not spawn time).** On
completing the ADR (committed to the story branch, `status: proposed`), the system-architect
seat's exit action appends the label **`design-first-done`** via the adapter (`tracker update
<id> labels …`), then re-releases the ticket at `Ready for Development`. Adding
`design-first-done` — not removing `design-first` — preserves the audit trail that the ticket
*was* design-first while flipping the routing predicate false.

**Consumption is atomic with success.** The only action that adds `design-first-done` is a
*successful* architect handoff. This is the deliberate choice over runner-at-spawn-time
consumption, which would flip the latch before the ADR exists.

**Loop-safety (no re-spawn of the architect after handoff).** Routing to `system-architect`
*requires* `design-first ∧ ¬design-first-done`. Once the successful handoff adds
`design-first-done`, that predicate is permanently false for this ticket, so no later sweep
can re-resolve to the architect. The **next sweep** (the poll re-read guard, or the
stall-reconcile sweep on the resting `Ready for Development` ticket, ABS-198) re-dispatches and
resolves to the base dev role — exactly the Operator's "marker consumed → next sweep spawns
be-developer". No self-transition event is required; liveness is the existing resting-ticket
reconcile, correctness is the latch. The re-read/idempotency guard (`ticket_still_in`, §5.4)
already makes a repeated `Ready for Development` dispatch safe.

**Crash / timeout before consumption.** If the architect seat crashes or times out before it
adds `design-first-done` + commits the ADR, the latch is untouched (`design-first` present,
`design-first-done` absent) → the next sweep re-resolves to `system-architect` and re-attempts
the authoring. Unbounded retry is prevented by the existing loop-breakers with **no new
machinery**: crash-backoff (ABS-118), per-visit respawn escalation (ABS-132), and the
cross-visit / escalation-budget auto-park (ADR-A-0018) on the repeating
`(system-architect, Ready for Development)` failure — which parks to `Blocked` with a single
operator NOTIFY. A partial architect run that committed the ADR but died before the label write
simply re-runs the (idempotent) authoring; a proposed-ADR already on the branch is re-asserted,
not duplicated.

### (c) Architect seat model — Opus (already pinned)

The system-architect seat is already pinned to Opus by role frontmatter
(`harness/claude/agents/system-architect.md`: `model: opus`), which the generated `.claude/`
inherits — matching established practice (memory `architect-tasks-on-opus`: Sonnet missed key
bits in ADR work). No change is required to run this path on Opus. Per-run override remains the
ABS-111 B6 seam **`ORCH_MODEL_SYSTEM_ARCHITECT`** (e.g. `=sonnet` to downsize), which beats the
frontmatter via `role_env`. Decision: keep the frontmatter `model: opus` as the committed
default; do not hard-code a model in the routing code.

### (d) AC3 mechanical guard — a suite test, not a `.claude` hook

The "agent-authored ADR MUST be `status: proposed`" check (the ABS-199/204 lesson: ADR-A-0018
was authored `accepted` and had to be downgraded) lives as a **shell test in the repo suite**
(e.g. `tests/test-adr-status.sh`, wired into the existing runner so AC4's green suite covers
it) — **not** as a `.claude/hooks/` hook. Rationale: `.claude/` is governor-generated from the
pinned `.governor-tag` (ABS-94), so a hand-added hook there is not the durable, version-
controlled home; a suite test is adapter-neutral, runs in CI and in the QAS/review gate, and is
the same discipline ADR-A-0018's implementation used (`tests/test-orchestrator.sh`).

The test asserts, over every `adrs/**/*.md` except `README.md`:

1. a `status:` frontmatter field is present and in `{proposed, accepted, superseded,
   deprecated}`; and
2. **`status: accepted` or `status: superseded` ⇒ non-empty `accepted_by` AND `accepted_date`
   frontmatter** — the human-acceptance evidence a proposed ADR omits (cf. ADR-A-0004
   `proposed`, no acceptance fields, vs. ADR-A-0017 `accepted` with both).

This is fully mechanical and deterministic: an ADR promoted to `accepted` without the
human-acceptance fields fails the suite, catching the ADR-A-0018 error class at the gate. The
design-first architect seat only ever writes `proposed` (no acceptance fields), so it passes by
construction; promotion to `accepted` stays human-only (ADR-A-0004).

### (e) Kill-switch — `ORCH_DESIGN_FIRST_ROUTING`, default-on

Per the ABS-111 convention (every new seam is default-on with an `ORCH_*=0` escape), the
architect-first role switch is gated by **`ORCH_DESIGN_FIRST_ROUTING`** (default `1`). Set
`ORCH_DESIGN_FIRST_ROUTING=0` to restore the legacy `resolve_implementer_role()` behavior (base
role always, `design-first` label ignored). When disabled, a design-first ticket routes
straight to the dev seat as before — fail-open to the pre-ABS-213 path.

## Consequences

- Design-first stories get a regular pipeline path: the architect authors the proposed ADR
  first, then the dev seat implements the *decided* topology as pure execution — no operator
  hand-spawns.
- **Zero new status** — the 26-status model is untouched (Operator direction / Option A
  rejected). The change is localized to `resolve_implementer_role()` plus the architect seat's
  exit action; `map_action`, `conditional_flag_for`, and `skip_forward_target` are unchanged.
- **Zero adapter change** for the signal — `design-first` / `design-first-done` are free-form
  labels that already round-trip (ABS-101).
- No new loop-breaker code — crash/timeout re-attempts and their upper bound reuse ABS-118 /
  ABS-132 / ADR-A-0018 exactly.
- New label vocabulary: `design-first` (input, set by BSA/PO at decomposition or by the
  operator) and `design-first-done` (latch, written only by a successful architect handoff).
- The AC3 guard hardens *all* ADRs, not just design-first ones: any future ADR promoted to
  `accepted` without human-acceptance frontmatter now fails the suite.
- Latency: a design-first ticket waits one extra reconcile/poll interval between the architect
  handoff and the dev spawn (the "next sweep"). Acceptable for this low-frequency path; an
  optional runner re-enqueue on async-spawn completion could shorten it later (out of scope).

## Alternatives considered

1. **Option A — a new conditional pre-stage / status** that spawns `system-architect` then
   SKIP-FORWARDs when unflagged (mirrors `Design → ui-ux-design`). **Rejected by the human
   Operator (2026-07-12):** it adds a canonical status to the documented 26-status model.
   Option B's in-place switch is a smaller diff and leaves the status model untouched.
2. **`flag:design-first` instead of a plain label.** Rejected — see (a): dual-validator edit,
   pollutes the SKIP-FORWARD flag namespace, and collides in meaning with the `design` flag.
3. **Runner consumes the latch at architect-spawn time.** Rejected: it would flip routing to
   the dev seat before the ADR exists, so an architect crash/timeout would let the dev proceed
   with no ADR — defeating the whole precondition. Consumption must be atomic with the
   *successful* handoff (b).
4. **A `work/.orchestrator/designfirst-<ticket>` marker file** (à la ADR-A-0018 cross-visit
   memory). Rejected as unnecessary here: ADR-A-0018 used a local file to avoid network reads
   in the loop-breaker path, but `resolve_implementer_role()` already does a `tracker get` every
   time, so the label latch is free and is the single adapter-visible source of truth (no
   local/remote divergence, survives runner restarts).
5. **AC3 as a `.claude/hooks/` hook.** Rejected — see (d): `.claude/` is governor-generated, so
   the durable home is a version-controlled suite test.
6. **Removing the `design-first` label on consume** (instead of adding `design-first-done`).
   Rejected: it erases the provenance that the ticket was design-first. Appending a `-done`
   latch flips the predicate while preserving the audit trail.

## Related Decisions

- [ADR-A-0004](ADR-A-0004-human-approval-boundaries.md) — humans own ADR acceptance; this ADR
  ships `proposed`, and decision (d) enforces the proposed/accepted boundary mechanically.
- [ADR-A-0018](ADR-A-0018-cross-visit-blocker-classification.md) — the crash/loop bounds this
  ADR reuses for the architect crash-before-consume case; and the label-vs-local-file authority
  reasoning.
- [ADR-A-0010](ADR-A-0010-minimal-change-default.md) — minimal-change default (plain label, no
  new status, no new loop-breaker).
- [ADR-A-0001](ADR-A-0001-three-level-adr-hierarchy.md) — this is an `agentic` (cross-project,
  boilerplate-owned) orchestration decision.
- [ADR-A-0002](ADR-A-0002-fresh-subagent-execution.md) — fresh-subagent-per-task boundary the
  architect-then-dev sequencing respects (two separate seats, not one).

## References

- ABS-213 (this decision's ticket; carries the code + tests). Operator direction comment
  (2026-07-12) fixing Option B; be-developer ADR Authoring Request (2026-07-11).
- Operator-Retro §4 (origin; left the sequencing mechanism open).
- Evidence: ABS-199, ABS-204 (2026-07-10 design-first stops-the-line + manual operator
  architect spawns); ADR-A-0018 (agent ADR wrongly authored `accepted`, downgraded — the AC3
  lesson).
- `scripts/orchestrator.sh`: `resolve_implementer_role()` (§2.2), `map_action()`,
  `conditional_flag_for()` / `skip_forward_target()` (unchanged), `ticket_has_label()`,
  `role_env()`, ABS-111 default-on-with-`ORCH_*=0` convention.
- `scripts/jira-tracker.sh`: `flag:`/label round-trip (ABS-101), closed flag-vocab validators.
- `harness/claude/agents/system-architect.md`: `model: opus` frontmatter pin.
