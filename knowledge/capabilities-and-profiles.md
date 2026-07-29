---
type: concept
resource: profiles/
tags: [architecture, configuration]
timestamp: 2026-07-03
---

# Capabilities and profiles

The boilerplate stays technology-neutral by splitting **what** the agentic SDLC needs
(a capability) from **which** tool fills it (a provider). A capability is a neutral interface
(`profiles/neutral/adapters/<capability>.md`); a **profile** (`profiles/<name>/profile.yaml`)
binds each capability to a provider and to the stack-independent SAW skills/commands/agents
that operate it. Binding a provider never edits harness files — it stays upgrade-clean via
[`.harness-manifest.yml`](harness-sync-and-manifest.md).

## The 10 capabilities

| Capability | Covers | Neutral default provider |
|------------|--------|---------------------------|
| `task-tracking` | Tickets; status changes trigger agents | `mock` |
| `docs` | Durable human-facing documentation | `mock` |
| `git` | Branches, diffs, PRs — never autonomous merge | `github` |
| `database` | Schema, migrations, access control | `none` |
| `deploy` | Build & deploy pipelines (humans release prod) | `none` |
| `notifications` | Human notification via the tracker | `task-tracking` |
| `design-system` | Design tokens/components (optional) | `none` |
| `knowledge` | Pre-summarized OKF bundle, queried before grep | `okf-repo` |
| `secrets` | Mediated credential access | `env` |
| `evolution` | Self-evolution signals (Genes/Capsules/Events) | `none` |

Each capability's `required: true/false` flag (set in `profile.yaml`) marks whether bootstrap
must resolve it before a project is "ready for agentic execution."

## Provider binding

`profile.yaml` lists, per capability: `interface` (the adapter doc), `provider`, and
`implemented_by` (agents/skills/commands/scripts that operate it). Example — `task-tracking` in
the neutral profile binds `provider: mock`, agent `tdm`, skill `safe-workflow`, and
`scripts/mock-tracker.sh`; the `saw-stack` profile instead binds `provider: linear` with
`linear-sop` / `sync-linear` / the Linear MCP on the **same** interface.

## Shipped profiles

| Profile | Stack | Use when |
|---------|-------|----------|
| `neutral` | Capabilities declared, providers `mock`/`none` | Stack-agnostic starting point |
| `saw-stack` | Linear · Confluence · Supabase/Postgres+RLS · Docker/GH Actions · Next.js | SAW's production stack |
| `jira-github-postgres` | Jira · GitHub · plain Postgres | Reference non-SAW binding |
| `evolver` | Neutral + Evolver self-evolution (offline) | Self-Improvement feed without Hub/network |

## Human-approval boundaries

Every profile carries the same `approval_boundaries` list (architecture-change,
breaking-change, merge-to-main, additional-costs, production-deployment, adr-acceptance,
epic-acceptance) — these are stack-independent invariants, not provider config. See
[approval-boundaries.md](approval-boundaries.md).

## Related

- [ticket-lifecycle-and-statuses.md](ticket-lifecycle-and-statuses.md) — the `task-tracking`
  capability's canonical model in depth
- [harness-sync-and-manifest.md](harness-sync-and-manifest.md) — how profile/provider choices
  survive a harness upgrade
- [evolution-loop.md](evolution-loop.md) — the `evolution` capability's only shipped provider
- [bootstrap-flow.md](bootstrap-flow.md) — how a profile gets selected at setup time
- Source: `profiles/README.md`, `profiles/neutral/profile.yaml`,
  `blueprint/BLUEPRINT.md` §5 (Configuration Model), §18 (Task-Tracking Adapter Model),
  §19 (MCP, Tool, and Skill Model)
