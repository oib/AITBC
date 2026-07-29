# Profiles — technology-neutral core, opinionated stacks on top

A **profile** binds the boilerplate's neutral *capabilities* to concrete *providers*. This is
how the same SAW-based harness stays technology-neutral while still working out of the box: the
neutral core declares *what* capability is needed (task tracking, docs, database, deploy, …);
a profile declares *which* tool fills it and points at the SAW skills/commands/agents that
implement it.

## Capabilities (neutral vocabulary)

| Capability | What it covers | Neutral interface |
|------------|----------------|-------------------|
| `task-tracking` | Read/create/update/comment/transition tickets; status changes trigger agents | [`neutral/adapters/task-tracking.md`](neutral/adapters/task-tracking.md) |
| `docs` | Durable human-facing documentation (specs, ADRs, guides) | [`neutral/adapters/docs.md`](neutral/adapters/docs.md) |
| `git` | Branches, diffs, PRs/MRs — never autonomous merge to protected branches | [`neutral/adapters/git.md`](neutral/adapters/git.md) |
| `database` | Schema, migrations, access control | [`neutral/adapters/database.md`](neutral/adapters/database.md) |
| `deploy` | Build & deploy pipelines (agents prepare; humans release to prod) | [`neutral/adapters/deploy.md`](neutral/adapters/deploy.md) |
| `notifications` | Human notification (epic ready, blocker needs input) | [`neutral/adapters/notifications.md`](neutral/adapters/notifications.md) |
| `design-system` | Design tokens/components/UX constraints (optional) | [`neutral/adapters/design-system.md`](neutral/adapters/design-system.md) |
| `secrets` | Mediated credential access; agents never see raw secrets by default | [`neutral/adapters/secrets.md`](neutral/adapters/secrets.md) |
| `evolution` | Self-evolution signals and auditable GEP assets (Genes/Capsules/Events) | [`neutral/adapters/evolution.md`](neutral/adapters/evolution.md) |

## Shipped profiles

| Profile | Stack | Use when |
|---------|-------|----------|
| [`neutral`](neutral/profile.yaml) | **Default.** Capabilities + stack-independent SAW drivers declared; providers left open (`mock`/`none`) | You want a stack-agnostic starting point, or a stack SAW doesn't ship |
| [`saw-stack`](saw-stack/profile.yaml) | Linear · Confluence · Supabase/Postgres+RLS · Docker/GitHub Actions · Next.js/Clerk/shadcn · Stripe | You want SAW's production-tested opinionated stack immediately |
| [`jira-github-postgres`](jira-github-postgres/profile.yaml) | Jira · GitHub · plain PostgreSQL · Docker/GitHub Actions · docs-in-repo | Reference for a **non-SAW** stack — proves the abstraction genericizes without editing harness files |
| [`evolver`](evolver/profile.yaml) | Neutral + Evolver self-evolution (offline, `--review`) | You want EvoMap Evolver feeding the Self-Improvement loop without Hub/network features |

## How a profile is used

1. `scripts/setup-template.sh` (SAW's bootstrap) fills identity placeholders and selects a
   profile.
2. The profile maps each capability to a provider and to the SAW skills/commands that implement
   it (e.g. `task-tracking → linear` binds SAW's `linear-sop` skill, `sync-linear` command, and
   `linear-mcp`).
3. Capabilities the profile marks `mock` or `none` degrade gracefully — the workflow still runs,
   with the corresponding gate skipped and flagged (mirrors SAW's optional-feature handling).

## Defining a new profile

Copy [`neutral/profile.yaml`](neutral/profile.yaml), set each capability's `provider`, and point
`implemented_by` at the SAW skills/commands/agents (or new ones you add). Genericizing a
capability that SAW currently hard-codes (e.g. swapping Linear for Jira) means providing the
adapter binding here — **not** editing SAW's harness files, which stay upgrade-clean via
[`.harness-manifest.yml`](../.harness-manifest.yml).

## Activating a profile (ABS-37)

Declaring a profile.yaml doesn't do anything by itself — something has to say *which* profile is
active. That activation point is mechanical and dependency-free:

**Precedence**: `ACTIVE_PROFILE` env var > `.active-profile` file (repo root) > `neutral` default.

```bash
# Inspect the active profile and each capability's resolved provider
scripts/profile.sh show

# Activate a profile (validates profiles/<name>/profile.yaml exists,
# then writes its name to .active-profile)
scripts/profile.sh set evolver

# One-off / CI override — wins over .active-profile without writing it
ACTIVE_PROFILE=evolver scripts/hooks/evolver-lifecycle.sh
```

`.active-profile` is a plain text file (just the profile name, no YAML) so it can be read with
bash 3.2 + grep/sed alone — the same no-parser-dependency constraint every profile/adapter
binding in this repo follows. `scripts/lib/profile.sh` is the sourceable helper that implements
the precedence rule and resolves a capability's provider (`get_active_profile`,
`get_capability_provider <capability>`), including the `based_on:` fallback: if the active
profile doesn't declare a capability itself (e.g. `jira-github-postgres` has no `evolution` key),
the helper reads it from the profile named in `based_on:` (typically `neutral`) instead.

`scripts/hooks/evolver-lifecycle.sh` sources this helper for its provider resolution; an
`EVOLUTION_PROVIDER` env var still overrides everything, unchanged from before ABS-37.

Bootstrap (`scripts/setup-template.sh`) does not yet write `.active-profile` automatically —
that wiring is tracked separately (ABS-48). Until then, activate a profile manually with
`scripts/profile.sh set <name>` after setup.
