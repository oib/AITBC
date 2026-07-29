---
id: ADR-A-0009
title: Cost-incurring options require a human approval gate
status: proposed
scope: agentic
date: "2026-07-02"
---

## Context

Agents choosing dependencies, services, or workflows can silently commit an organization to
license costs or increased LLM API costs. Costs are a business decision wearing a technical
disguise.

## Decision

We will count license costs and LLM API costs as additional costs. Whenever ticket creation or
planning selects an option that introduces additional costs, the workflow pauses at the
`additional-costs` human gate before the option may be chosen: the option is recorded as a
`cost_flags` entry (with the no-cost alternative and trade-off stated), the human approves or
rejects each flag in the tracker, and the decision persists on the ticket. Pre-approved
licenses (`config.costs.pre_approved_licenses`) skip the gate. Policy:
`.agentic/governance/cost-control.md`.

## Consequences

No agent-initiated cost surprises. The gate fires on new cost *sources*, not usage noise, which
keeps it quiet enough to be respected. Rejected flags force re-planning rather than negotiation.
