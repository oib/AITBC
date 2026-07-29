---
type: concept
resource: adrs/agentic/ADR-A-0004-human-approval-boundaries.md
tags: [governance, security, human-in-the-loop]
timestamp: 2026-07-03
---

# Approval boundaries

Design rule: **humans own irreversibility**. Everything reversible is delegated to agents;
everything hard to undo passes an explicit, structural human gate — "the agent can't," not "the
agent shouldn't." Enforcement is structural where possible (no merge operation exposed for
protected branches; the ADR checker rejects non-`proposed` statuses from agents; no role is
granted deploy capability).

## The gates

| Gate id | Decision | Enforcement |
|---------|----------|-------------|
| `architecture-change` | Architecture changes | ADR/Governance Checker flags → Architect proposes ADR → human accepts |
| `breaking-change` | Breaking changes | adr-check gate detects → human sign-off on the ticket |
| `merge-to-main` | Merges to protected branches | Git provider branch protection + git adapter structurally cannot merge |
| `additional-costs` | License/LLM API costs | Cost approval gate pauses on `cost_flags` with `approved: null` |
| `production-deployment` | Production deploys | Release Agent prepares only; no role has deploy capability |
| `adr-acceptance` | Every accepted ADR | Agents write only `status: proposed`; checker rejects agent-side `accepted` |
| `epic-acceptance` | Final epic acceptance | PO-Agent recommends; human moves tickets to ready-for-merge |
| `migration-plan-approval` | Existing-project migration plan | No files written before approval |
| `boilerplate-drift` | Locally modified boilerplate-owned files | Upgrade workflow pauses per drifted file |
| `blocker-resolution` | Unresolvable blockers | Human answers on the ticket |
| `raw-secret-access` | Any agent seeing a raw secret | Mediated access is default; raw exposure needs explicit per-task approval |

## Credentials provisioning (ADR-A-0004 amendment, ABS-11)

Provisioning credentials, secrets, API keys, and external service accounts is human-only,
alongside feature initiation, merges to main, and cost approval. Agents never create, obtain, or
work around a missing credential — regardless of cost. An agent that hits a missing credential
stops and escalates with: the credential name, the consuming library/service, and where it must
be configured. This closed a real gap: uncodified free-tier credentials previously triggered no
boundary and produced unfixable tester/implementer iteration loops.

## PO-Agent authority carve-out (ADR-A-0004 amendment, ABS-9)

The PO-Agent gained full story-acceptance authority (post-QAS), epic-completion determination,
and autonomous WSJF backlog prioritization — narrowing but not removing the human boundary.
**Three decisions stay human-only**, and the PO-Agent escalates rather than decides them:
creating new features, merging to main, and approving additional costs.

## What agents MAY do without asking

Create branches/PRs (even with documented failing gates), propose ADRs, create/update/transition
tickets within the status machine, run gates, prepare deployments and release notes, comment
everywhere, reassign work among themselves.

## Non-negotiables

No agent merges to main, deploys to production, or accepts an ADR — permanent, not v1
restrictions. A human approval in one context never extends to another. Every human gate is
cleared **in the task tracker** so the decision is durable and auditable.

## Related

- [agent-roster-and-gates.md](agent-roster-and-gates.md) — which role hits which gate in the
  standard chain
- [loop-termination.md](loop-termination.md) — rule 6 (environment preflight) routes credential
  gaps here
- [capabilities-and-profiles.md](capabilities-and-profiles.md) — `approval_boundaries` is
  declared identically in every profile
- Source: `adrs/agentic/ADR-A-0004-human-approval-boundaries.md`,
  `blueprint/governance/approval-boundaries.md`
