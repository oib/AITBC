# Remove dead files and deprecated command aliases (Audit Finding #7)

## Goal
Repo is free of audit-named dead paths. Each deletion is preceded by a reference-check;
no live caller is broken. Scope is exactly the named paths.

## Scope
- **In scope**: confirm existence + delete: `blueprint/AUDIT-GAP-PLAN.md`,
  `scripts/{generalize_commands.py,install-prompts.sh,apply-workflow.sh}`,
  `patterns/` dir (if present), `templates/` dir (if present), 5 deprecated
  `.claude/commands/` aliases.
- **Out of scope**: behavioural refactors; files with live callers; general cleanup.

## Environment Prerequisites
None.

## Acceptance Criteria
- [ ] AC-1: For each named path, `find . -path '<path>' -not -path './.git/*'` returns
  empty after deletion (or PR description notes it was already removed by ABS-139/140/148).
- [ ] AC-2: For each deleted path, `grep -rn '<basename>' . --exclude-dir=.git` returns
  no hit from any live file.
- [ ] AC-3 (aliases — verify first): Run `git log --diff-filter=D --name-only
  origin/main..HEAD -- .claude/commands/` to confirm what was already removed by done
  children. List remaining deprecated aliases by filename in the PR description and delete
  them. If live and harness commands/ are identical and done children removed all deprecated
  aliases, note this item is complete.
- [ ] AC-4: `npx markdownlint-cli '**/*.md' --ignore node_modules` exits 0; repo lint and
  build scripts (package.json) exit 0 after all deletions.

## References
- **Origin**: BSA Grooming, ABS-138 Finding #7
- **Related**: ABS-139, ABS-140, ABS-148 (verify prior removals first)
- **Patterns/Specs**: No applicable pattern. See `CONTRIBUTING.md` for PR workflow.

## Guardrail Annotation
- **Feasibility**: flagged
- **Applicable ADRs**: ADR-A-0010 (delete named paths only; no drive-by cleanup);
  ADR-A-0004 (merge to main is human gate)
- **Approval Boundaries**: merge to main is the human gate (ADR-A-0004)
- **Constraints**: Reference-check first (AC-2), delete second. If a "dead" path has a live
  caller, do NOT delete it — file a separate finding. Scope = audit-named paths only.

## Context Pack
- ADR-A-0004: merges to main are human-only (`adrs/agentic/ADR-A-0004-human-approval-boundaries.md`)
- ADR-A-0010: delete named paths only; no drive-by cleanup (`adrs/agentic/ADR-A-0010-minimal-change-default.md`)
- ADR-A-0003: open named files deliberately; no broad grep (`adrs/agentic/ADR-A-0003-context-minimization.md`)
- Pattern paths: none applicable
- Code refs: `blueprint/`, `scripts/`, `.claude/commands/` (19 commands at HEAD; harness identical)
- Guardrails: `model:sonnet`; full gates; no skip-review/skip-test
