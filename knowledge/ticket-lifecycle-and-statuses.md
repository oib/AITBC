---
type: concept
resource: profiles/neutral/adapters/task-tracking.md
tags: [workflow, task-tracking]
timestamp: 2026-07-03
---

# Ticket lifecycle and statuses

Task tracking is **active, not passive**: every status change is an event that triggers a
workflow ([`docs/sop/AGENT_WORKFLOW_SOP.md`](../docs/sop/AGENT_WORKFLOW_SOP.md)). The boilerplate
is tracker-agnostic — agents speak only the neutral interface in
[`profiles/neutral/adapters/task-tracking.md`](../profiles/neutral/adapters/task-tracking.md);
a provider (mock, Linear, Jira, GitLab) maps canonical statuses onto its own board.

## The canonical statuses (28: 10 v1 core + 16 v3 workflow + Canceled + Rejected)

[`statuses.yaml`](../profiles/neutral/adapters/statuses.yaml) defines **28** canonical statuses:
the **ten v1 core** statuses below (the v1/v2 happy path, unchanged), the **sixteen
v3 workflow** statuses (ABS-69/ABS-70) documented further down, and two cross-cutting
terminal rests — **Canceled** (ABS-338: ticket abandoned at the tracker source of truth; no seat
is ever spawned for it, the shadow mirror syncs it as a terminal rest) and **Rejected**
(PILOT-34: an operator consciously decided the ticket will not be implemented — "Won't Do";
entered only via the Mission Control Human-Override, an admin-only audited action, and treated
like Done/Canceled by the runner and sweeps). The v3 statuses are purely
additive — the v1 happy path still runs.

### The ten v1 core statuses

```text
Backlog → Ready for Development → In Progress → In Review → In Test
        → Ready for Human Acceptance → Ready for Merge → Done
                          (any active status) ↔ Blocked
                          (any active status) → Needs PO Decision
```

| Status | Entered when | Triggers |
|--------|--------------|----------|
| Backlog | Ticket created | PO prioritization sweep — **only if the ticket carries the `orchestrator-ready` label** (see Backlog opt-in gate below) |
| Ready for Development | Prioritized, dependencies clear, quality gate passed | Coordinator spawns implementation subagent |
| In Progress | Subagent starts | Progress monitoring |
| In Review | Handoff complete, PR/diff exists | Coordinator spawns Review Agent |
| In Test | Review passed / findings triaged | Coordinator spawns QA/Test Agent |
| Ready for Human Acceptance | Tests pass, gates green | PO epic-completion check; human notified on epic-complete |
| Ready for Merge | Human accepted ticket scope | Human merges (RTE has PR ready) |
| Done | PR merged | Documentation sweep, epic progress update |
| Blocked | Any agent hits an unresolvable obstacle | PO triage, then human escalation |
| Needs PO Decision | An agent, human, or sweep requests a product decision | Coordinator spawns PO-Agent |

The full transition table (which statuses each status may move to) is enforced by the adapter
and defined in [`profiles/neutral/adapters/statuses.yaml`](../profiles/neutral/adapters/statuses.yaml).
Blocked is reachable from, and returns to, any active (non-Done) status. Needs PO Decision is
likewise reachable from any active (non-Done) status and returns to Backlog, Ready for
Development, or Blocked once the PO-Agent has recorded its decision.

### The sixteen v3 workflow statuses (ABS-69/ABS-70)

v3 adds two pipelines — one seated agent role per transient status. Conditional story stages
(Design / Security Review / Test Prep / Design Test) are SKIP-FORWARDed by the orchestrator when
the ticket lacks the matching flag (spec §3.3). Full entry conditions, triggers and the exact
transition table (incl. bounces) live in
[`statuses.yaml`](../profiles/neutral/adapters/statuses.yaml).

**Epic pipeline (9 additive statuses; Backlog is the shared entry):**

```text
Backlog → PO Triage → Grooming → Enrichment → Ticket Review → Architecture Review
        → Stories In Flight → Epic Integration → Ready for Epic Acceptance → Epic Done
```

**Story pipeline (7 additive stages; the rest reuse the v1 core statuses):**

```text
Design → … → Security Review → Test Prep → … → Design Test → Story Acceptance
       → Merging → Docs → Done
```

