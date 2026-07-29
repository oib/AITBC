# Cost Control

**Additional costs** = license costs and LLM API costs introduced by a chosen option — a new
paid dependency, a paid SaaS tier, a paid API, or a workflow that materially increases LLM usage
(e.g. enabling a new always-on agent).

## The gate

1. During ticket creation or planning, any option that introduces additional costs is recorded
   on the ticket as a `cost_flags` entry (`kind: license | llm-api | other`, `approved: null`).
2. The workflow **pauses at the `additional-costs` human gate** before the option may be
   selected. The Ticket Creation Agent must present the alternative (usually: the no-cost
   option and its trade-off) in the flag description.
3. The human approves or rejects each flag individually in the tracker; the decision
   (`approved`, `approved_by`) stays on the ticket as the audit record.
4. Rejected options force re-planning of the affected ticket.

## Reducing gate noise

- `config.costs.pre_approved_licenses` lists licenses/products that never trigger the gate
  (they were approved once, durably, by a human editing config).
- `config.costs.budget_hints` is informational context for the PO Agent's prioritization — the
  gate fires on **new cost sources**, not on usage fluctuations.

## Who watches the watchers

The ticket-quality gate verifies that tickets introduce no unapproved costs; the adr-check gate
re-verifies at implementation time (a dependency added mid-implementation triggers it too).
Cost approval is a first-class workflow gate — never a convention or a comment.
