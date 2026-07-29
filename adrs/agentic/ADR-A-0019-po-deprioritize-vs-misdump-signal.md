---
id: ADR-A-0019
title: PO-deprioritize vs. mis-dump — an explicit declared-target marker is the routing signal for escalation seats
status: accepted
scope: agentic
date: "2026-07-11"
accepted_by: "Raphael Sahann (POPM)"
accepted_date: "2026-07-11"
---

## Context

Escalation seats (the PO-Agent's *Decision* seat, the TDM triage seat) resolve a raised or
blocked ticket by transitioning it onward. Today the escalation-resume routing is **by
discretion**: the seat picks a next status. Two behaviours are indistinguishable at the
mechanical level:

- a **legitimate PO deprioritisation** — the PO decides a raised ticket stays low priority and
  parks it back to `Backlog`. This path is shipped and guarded: `orchestrator.sh`
  (`last_po_park_epoch`, `stall_raise_suppressed`, ~L1110–1189) keys off the
  `Needs PO Decision -> Backlog` transition to suppress re-raising a ticket the PO already routed;
- a **mis-dump** — a seat that has no declared target throws the ticket back to `Backlog`
  accidentally, where the PO-park guard then treats it as a sanctioned park and it silently
  disappears from the flow.

The discriminator today is only the *transition path* (`from == Needs PO Decision`). That is not
a decision signal — a bare, target-less resume can land on the same path and be misread as a
legitimate park. ABS-198 M2 requires escalation seats to route **deterministically to origin**
rather than by discretion, without breaking the guarded PO-park path. The open question this ADR
settles: **what mechanical signal separates a legit deprioritisation from a mis-dump?** The
ABS-198 guardrail annotation said "no new ADR", but M2 changes sanctioned routing semantics that a
shipped guard depends on and that multiple seats must obey identically — a durable cross-project
mechanical contract, which is exactly the agentic-ADR level's purpose.

## Decision

1. **The signal is an explicit declared target, not the transition path.** An escalation seat that
   intends any onward routing MUST emit its verdict in its handoff / `kind: decision` comment with
   an explicit, machine-readable target — for a deprioritisation: `verdict: deprioritize` **and**
   `target: Backlog`. A resume whose handoff declares **no** target is, by definition, a mis-dump
   and MUST NOT be routed to `Backlog` by discretion.

2. **Routing rule (deterministic):**
   - Handoff declares a **legitimate target** (e.g. `verdict: deprioritize` / `target: Backlog`, or
     any other sanctioned target status) → apply that target.
   - Handoff declares **no target** → **Resume-to-Origin**: transition back to the recorded
     `BLOCKED-FROM=<status>` pre-blocked origin (`blocked_from_marker`,
     `last_transition_into_blocked_from`, ~L1867–1923) if one is recorded; otherwise **Halt in
     Blocked**. Never pick `Backlog` by discretion.

3. **The guarded PO-park path is unchanged and regression-protected.** A declared
   `verdict: deprioritize` / `target: Backlog` IS a legitimate declared target: it still produces
   the `Needs PO Decision -> Backlog` transition + reason comment that `last_po_park_epoch` reads,
   and `stall_raise_suppressed` continues to suppress re-raise (and re-arm on edit-after-park)
   exactly as shipped. The new rule is **additive** — it constrains only the *default for a missing
   declaration*; it never changes what counts as a legitimate park. The existing park-suppress /
   re-arm behaviour is the regression contract and must stay green.

This decision operates within ADR-A-0004 (deprioritisation remains PO authority; mis-dump
prevention is structural, not a new human boundary) and refines the canonical-status routing of
ADR-A-0006. It conflicts with no accepted broader-level ADR, so it declares no `overrides`.

## Consequences

- Escalation routing becomes deterministic and auditable: a Backlog park is honoured only when the
  seat declared it; an undeclared resume can no longer masquerade as a PO park.
- Escalation seats gain a small obligation — emit an explicit target in the handoff — enforced by
  the orchestrator's resume routing rather than left to seat discretion.
- No change to the human-only boundaries (ADR-A-0004) or to the shipped `last_po_park_epoch` /
  `stall_raise_suppressed` guard behaviour.

## Related Decisions

- [ADR-A-0006](ADR-A-0006-active-task-tracking.md) — canonical statuses this routing moves between.
- [ADR-A-0004](ADR-A-0004-human-approval-boundaries.md) — deprioritisation is PO authority; this
  ADR adds no new human boundary.
- [ADR-A-0002](ADR-A-0002-fresh-subagent-execution.md) — escalation seats run as fresh subagents;
  the declared-target marker is how their intent survives the spawn boundary.

## References

- `scripts/orchestrator.sh` — `last_po_park_epoch` / `stall_raise_suppressed` (~L1110–1189);
  `blocked_from_marker` / `last_transition_into_blocked_from` / `record_blocked_from` (~L1867–1923);
  Blocked → TDM triage spawn (~L3005–3015).
- ABS-198 M2 (Eskalations-Resume-to-Origin); ABS-76 (resume-to-origin marker); ABS-62 (PO-park
  re-raise guard).
