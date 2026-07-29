# Resolve merge-policy contradiction: dark-factory squash vs ADR rebase-only [ADR-GATED] (Audit Finding #8)

## Goal
The governance contradiction between `dark-factory/docs/MERGE-QUEUE-POLICY.md` (mandates
`gh pr merge --auto --squash`) and ADR-A-0004/CONTRIBUTING (rebase-only, human merges) is
resolved in one authoritative ADR, and the offending policy text is aligned to it.

## Scope
- **In scope**: author a new/updated ADR (proposed level: agentic) stating the single merge
  policy; align `dark-factory/docs/MERGE-QUEUE-POLICY.md` and `CONTRIBUTING.md` to the decision.
- **Out of scope**: implementing a new merge mechanism; changing CI configuration.

## Environment Prerequisites
None.

## Acceptance Criteria
- [ ] AC-1: A new/updated ADR is authored under `adrs/agentic/` following `docs/sop/ADR_AUTHORING_GUIDE.md`,
  with status `proposed`, stating the single authoritative merge policy for agent PRs.
- [ ] AC-2: `grep -n 'gh pr merge --auto --squash' dark-factory/docs/MERGE-QUEUE-POLICY.md`
  returns no line asserting it as the mandated policy (the contradiction is resolved).
- [ ] AC-3: `CONTRIBUTING.md` references or explicitly aligns to the decision in the ADR.
- [ ] AC-4: The ADR status is `proposed` at PR merge time. ADR acceptance is a human-only gate
  (ADR-A-0004): agent authors; human POPM/System Architect accepts (changes status to `accepted`).
  This child CANNOT be Done until a human changes the ADR status.

## References
- **Origin**: BSA Grooming, ABS-138 Finding #8; PO Triage — ADR Authoring Request to System Architect
- **Related**: `dark-factory/docs/MERGE-QUEUE-POLICY.md`; `CONTRIBUTING.md`;
  `adrs/agentic/ADR-A-0001-three-level-adr-hierarchy.md`; `adrs/agentic/ADR-A-0004-human-approval-boundaries.md`
- **Patterns/Specs**: `docs/sop/ADR_AUTHORING_GUIDE.md` (MANDATORY — read before authoring the ADR)
- **depends_on**: System Architect ADR Authoring Request outcome (PO downstream handoff — surface
  as a formal depends_on ticket once the SA request is captured as a ticket; do NOT proceed
  until SA has reviewed the contradiction and scoped the decision)

## Guardrail Annotation
- **Feasibility**: flagged — ADR acceptance is a human gate; child CANNOT be Done until
  a human accepts the ADR
- **Applicable ADRs**: ADR-A-0001 (authority order; agent authors `proposed`, human accepts);
  ADR-A-0004 (accepted ADRs are human-only)
- **Approval Boundaries**: (1) ADR acceptance — human-only gate (ADR-A-0004); (2) merge to main
  — human-only gate (ADR-A-0004)
- **Constraints**: Status MUST stay `proposed` at PR merge time. Do NOT self-accept. Do not
  implement a new merge mechanism — authoring + doc alignment only.
- **🚧 BLOCKED**: Do NOT set `orchestrator-ready` until SA ADR Authoring Request outcome
  is captured as a formal ticket and linked in depends_on.

## Context Pack
- ADR-A-0001: authority order; agent proposes, human accepts (`adrs/agentic/ADR-A-0001-three-level-adr-hierarchy.md`)
- ADR-A-0004: accepted ADRs are human-only; agents author `proposed` only (`adrs/agentic/ADR-A-0004-human-approval-boundaries.md`)
- ADR-A-0010: authoring + doc alignment only; no new merge tooling (`adrs/agentic/ADR-A-0010-minimal-change-default.md`)
- Pattern paths: `docs/sop/ADR_AUTHORING_GUIDE.md` (mandatory reference for ADR authoring)
- Code refs: `dark-factory/docs/MERGE-QUEUE-POLICY.md` (offending policy); `adrs/agentic/` (new ADR home);
  `CONTRIBUTING.md` (to align); `adrs/agentic/ADR-A-0004-human-approval-boundaries.md` (authority)
- Guardrails: 🚧 ADR-GATED; `model:opus`; full gates
