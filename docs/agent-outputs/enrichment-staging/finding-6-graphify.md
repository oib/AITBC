# Rebuild graphify-out from current HEAD (Audit Finding #6)

## Goal
`graphify-out/` is regenerated from current HEAD so the mandated agent-context source
(ADR-A-0003 step-3) reflects the current codebase, not the stale snapshot.

## Scope
- **In scope**: regenerate `graphify-out/` using `graphify update .` from current HEAD;
  commit the result with the source commit hash recorded.
- **Out of scope**: changing graphify tooling, config, or output format.

## Environment Prerequisites
None (graphify is a local tool). If `graphify update .` requires network or credentials,
stop and escalate to a human (ADR-A-0004 amendment).

## Acceptance Criteria
- [ ] AC-1: `graphify update .` exits 0 without errors.
- [ ] AC-2: `cat graphify-out/GRAPH_REPORT.md | grep 'Built from commit'` outputs the
  commit hash matching `git rev-parse HEAD` at the time of regeneration.
- [ ] AC-3: File coverage in the report is consistent with the current tree. Run:
  `ACTUAL=$(find . -name '*.ts' -o -name '*.md' -o -name '*.js' | grep -v node_modules |
  grep -v .git | wc -l)` and verify the graph reports >= ACTUAL * 0.9 files processed
  (accounts for excluded paths). No reference to the old `edd4cca6` snapshot commit.
- [ ] AC-4: `graphify-out/` changes (including `graph.json` and `GRAPH_REPORT.md`) are
  committed to the repo.

## References
- **Origin**: BSA Grooming, ABS-138 Finding #6
- **Related**: ABS-138 Finding #2 (graphify-out is also a mandated context source for agents)
- **Patterns/Specs**: `knowledge/orchestrator-hardening-abs-111.md` (agents rely on graphify-out).
  No applicable `patterns_library/` entry. Generation command: `graphify update .`

## Guardrail Annotation
- **Feasibility**: flagged
- **Applicable ADRs**: ADR-A-0003 (graphify-out is step-3 of the mandatory agent context
  sequence; regeneration is necessary maintenance); ADR-A-0010 (regen only — no tooling changes);
  ADR-A-0004 (merge to main and credential use are human gates)
- **Approval Boundaries**: merge to main is the human gate; if `graphify update .` requires
  network/credentials, escalate (ADR-A-0004 amendment 2026-07-03)
- **Constraints**: Run `graphify update .` only. No tooling config changes. If graphify
  requires credentials, stop + escalate.

## Context Pack
- ADR-A-0003: graphify-out is step-3 of the mandatory context sequence (`adrs/agentic/ADR-A-0003-context-minimization.md`)
- ADR-A-0004: merges to main and credential use are human-only gates (`adrs/agentic/ADR-A-0004-human-approval-boundaries.md`)
- ADR-A-0010: regen only; no tooling changes (`adrs/agentic/ADR-A-0010-minimal-change-default.md`)
- Pattern paths: `knowledge/orchestrator-hardening-abs-111.md`; no `patterns_library/` entry
- Code refs: `graphify-out/GRAPH_REPORT.md` (current build commit: `d3241062`); `graphify-out/graph.json`
- Generation command: `graphify update .`
- Guardrails: `model:sonnet`; full gates (regen correctness needs review — no skip)
