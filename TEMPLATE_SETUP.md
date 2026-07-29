# Template Setup Guide

This repository is a **GitHub template** for AI agent team workflows. After creating a new repository from this template, run the setup wizard to customize it for your project.

## Quick Setup

```bash
bash scripts/setup-template.sh
```

The wizard prompts for your project values and replaces all placeholders automatically.
In one bootstrap it also:

- **Generates `.harness-manifest.yml`** (schema v1.1) from your identity values, so the
  [harness sync tooling](docs/HARNESS_SYNC_GUIDE.md) can upgrade cleanly later.
- **Selects a [profile](profiles/README.md)** (default `neutral`) and records it in
  `.active-profile` — the activation point the workflow reads to bind capabilities to providers.
- **Emits `bootstrap-gap-report.md`** — a tooling-readiness report listing, per capability,
  whether it is `ready`, `mocked`, or `MISSING`, with an overall
  *ready / NOT ready for agentic execution* verdict.

The wizard is **idempotent**: run it again and it detects already-replaced placeholders
(prints "nothing to replace"), regenerates the manifest/report, and never re-prompts for a
git re-init it already performed.

### Performance on real projects

The wizard finishes in seconds even when the target project already contains a large
`node_modules` tree or a built output directory. All internal sweeps — candidate scan,
substitution, idempotency check, and remaining-token report — share one directory-exclude
list and never traverse:

`.git` · `node_modules` · `dist` · `build` · `.next` · `vendor` · `worktrees` · `tmp`

Only files that actually contain a `{{` placeholder are processed. All substitutions run as
a single `sed` call per file (one `-e` chain for all 30 placeholders), and the shell dialect
check (GNU vs. BSD sed) runs once at startup rather than once per file.

**Result**: a boilerplate tree overlaid onto a fresh `npm create next-app` project
(~11 000 files, real `node_modules`) bootstraps in about 2 seconds. The previous
implementation needed hours on the same tree.

### Non-interactive bootstrap

Provide values without prompts using a KEY=VALUE file (copy
[`bootstrap.values.template`](bootstrap.values.template)):

```bash
cp bootstrap.values.template bootstrap.values   # then edit it
bash scripts/setup-template.sh --values bootstrap.values --yes
```

Values resolve in this order: **`--values` file → environment variable of the same name →
built-in default → interactive prompt** (only when a TTY is attached). Environment variables use
the same names as the prompts (`PROJECT_NAME`, `TICKET_PREFIX`, …), so
`PROJECT_NAME=foo TICKET_PREFIX=FOO ... bash scripts/setup-template.sh --yes` works too.

When stdin is not a TTY and a **required** value is missing (`PROJECT_NAME`, `PROJECT_REPO`,
`PROJECT_SHORT`, `GITHUB_ORG`, `TICKET_PREFIX`), the wizard exits non-zero and lists exactly the
missing keys.

### Flags

| Flag | Effect |
|------|--------|
| `--values <file>` | Read KEY=VALUE inputs from a file (implies non-interactive). |
| `--yes` / `-y` | Skip the "Proceed?" confirmation (required in non-interactive mode). |
| `--profile <name>` | Select `profiles/<name>` (also honored via `PROFILE=` value/env). Default `neutral`. |
| `--allow-gaps` | In non-interactive mode, do **not** fail when the gap report is *NOT ready*. |
| `--finalize` | Delete the wizard (`scripts/setup-template.sh`) and `TEMPLATE_SETUP.md` after setup. |

> The wizard **no longer self-deletes by default** — that would break idempotent re-runs. Run
> `bash scripts/setup-template.sh --finalize` once your project is fully configured to remove the
> template-only artifacts. In non-interactive mode, a *NOT ready* gap report makes the wizard exit
> non-zero unless you pass `--allow-gaps`.

## Manual Setup

If you prefer manual customization, replace these placeholders across the repository:

