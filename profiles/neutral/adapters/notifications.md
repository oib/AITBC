# Notification Adapter — Interface

> _Adapted from the clean-room blueprint. Inline `.agentic/…` names below are design-record concepts; their live homes are in the [crosswalk](../../../blueprint/CROSSWALK.md). Treat this file as the capability contract._

All human notification flows **through the task-tracking system** in v1 — the human's existing
inbox, no new channels. The adapter is a thin layer over the task-tracking adapter's `comment`
operation plus provider-native mention/watch mechanics.

## Operation

`notify_human(ticket_id, event, payload)` — posts a structured, human-readable notification
comment on the ticket/epic and triggers the provider's attention mechanism (Jira: mention +
watcher; GitLab: mention; mock: a `NOTIFICATIONS.md` inbox file at the store root).

## Events (must match `config.notifications.notify_human_on`)

| Event | Fired by | Payload |
|-------|----------|---------|
| `epic-ready-for-acceptance` | epic-acceptance workflow | Per-ticket summary, test evidence links, gate results, documented exceptions, PRs awaiting merge, ADRs awaiting acceptance |
| `unresolvable-blocker` | blocked-escalation workflow | What was attempted, why it can't proceed, the specific decision needed |
| `cost-approval-needed` | cost gate | Cost flags with descriptions and alternatives |
| `adr-awaiting-acceptance` | epic-intake / upgrade workflows | Proposed ADR summary + link |
| `boilerplate-drift-detected` | upgrade workflow | Drifted files + recommended handling |

## Rules

- The **final epic notification happens on the epic itself** in the tracker.
- Notifications are durable comments — part of the auditable record, never ephemeral pings.
- One notification per event occurrence; the Coordinator deduplicates re-fires.