(The 16 additive v3 statuses are: Design, Security Review, Test Prep, Design Test, Story
Acceptance, Merging, Docs — plus the epic pipeline's PO Triage, Grooming, Enrichment, Ticket
Review, Architecture Review, Stories In Flight, Epic Integration, Ready for Epic Acceptance,
Epic Done.)

## Backlog opt-in gate (`orchestrator-ready`, ABS-101)

The orchestrator does **not** act on a Backlog ticket by default. It picks one up — PO
prioritization sweep, and the mechanical [stall rules](#) — **only when the ticket carries the
`orchestrator-ready` label**. An unlabelled ticket rests untouched: no sweep, no stall raise, no
reconcile re-derive.

- **Why opt-in, not opt-out (a skip label):** the fail-safe default is "do nothing". A forgotten
  label yields inaction, never an agent grabbing an under-specified ticket. It also makes migration
  cheap — importing a project with a full backlog only means labelling the few tickets you want
  worked, instead of skip-labelling all the rest.
- **`orchestrator-ready` vs *agent-ready*:** these are different axes. `orchestrator-ready` is the
  human INPUT gate ("you may start this, grooming included"). *agent-ready* (issue-enrichment) is the
  OUTPUT of grooming ("fully specified, executable"). The label is orthogonal to the status machine:
  status says *where in the workflow*, the label says *may the factory touch this at all*.
- **Runtime behaviour:** adding the label to a resting Backlog ticket makes it eligible on the next
  reconcile sweep — no restart needed (labelled Backlog tickets are the one controlled exception to
  Backlog's normal exclusion from reconcile).
- **Config:** `ORCH_REQUIRE_START_LABEL` (default `1`; set `0` to disable the gate — every Backlog
  ticket eligible, e.g. a greenfield project where all tickets are agent-created) and
  `ORCH_START_LABEL` (default `orchestrator-ready`). See
  [`docs/sop/ORCHESTRATOR_SOP.md`](../docs/sop/ORCHESTRATOR_SOP.md).

## Canonical ticket fields

Every ticket carries: **Goal, Scope (in/out), Acceptance Criteria, Definition of Done, Test
Plan**, and relevant ADR context when useful — see
[`specs_templates/spec_template.md`](../specs_templates/spec_template.md).

## Ticket-quality gate

The Ticket Creation / Issue Enrichment Agent must verify, before a ticket reaches *Ready for
Development*: it is executable by an agent; has clear acceptance criteria and a definition of
done; has a test plan; carries enough context to avoid unnecessary repository exploration; and
introduces **no unapproved architecture changes, breaking changes, or costs** (violations route
to the Architect Agent or the cost gate, not the backlog).

## Adapter operations (all providers implement)

`get_ticket`, `search_tickets`, `create_ticket`, `update_ticket`, `comment`, `transition`,
`link`, `get_epic_children`, `parent`, `child_count`, `subscribe_events`, `assign_ticket`
(twelve operations; `assign_ticket` sets the assignee at spawn time — ABS-126 — and is a graceful
no-op when the accountId is empty). The authoritative operation contract is
[`profiles/neutral/adapters/task-tracking.md`](../profiles/neutral/adapters/task-tracking.md).
Events are `{ticket_id, from_status, to_status, actor, at}`, delivered at-least-once; the
Coordinator deduplicates by `(ticket_id, to_status, at)`.

## Provider bindings

`mock` is the live reference adapter: tickets as markdown+frontmatter in `work/tickets/`, all
twelve operations via `scripts/mock-tracker.sh` (incl. `assign`), events by polling. Linear
(`saw-stack`),
Jira/GitHub/GitLab (`jira-github-postgres`) bind the same interface.

## Related

- [capabilities-and-profiles.md](capabilities-and-profiles.md) — how `task-tracking` fits the
  wider capability model
- [agent-roster-and-gates.md](agent-roster-and-gates.md) — which agent triggers on which status
- [loop-termination.md](loop-termination.md) — the `Iteration N of M` bounce marker written into
  ticket comments during the In Review / In Test loop
- Source: `profiles/neutral/adapters/statuses.yaml`, `profiles/neutral/adapters/task-tracking.md`,
  `blueprint/BLUEPRINT.md` §14 (Ticket Lifecycle)