| Placeholder | Description | Example |
|-------------|-------------|---------|
| `AITBC` | Project/repo short name | `my-saas-app` |
| `AITBC` | Full repo name (for URLs) | `my-saas-app` |
| `AITBC` | Project acronym (uppercase) | `ACME` |
| `{{PROJECT_DOMAIN}}` | Project website domain | `acme.com` |
| `oib` | GitHub organization or username | `acme-corp` |
| `AITBC` | Company/org display name | `Acme Corp` |
| `oib` | Primary author full name | `Jane Smith` |
| `oib` | Author first name | `Jane` |
| `oib` | Author last name | `Smith` |
| `o. o.` | Author initials (derived) | `J. S.` |
| `oib` | Author GitHub handle | `janesmith` |
| `andreas.fleckl@chello.at` | Author email | `jane@acme.com` |
| `{{AUTHOR_WEBSITE}}` | Author website URL | `https://janesmith.dev` |
| `oib` | Lead architect GitHub handle | `lead-dev` |
| `AITBC` | Linear/issue tracker prefix (uppercase) | `ACM` |
| `aitbc` | Ticket prefix lowercase | `acm` |
| `{{LINEAR_WORKSPACE}}` | Linear workspace slug | `acme` |
| `andreas.fleckl@chello.at` | Security contact email | `security@acme.com` |
| `aitbc` | Database username | `app_user` |
| `{{DB_PASSWORD}}` | Database password | `app_password` |
| `aitbc` | Database name | `app_dev` |
| `aitbc-postgres` | Database container name | `app-postgres` |
| `aitbc-dev` | Dev app container name | `app-dev` |
| `aitbc-staging` | Staging app container name | `app-staging` |
| `ghcr.io/oib` | Container registry URL | `ghcr.io/acme-corp` |
| `https://github.com/oib/AITBC` | Full GitHub repo URL (derived) | `https://github.com/acme-corp/my-saas-app` |
| `linear-mcp` | Linear MCP server name | `linear-mcp` |
| `confluence-mcp` | Confluence MCP server name | `confluence-mcp` |
| `jira-mcp` | Jira MCP server name | `jira-mcp` |
| `v2.35.0` | Harness version (derived from HARNESS_CHANGELOG.yml) | `v2.10.0` |

Additional placeholders in `CLAUDE.md` and `CONTRIBUTING.md` (technology stack):

| Placeholder | Description | Example |
|-------------|-------------|---------|
| `{{FRONTEND_FRAMEWORK}}` | Frontend framework | `Next.js` |
| `{{BACKEND_FRAMEWORK}}` | Backend framework | `Node.js` |
| `{{DATABASE_SYSTEM}}` | Database system | `PostgreSQL` |
| `{{ORM_TOOL}}` | ORM/query builder | `Prisma` |
| `{{AUTH_PROVIDER}}` | Authentication provider | `Clerk` |
| `{{LINT_COMMAND}}` | Lint command | `yarn lint` |
| `{{BUILD_COMMAND}}` | Build command | `yarn build` |
| `{{TEST_UNIT_COMMAND}}` | Unit test command | `yarn test:unit` |
| `{{DEV_COMMAND}}` | Dev server command | `yarn dev` |
| `main` | Main branch name | `main` |

### Manual-only tokens (not wizard-substituted)

These tokens are **not** touched by the setup wizard. Fill them in by hand for
your team, or provide them at runtime (Jira credentials/site are
human-provisioned and never committed). They are registered in the
manual-token whitelist (`tests/manual-token-whitelist.txt`) so the token-registry
check treats them as intentional rather than leaked.

| Placeholder | Description | Example |
|-------------|-------------|---------|
| `{{POPM_NAME}}` | Product Owner / Program Manager display name | `Alex Rivera` |
| `{{ARCHITECT_NAME}}` | Lead architect display name | `Sam Lee` |
| `{{JIRA_SITE}}` | Jira Cloud base URL (runtime env var, human-provisioned) | `https://acme.atlassian.net` |
| `{{JIRA_CLOUD_ID}}` | Jira Cloud instance id (runtime, human-provisioned) | `a1b2c3d4-...` |

