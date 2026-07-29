# Restore functional CI for Bitbucket-hosted repo (Audit Finding #1)

## Goal
CI actually runs on every PR: `bitbucket-pipelines.yml` is added with the same checks the
GitHub Actions workflows intended; the literal `AITBC` regex is replaced with a
real `ABS-[0-9]+` pattern; dead GitHub Actions workflows are removed or marked inactive.

## Scope
- **In scope**: create `bitbucket-pipelines.yml` with the enumerated pipeline steps; fix the
  `AITBC` regex in `.github/workflows/pr-validation.yml`; decommission or annotate
  the 5 non-running GitHub Actions workflows.
- **Out of scope**: new check types beyond current intent; CI runner credential provisioning
  (human gate per ADR-A-0004).

## Environment Prerequisites
None (uses existing repo scripts; no new CI secrets required for authoring the YAML).
If a Bitbucket runner variable is needed for execution, that is a human-gate follow-up —
not this ticket.

## Acceptance Criteria
- [ ] AC-1: `bitbucket-pipelines.yml` exists at repo root and defines a pipeline for pull
  requests containing these steps (matching the intent of the removed GH Actions workflows):
  1. Install dependencies (e.g. `yarn install --frozen-lockfile`)
  2. Lint (repo's `yarn lint` or equivalent)
  3. Type check (repo's `yarn type-check` or equivalent)
  4. Tests (repo's `yarn test` or equivalent)
  5. Claude Code hooks wiring validation (`bash tests/test-hooks-behavioral.sh &&
     bash tests/test-hooks-config.sh`)
  6. Provider hook copies sync (`diff -r .claude/hooks agent_providers/claude_code/hooks`)
  7. Provider skills parity (`.github/scripts/check-skills-parity.sh`)
  8. PR rebase check (PR branch is up-to-date with base)
- [ ] AC-2: The ticket-key regex matches `ABS-123`-style keys and rejects the empty literal.
  Test: `echo "ABS-138" | grep -E "ABS-[0-9]+" && echo "AITBC" | grep -E
  "ABS-[0-9]+" || echo "template literal rejected"` — second grep must print "template
  literal rejected".
- [ ] AC-3: No GitHub Actions workflow in `.github/workflows/` implies coverage it cannot
  provide. Each workflow is either deleted or has a comment `# status: inactive — Bitbucket
  repo; replaced by bitbucket-pipelines.yml`.
- [ ] AC-4: `bitbucket-pipelines.yml` is valid YAML (`python3 -c "import yaml; yaml.safe_load(
  open('bitbucket-pipelines.yml'))"` exits 0).

## References
- **Origin**: BSA Grooming, ABS-138 Finding #1
- **Related**: ABS-138 Finding #2 (mirror drift — drift-check CI step depends on this CI)
- **Patterns/Specs**: `patterns_library/ci/github-actions-workflow.md`,
  `patterns_library/ci/deployment-pipeline.md`

## Guardrail Annotation
- **Feasibility**: flagged
- **Applicable ADRs**: ADR-A-0010 (add pipeline mirroring existing intent; no new check types);
  ADR-A-0004 (merge to main and credential provisioning are human gates)
- **Approval Boundaries**: merge to main = human gate; Bitbucket runner credential setup is
  a separate human gate (ADR-A-0004 amendment 2026-07-03)
- **Constraints**: Mirror existing check intent. If a step requires tooling not already in
  the repo, note it as a flag and skip rather than adding new dependencies.

## Context Pack
- ADR-A-0004: merges to main AND credential provisioning are human-only (`adrs/agentic/ADR-A-0004-human-approval-boundaries.md`)
- ADR-A-0010: mirror existing check intent; no new check types (`adrs/agentic/ADR-A-0010-minimal-change-default.md`)
- Pattern paths: `patterns_library/ci/github-actions-workflow.md`, `patterns_library/ci/deployment-pipeline.md`
- Code refs: `.github/workflows/` (5 workflows); `bitbucket-pipelines.yml` (to create);
  `tests/test-hooks-behavioral.sh`, `tests/test-hooks-config.sh`, `.github/scripts/check-skills-parity.sh`
- Guardrails: Bitbucket runner credentials = separate human gate; `model:sonnet`; full gates
