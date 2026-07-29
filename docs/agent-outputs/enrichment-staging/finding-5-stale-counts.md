# Fix stale agent/skill counts and team-config roster (Audit Finding #5)

## Goal
Every live doc and config asserting an agent/skill count is accurate: 17 agents (not 11),
21 skills (not 17/18), `.claude/team-config.json` reflects the current 17-role roster.

## Scope
- **In scope**: correct "11 agents"→17 and "17/18 skills"→21 in the 10 enumerated live
  docs (see AC-1); update `.claude/team-config.json` to the current roster.
- **Out of scope**: adding/removing actual agents; restructuring docs; editing `docs/releases/`
  historical records.

## Environment Prerequisites
None.

## Acceptance Criteria
- [ ] AC-1: `grep -rn '11 agents' . --exclude-dir=.git --exclude-dir=docs/releases` returns
  no hit. Confirm these files updated: `.agents/README.md`, `.claude/SETUP.md`,
  `harness/.claude/SETUP.md`, `docs/guides/WORKSPACE-ADOPTION-GUIDE.md`,
  `docs/guides/GETTING-STARTED.md`, `docs/onboarding/DAY-1-CHECKLIST.md`,
  `docs/onboarding/AGENT-SETUP-GUIDE.md`, `docs/whitepapers/HARNESS-v2.5.0-KT.md`,
  `docs/whitepapers/README.md`, `docs/whitepapers/ANTHROPIC-RESEARCH-ALIGNMENT.md`.
  Any additional live hits also corrected.
- [ ] AC-2: `grep -rn '17/18 skills\|17 skills\|18 skills' . --exclude-dir=.git
  --exclude-dir=docs/releases` returns no hit.
- [ ] AC-3: Role set in `.claude/team-config.json` exactly matches `.claude/agents/`.
  Verify with: `comm -3 <(jq -r '.roles[].name' .claude/team-config.json | sort)
  <(ls .claude/agents/*.md | xargs -I{} basename {} .md | sort)` returns empty.
  (Adapt jq path to actual schema.)
- [ ] AC-4: Repo lint and build scripts (package.json) exit 0 after changes.

## References
- **Origin**: BSA Grooming, ABS-138 Finding #5
- **Related**: ABS-139, ABS-140, ABS-148 (confirm none already closed #5)
- **Patterns/Specs**: `knowledge/agent-roster-and-gates.md`. No applicable `patterns_library/` entry.

## Guardrail Annotation
- **Feasibility**: flagged
- **Applicable ADRs**: ADR-A-0010 (targeted corrections only; do not restructure docs or
  rename agents); ADR-A-0004 (merge to main is human gate)
- **Approval Boundaries**: merge to main is the human gate (ADR-A-0004)
- **Constraints**: Source of truth for count = `ls .claude/agents/*.md | wc -l`. Do NOT
  update `docs/releases/` entries (historical). Correct counts only.

## Context Pack
- ADR-A-0004: merges to main are human-only (`adrs/agentic/ADR-A-0004-human-approval-boundaries.md`)
- ADR-A-0010: targeted corrections only (`adrs/agentic/ADR-A-0010-minimal-change-default.md`)
- Pattern paths: `knowledge/agent-roster-and-gates.md`
- Code refs: `.claude/team-config.json`, `.claude/agents/` (source of truth), 10 live docs in AC-1
- Guardrails: `model:sonnet`; full gates (functional config — no skip)
