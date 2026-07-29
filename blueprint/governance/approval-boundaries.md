# Human Approval Boundaries

The design rule: **humans own irreversibility**. Everything reversible is delegated to agents;
everything hard to undo passes an explicit human gate. Workflow `human-gate` steps reference the
boundary ids below.

| Gate id | Decision | Enforcement mechanism |
|---------|----------|----------------------|
| `architecture-change` | Architecture changes | ADR/Governance Checker flags → Architect proposes ADR → human accepts |
| `breaking-change` | Breaking changes | adr-check gate detects → human sign-off recorded on the ticket |
| `merge-to-main` | Merges to main / protected branches | Git provider branch protection **and** the git adapter structurally cannot merge protected branches |
| `additional-costs` | Additional license costs & additional LLM API costs | Cost approval gate: workflow pauses on `cost_flags` with `approved: null` |
| `production-deployment` | Production deployments | Release Agent prepares only; no deploy capability is granted to any role |
| `adr-acceptance` | Every accepted ADR (all three levels) | Agents can only write `status: proposed`; the ADR/Governance Checker rejects agent-side `accepted`; schema requires `accepted_by` |
| `epic-acceptance` | Final epic acceptance | PO recommends; human moves tickets to ready-for-merge |
| `migration-plan-approval` | Existing-project migration plan | No files written before approval (migration workflow) |
| `boilerplate-drift` | Handling of locally modified boilerplate-owned files | Upgrade workflow pauses per drifted file |
| `blocker-resolution` | Unresolvable blockers | blocked-escalation notifies; human answers on the ticket |
| `raw-secret-access` | Any agent seeing a raw secret value | Secrets adapter default is mediated access; raw exposure needs explicit per-task human approval ([security.md](security.md)) |

## What agents MAY do without asking

Create branches and PRs (including with documented failing gates), propose ADRs, create/update/
transition tickets within the status machine, run gates, prepare deployments and release notes,
comment everywhere, and reassign work among themselves via the PO/Coordinator.

## Non-negotiables

- No agent merges to main. No agent deploys to production. No agent accepts an ADR.
  These are permanent, not v1 restrictions.
- A human approval in one context never extends to another (approving one cost flag does not
  approve the next one).
- Every human gate is cleared **in the task tracker** (status change, comment, or ADR edit) so
  the decision is durable and auditable.
