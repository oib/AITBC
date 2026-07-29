---
id: ADR-A-0003
title: Strict context minimization is a workflow quality requirement
status: proposed
scope: agentic
date: "2026-07-02"
---

## Context

Token usage scales with loaded context, and broad repository exploration is the dominant waste.
Worse, exploration-heavy agents produce less focused work. The cheapest context is the context
someone already summarized.

## Decision

We will treat excessive context loading as a workflow quality problem. Binding rules — the
mandatory context sequence in
[`profiles/neutral/adapters/knowledge.md`](../../profiles/neutral/adapters/knowledge.md):
start from the ticket, never the repository; load only packet-named artifacts; stop at the five
stop conditions (goal, owning capability, applicable ADRs/governance, affected files/contracts,
required gates); query the knowledge base — the in-repo OKF bundle
([`knowledge/index.md`](../../knowledge/index.md)) or a context-graph MCP — before any broad
grep or full-file exploration when one is configured; prefer pre-summarized ADR/design excerpts
inside tickets over rediscovery; declare every overrun in the handoff record with a reason.

## Consequences

Token spend becomes attributable: repeated overruns indict ticket quality, not executing agents,
and generate follow-up tickets against the ticket-creation workflow. Ticket creation gets more
expensive (embedding excerpts) so that execution gets much cheaper — paid once, saved N times.
