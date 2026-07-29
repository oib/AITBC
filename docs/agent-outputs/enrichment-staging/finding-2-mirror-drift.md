# Mirror governance: generator + drift guard for all provider mirrors (Audit Finding #2)

## Goal
One generator script produces all provider mirrors from the canonical `.claude/agents/` and
`.claude/skills/` source; all 17 agents are present and consistent across mirrors; drift
fails CI when any mirror is stale.

## Scope
- **In scope**: one generator script; regenerated mirrors for `agent_providers/claude_code/`,
  `.codex/agents/`, and the skills mirror (unifying the 3-way fork: `.claude/skills/`,
  `.agents/`, `.gemini/skills/`); a CI drift-check step; updated `.agents/README.md`.
- **Out of scope**: changing agent-prompt content/semantics; changes to `.claude/agents/`
  canonical definitions; CI runner changes beyond adding the drift-check step.

## Environment Prerequisites
None.

## Acceptance Criteria
- [ ] AC-1: A single script (path stated in PR description) regenerates all mirrors
  idempotently from `.claude/agents/` (agents) and `.claude/skills/` (skills) as canonical
  source. Running it twice on an already-synced mirror produces no file changes: `git diff
  --exit-code agent_providers/ .codex/ .agents/ .gemini/` exits 0 on second run.
- [ ] AC-2: After running the script: `diff <(ls .claude/agents/*.md | xargs basename | sort)
  <(ls agent_providers/claude_code/prompts/*.md 2>/dev/null | xargs basename | sort)` is
  empty (all 17 agents present). Same check for `.codex/agents/`.
- [ ] AC-3: Skills are sourced from `.claude/skills/` only; `.agents/` and `.gemini/skills/`
  are generated/symlinked — no independent edited copies. Verify: `diff .claude/skills/
  .agents/skills/` (or equivalent) exits 0 after generation.
- [ ] AC-4: A drift-check command (referenced in `bitbucket-pipelines.yml` per Finding #1 child)
  exits non-zero when a mirror is stale. Demonstrate: modify a source file in `.claude/agents/`,
  run the drift check, confirm non-zero exit; regenerate, confirm zero exit.
- [ ] AC-5: `.agents/README.md` references the generator script as the authoritative mirror source.

## References
- **Origin**: BSA Grooming, ABS-138 Finding #2
- **Related**: ABS-138 Finding #1 child (depends_on: CI must exist for drift-check AC-4).
  See `knowledge/harness-sync-and-manifest.md` for harness sync concept.
- **Patterns/Specs**: `patterns_library/ci/deployment-pipeline.md` (for the CI drift-check step).
  `knowledge/harness-sync-and-manifest.md`.

## Guardrail Annotation
- **Feasibility**: flagged
- **Applicable ADRs**: ADR-A-0003 (`.claude/` is canonical; generator must NOT edit canonical;
  mirrors are derived); ADR-A-0010 (generator scope = mirror reproduction only, no semantic
  changes); ADR-A-0004 (merge to main is human gate)
- **Approval Boundaries**: merge to main is the human gate (ADR-A-0004)
- **Constraints**: Generator treats `.claude/agents/` and `.claude/skills/` as READ-ONLY source.
  Do NOT change prompt semantics or restructure the canonical harness. model:opus because this
  defines the canonical model for all future harness syncs — wrong architecture is expensive.
- **#PLAN_UNCERTAINTY (resolved)**: Canonical source = `.claude/agents/` (agents) and
  `.claude/skills/` (skills). Mirror targets confirmed: `agent_providers/claude_code/prompts/`,
  `.codex/agents/`, `.agents/` (skills), `.gemini/skills/` (confirm presence with `ls .gemini/`).

## Context Pack
- ADR-A-0003: `.claude/` is canonical; mirrors are derived, never edited directly (`adrs/agentic/ADR-A-0003-context-minimization.md`)
- ADR-A-0004: merges to main are human-only (`adrs/agentic/ADR-A-0004-human-approval-boundaries.md`)
- ADR-A-0010: generator scope = mirror reproduction only (`adrs/agentic/ADR-A-0010-minimal-change-default.md`)
- Pattern paths: `patterns_library/ci/deployment-pipeline.md`; `knowledge/harness-sync-and-manifest.md`
- Code refs: `.claude/agents/` (canonical, 17 agents); `agent_providers/claude_code/prompts/` (17 files);
  `.codex/agents/` (0 files); `.agents/README.md`; `scripts/sync-claude-harness.sh`
- **depends_on**: Finding #1 child (drift-check CI step requires CI to be operational)
- Guardrails: `model:opus`; full gates
