---
type: concept
resource: AGENTS.md
tags: [agents, workflow, governance]
timestamp: 2026-07-03
---

# Agent roster and gates

The boilerplate ships **17 agent roles** (extended from an original 11 by ADR-A-0012), organized
around a round-table philosophy: equal voice, but structural independence gates that no
implementer can collapse into itself.

## The 17 roles

Orchestration/coordination: **TDM** (reactive blocker resolution, not orchestration),
**PO-Agent** (story acceptance post-QAS, epic-completion determination, WSJF prioritization).
Planning: **BSA** (requirements, acceptance criteria, follow-up ticket decisions),
**Issue Enrichment Agent** (sole owner of ticket creation: dedup → format → create),
**System Architect** (pattern validation, Stage 1 PR review, guided ADR authoring).
Design: **UI/UX Design Agent**, **QAS-Design** (independent design testing).
Implementation: **FE Developer**, **BE Developer**, **Data Engineer**,
**Data Provisioning Engineer**, **Tech Writer**.
Quality/release: **QAS** (gate owner), **Security Engineer**, **RTE** (PR shepherd).
Meta: **Self-Improvement Agent** (skill mining, PO-triggered), **Boilerplate Migration Agent**
(single responsibility: migrate a consuming project to the current boilerplate version).

## Gate chain (standard path)

```text
BSA (spec) → Implementer (FE/BE/DE) → QAS gate → RTE (PR) → 3-Stage PR Review → HITL merge
```

Exit states mark each handoff: Implementer → `"Ready for QAS"`; QAS → `"Approved for RTE"`;
RTE → `"Ready for HITL Review"`; System Architect (Stage 1) →
`"Stage 1 Approved - Ready for ARCHitect"`; HITL → `MERGED`.

**3-Stage PR Review**: Stage 1 System Architect (pattern validation) → Stage 2 ARCHitect-in-CLI
(architectural alignment, cross-cutting concerns) → Stage 3 HITL (final merge authority — the
only stage that actually merges).

**Follow-up chain** (review findings never die in comments): Review Agent → BSA (decide
create/in-scope/discard) → Issue Enrichment Agent (`duplicate-detection` skill → `issue-enrichment`
skill → create/append via the task-tracking adapter) → PO-Agent (prioritize into backlog).

## Role collapsing

**Collapsible**: RTE — PR creation/CI shepherding may be done by the implementer directly for
simple, single-agent work. **Non-collapsible (independence gates)**: QAS, QAS-Design, and
Security Engineer — each requires a spawned subagent even in an otherwise-collapsed workflow,
because self-review bias and conflict of interest make implementer self-certification invalid.

## Exit states and the stop-the-line gate

Before any implementation begins: no acceptance criteria/DoD on the ticket → **stop immediately**,
escalate to BSA. Work never proceeds on an underspecified ticket.

## Related

- [ticket-lifecycle-and-statuses.md](ticket-lifecycle-and-statuses.md) — the status transitions
  each gate corresponds to
- [loop-termination.md](loop-termination.md) — how the QAS/QAS-Design gate loop is bounded
- [approval-boundaries.md](approval-boundaries.md) — the decisions even PO-Agent cannot make
- Source: `AGENTS.md`, `docs/sop/AGENT_WORKFLOW_SOP.md` (vNext Workflow Contract, Role
  Collapsing Guidelines), `adrs/agentic/ADR-A-0012-agent-team-extension.md`
