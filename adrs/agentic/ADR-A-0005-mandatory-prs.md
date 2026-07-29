---
id: ADR-A-0005
title: All agent work reaches main only through PRs
status: proposed
scope: agentic
date: "2026-07-02"
---

## Context

The PR is the one artifact where human review, gate results, test evidence, and approval
requirements naturally converge — and the merge button is the human gate that everything else
hangs from.

## Decision

We will make PRs mandatory for all agent work. A PR may include multiple tickets; an epic may
produce multiple PRs. Every PR description must include: ticket summary, implemented scope,
test evidence, quality gate results, gate exceptions, ADR references, and human approval
requirements (template: `.agentic/templates/pr-description.md`). Agents may create PRs with
failing gates only when the failure and reason are documented; Ready for Merge with exceptions
requires each exception justified and documented.

## Consequences

The human merge decision is always fully informed from the PR alone. No direct-to-main agent
commits exist, ever. PR descriptions become part of the durable, resumable state.

## Exceptions

**Dark Factory merge queue (bounded, POPM-approved 2026-07-07).** The Dark Factory
autonomous-agent merge queue (`dark-factory/docs/MERGE-QUEUE-POLICY.md`) may auto-enqueue and
squash-merge PRs via `gh pr merge --auto --squash`. This exception is bounded to:

- **GitHub-hosted consumer projects only** — not this governance/boilerplate repo, which stays on
  the `CONTRIBUTING.md` rebase-first, "Rebase and merge", human-merged flow.
- **Story PRs into an epic integration branch only** (`epic/AITBC-XX-{description}`),
  consistent with [ADR-A-0014](ADR-A-0014-workflow-v3-per-epic-merge-gate.md).

The human gate for the epic→`main` PR is **untouched**: it is never auto-merged and
never squash-merged by an agent (see [ADR-A-0004](ADR-A-0004-human-approval-boundaries.md)).
Any doc describing agent squash/auto-merge must cite this exception and stay within its scope.
