---
type: concept
resource: TEMPLATE_SETUP.md
tags: [bootstrap, setup, known-limitation]
timestamp: 2026-07-03
---

# Bootstrap flow

How a new project starts from this template, and where the current implementation falls short
of the intended design.

## Intended model (blueprint §6)

Three modes — `new-project`, `existing-project`, `upgrade` — share one SAW entry point.
Bootstrap substitutes identity placeholders, validates tooling readiness against the mandatory
tooling layer (§19: task tracking adapter, git adapter, orchestrator/subagent runtime, knowledge
base, ponytail/minimal-change skill, quality gate runner, ADR/governance checker, notification
adapter — see [capabilities-and-profiles.md](capabilities-and-profiles.md)), and emits a gap
report; a project with unresolved mandatory capabilities is marked **not ready for agentic
execution**. Bootstrap is meant to be idempotent.

## What actually ships today

`scripts/setup-template.sh` (invoked via `bash scripts/setup-template.sh`, documented in
`TEMPLATE_SETUP.md`) is a **single linear wizard**: it prompts for identity values (project
name, GitHub org, author, ticket prefix, MCP server names, infrastructure names — the full
`{{PLACEHOLDER}}` set also listed in `.harness-manifest.yml`'s `identity` block) and substitutes
them across the repo. It does not branch on mode, does not select or write a `profiles/*/profile.yaml`
choice, and does not run a tooling-readiness/gap report.

## Prerequisites

- A repo created from the GitHub template (or the harness pulled into an existing repo per
  `docs/guides/WORKSPACE-ADOPTION-GUIDE.md`)
- Values for every placeholder in the table in `TEMPLATE_SETUP.md` (manual fallback if not using
  the wizard)
- Existing-project adoption additionally requires the analysis-first flow: read-only inventory →
  migration plan → **human approval gate** → staged PRs (blueprint §8), before agents take real
  tickets

## Known current limitation

The three-mode, profile-aware, gap-reporting bootstrap described in blueprint §6 is not yet
implemented — today's wizard only does placeholder substitution. A project must separately pick
a profile (see [capabilities-and-profiles.md](capabilities-and-profiles.md)) and there is no
automated readiness/gap report. The fix is tracked under **ABS-31**; do not assume mode-aware
bootstrap or an automated gap report exist until that ticket lands.

## Post-setup

`TEMPLATE_SETUP.md` gives a manual checklist (env template review, license line, delete
`TEMPLATE_SETUP.md`, choose profile, configure tracker) and points to
`docs/guides/GETTING-STARTED.md` for the first agent session and first PR.

## Related

- [capabilities-and-profiles.md](capabilities-and-profiles.md) — profile selection bootstrap is
  supposed to drive but currently doesn't automate
- [harness-sync-and-manifest.md](harness-sync-and-manifest.md) — the `upgrade` mode this flow is
  meant to share an entry point with
- Source: `TEMPLATE_SETUP.md`, `scripts/setup-template.sh`, `blueprint/BLUEPRINT.md` §6
  (Bootstrap Model)
