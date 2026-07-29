---
id: ADR-A-0012
title: Agent team extension to 17 roles with skills-based ticket workflow
status: proposed
scope: agentic
date: "2026-07-03"
---

## Context

The original agent lineup left gaps around product ownership, design, self-improvement,
boilerplate migration, and ticket hygiene. A first cut proposed seven new standalone agents,
but review showed overlap with existing roles (System Architect already owns ADRs; BSA already
owns requirements drafting) and conflict with the Role Collapsing guidelines
(`docs/sop/AGENT_WORKFLOW_SOP.md`), which push toward fewer, skill-equipped roles rather than
micro-agents. Jira epic ABS-1 (stories ABS-2 … ABS-10) tracked the restructured change.

## Decision

We will extend the team from 11 to **17 agents** via six new roles and two role extensions,
with algorithmic capabilities expressed as skills instead of standalone agents:

- **New roles:** PO-Agent (story acceptance, autonomous WSJF prioritization, epic-completion
  detection, orchestration triggers), UI/UX Design Agent (schema-conformant design + design
  acceptance criteria), QAS-Design Agent (independent design testing; non-collapsible
  independence gate), Self-Improvement Agent (skill mining + boilerplate improvement
  proposals; PO-triggered, no self-scheduling), Boilerplate Migration Agent (single
  responsibility: migrate a consuming project to the current boilerplate version),
  Issue Enrichment Agent (single owner of the ticket-creation workflow).
- **Role extensions:** System Architect gains guided ADR authoring (scan → update-vs-new →
  template/hierarchy → bidirectional links → stop-the-line); BSA gains the follow-up ticket
  decision (create / in-scope / discard, with drafting).
- **Skills instead of agents:** `duplicate-detection` (mandatory pre-creation dedup gate:
  reject / append / create, in-progress tickets never extended) and `issue-enrichment`
  (agent-ready formatting + guardrail annotation) are skills wired into the Issue Enrichment
  Agent. The originally proposed ADR-Creation, Task Extraction, and standalone Duplicate
  Detection agents are not created.
- **Authority change:** the PO-Agent holds full post-QAS story acceptance and autonomous
  backlog prioritization; creating new features, merging to `main`, and approving
  additional costs remain human-only (codified as the 2026-07-02 amendment to ADR-A-0004).

The canonical handoff chain for follow-up work is: reviewing agent → BSA (decision + draft) →
Issue Enrichment Agent (dedup → enrich → create via task-tracking adapter, ADR-A-0006/0007).

## Consequences

- `AGENTS.md`, `.claude/agents/`, both provider configs, and the SOPs describe 17 roles;
  consuming projects receive the new roles through the normal upgrade path (ADR-A-0008).
- Ticket-facing behaviour stays tracker-agnostic; production dedup requires the configured
  tracker MCP full-text search in the Issue Enrichment Agent's tool set.
- QAS and QAS-Design are both independence gates and never collapse into implementers.
- Human oversight narrows but sharpens: the three human-only decisions are hard boundaries
  every agent must escalate, not perform.

## Related decisions

- ADR-A-0001 (three-level ADR hierarchy) — placement and authority of this ADR.
- ADR-A-0004 (human-approval boundaries) — amended 2026-07-02 for PO-Agent authority.
- ADR-A-0005 (mandatory PRs), ADR-A-0009 (cost approval gate) — human-only boundaries.
- ADR-A-0006 / ADR-A-0007 (active task tracking / adapter model) — ticket workflow substrate.
- ADR-A-0008 (boilerplate ownership and upgrades) — rollout channel; version marker amended
  2026-07-03 (see its amendment note).
- ADR-A-0010 (minimal-change default) — scope rule for the Migration Agent.