## Version Identity

The harness uses a single source of truth for versioning:

| Component | Source | Purpose | Example |
|-----------|--------|---------|---------|
| Harness release version | `HARNESS_CHANGELOG.yml` (latest non-unreleased) | Project-facing version for sync, setup, and release management | `v2.10.0` |
| `.boilerplate-version` | Mirror of harness release version | Used by boilerplate migration agents to detect version skew | `v2.10.0` |
| `manifest_version` in `.harness-manifest.yml` | Schema version (independent) | Declares the manifest schema compatibility (e.g., v1.1), never synced | `1.1` |

The setup wizard reads `HARNESS_CHANGELOG.yml` to derive the `v2.35.0` placeholder. If the changelog is missing or Python unavailable, it falls back to `v2.10.0`.

## Removing Optional Features

Not every project needs every integration. See [`docs/guides/OPTIONAL-FEATURES.md`](docs/guides/OPTIONAL-FEATURES.md) for removal checklists covering:
- **Stripe/Payment** patterns (if your project doesn't process payments)
- **Confluence** integration (if you use a different documentation platform)
- **RLS/PostgreSQL** patterns (if you use a different database)
- **Clerk/Auth** patterns (if you use a different auth provider)

## Post-Setup Checklist

- [ ] Setup wizard completed (or manual placeholders replaced)
- [ ] Reviewed `bootstrap-gap-report.md` and closed any `MISSING` capabilities
- [ ] Confirmed the selected profile in `.active-profile` (default `neutral`)
- [ ] `.env.template` reviewed and updated with your service keys
- [ ] `LICENSE` copyright line updated
- [ ] `.github/FUNDING.yml` updated (or removed if not sponsoring)
- [ ] `CLAUDE.md` technology stack section customized
- [ ] Review [optional features](docs/guides/OPTIONAL-FEATURES.md) and remove integrations you don't need
- [ ] Customize `.claude/team-config.json` for your team structure
- [ ] Linear workspace configured (see `docs/onboarding/`)
- [ ] GitHub repository settings: enable "Template repository" if sharing
- [ ] Run `bash scripts/setup-template.sh --finalize` to remove the wizard and this file

## What's Next?

Setup is complete — now read **[Getting Started](docs/guides/GETTING-STARTED.md)** for the end-to-end workflow: your first agent session, first PR, and optional advanced features.

### Optional: Agent Teams

Enable multi-agent parallel work (requires Claude Code 2.1.0+):

1. Set `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` in your environment
2. Follow the [Agent Teams Guide](docs/onboarding/AGENT-TEAMS-GUIDE.md)

### Optional: Dark Factory (Remote Agent Teams)

Run persistent autonomous agent teams on a remote server via tmux:

1. Set up a remote Linux machine with SSH, tmux, Claude Code, git, and `gh`
2. Configure `~/.dark-factory/env` with your project values
3. Follow the [Dark Factory Guide](dark-factory/docs/DARK-FACTORY-GUIDE.md)

### Adopting into an Existing Project?

If you pulled this harness into a repo that already has code (rather than using
the GitHub template), see the
[Workspace Adoption Guide](docs/guides/WORKSPACE-ADOPTION-GUIDE.md) for
multi-repo strategies and keeping the harness up to date.

### Upgrading an Existing Harness?

If you already have a previous version of the harness and need to update:

```bash
# Check what version you're on
./scripts/sync-claude-harness.sh version

# Preview changes before applying
./scripts/sync-claude-harness.sh sync --dry-run

# Apply the latest release
./scripts/sync-claude-harness.sh sync --latest
```

See [Keeping the Harness Updated](docs/guides/WORKSPACE-ADOPTION-GUIDE.md#keeping-the-harness-updated) for full details on what to update vs. what to preserve.
