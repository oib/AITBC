# Claude Code Harness Setup Guide

## Quick Start (~0 LLM tokens)

This guide installs the SAFe Claude Code harness in a new project. **The default route is a
script — not the LLM.** `scripts/setup-template.sh` replaces every placeholder deterministically
with `sed`, so installation costs ~0 LLM tokens and never asks Claude to hand-edit thousands of
files.

> **Do NOT ask Claude to "search and replace the placeholders" or to "read the docs to learn the
> harness".** Both are token sinks (~19k placeholder occurrences across ~1,500 files; ~33k lines of
> docs/patterns). The wizard does the substitution; the deterministic checks below prove it worked.

---

## Prerequisites

- Claude Code CLI installed (`claude --version`)
- Git repository initialized
- Node.js project with `package.json`
- `jq` installed (`jq --version`) — command-conditioned hooks fail open (silent) without it
- **Windows only:** long paths enabled — `git config --global core.longpaths true`

> **Windows: set `core.longpaths` BEFORE cloning.** Without it, Git for Windows uses the ANSI API
> and any path over 260 chars (MAX_PATH) is **silently skipped at checkout** — the clone reports
> success, the files never land, and `git status` then shows them as deleted. The repo keeps its own
> paths inside a 100-char budget (enforced by `tests/test-path-budget.sh`), but a deep clone parent
> (`C:\Users\...\projects\customer\...`) plus the orchestrator's per-ticket worktrees
> (`.claude/worktrees/<TICKET>-auto/`) can still cross 260 — `core.longpaths` is the only fix that
> covers that. Already cloned? Set the config, then run `git checkout -- .` to materialize the files
> that were dropped.

---

## Path A (Default): Script Route

From the repository root, run the setup wizard:

```bash
# Interactive: prompts for your project values (PROJECT_NAME, TICKET_PREFIX, ...)
bash scripts/setup-template.sh

# Non-interactive: read KEY=VALUE inputs from a file
cp bootstrap.values.template bootstrap.values   # then edit
bash scripts/setup-template.sh --values bootstrap.values --yes
```

The wizard replaces **all** placeholders deterministically via `sed`
(`scripts/setup-template.sh`, substitution loop). It also generates `.harness-manifest.yml`,
selects a profile (`.active-profile`), and emits `bootstrap-gap-report.md`. It is **idempotent** ---
re-running detects already-replaced placeholders and prints "nothing to replace".

See [TEMPLATE_SETUP.md](../TEMPLATE_SETUP.md) for the full flag list (`--profile`, `--allow-gaps`,
`--finalize`) and the placeholder reference.

### Configure hooks (one copy, no UI step)

The workflow hooks (branch/commit reminders, push-to-main blocker, iteration guard, markdown
formatting, evolver lifecycle) ship pre-wired in the `"hooks"` block of
`.claude/settings.template.json`. Claude Code **auto-loads** `.claude/settings.json`, so you just
copy the template:

```bash
cp .claude/settings.template.json .claude/settings.json
```

Then restart / reload Claude Code so the hooks block is picked up. Customize the ticket prefix and
the protected branch name inside the hook commands if the wizard did not already set them.

---

## Validate Installation (deterministic + one smoke)

Installation is proven by **three deterministic checks** plus **exactly one cheap LLM smoke** --- not
by asking Claude to enumerate skills.

```bash
# 1. No placeholders remain (must print nothing)
grep -rlE '\{\{' .claude/ CLAUDE.md

# 2. Every hook command behaves against realistic payloads
bash tests/test-hooks-behavioral.sh

# 3. Harness is in sync with its shipped source (no unexpected drift)
bash scripts/sync-claude-harness.sh sync --dry-run
```

If check 1 prints any file path, run the wizard again (it is idempotent) or fill the listed
placeholder by hand. Checks 2 and 3 must exit clean.

**One LLM smoke** --- the only step that spends a token or two:

```text
/check-workflow
```

Expected: Claude reports the current workflow state. That confirms commands and skills load. There
is **no** "What skills are available?" step --- it pulls ~17k lines of skill/agent/command definitions
into context for no verification value.

---

## On-Demand Documentation (do not bulk-read)

Documentation is an **on-demand reference**, not install-time reading. **Never bulk-read `docs/` or
`patterns_library/`** --- that is ~33k lines of context for zero setup benefit. When you need a
pattern, the `pattern-discovery` skill fetches it in an isolated context; open a specific doc only
when a ticket or skill names it.

Start here when you actually need orientation:

- [AGENTS.md](../AGENTS.md) --- which agent to use when
- [CONTRIBUTING.md](../CONTRIBUTING.md) --- git workflow and commit standards
- [.claude/README.md](README.md) --- harness architecture (hooks, commands, skills)
- [.claude/TROUBLESHOOTING.md](TROUBLESHOOTING.md) --- common issues

---

## Directory Structure

After setup, your `.claude/` directory contains:

```text
.claude/
├── commands/           # 19 slash commands (start-work, pre-pr, end-work, ...)
├── skills/             # 22 model-invoked skills (safe-workflow, pattern-discovery, rls-patterns, ...)
├── agents/             # 17 SAFe agent profiles (bsa, tdm, rte, be-developer, ...)
├── hooks/              # Hook scripts (invoked by settings.json hooks)
├── settings.template.json # Template with the live "hooks" block (copy to settings.json)
├── settings.json       # Auto-loaded by Claude Code (copied from the template)
├── hooks-config.json   # Annotated source-of-record mirror (NOT auto-loaded)
├── README.md           # Harness overview
├── SETUP.md            # This file
└── TROUBLESHOOTING.md  # Common issues
```

---

## Quick Command Reference

| Command                             | Purpose                       |
| ----------------------------------- | ----------------------------- |
| `/start-work AITBC-123` | Begin work on a ticket        |
| `/check-workflow`                   | Check current workflow status |
| `/pre-pr`                           | Run validation before PR      |
| `/end-work`                         | Complete work session         |
| `/local-sync`                       | Sync after git pull           |
| `/remote-status`                    | Check remote Docker status    |

---

## Appendix: Manual Copy Fallback

Only if you cannot run the wizard (e.g. copying the harness into an existing repo by hand). Prefer
Path A --- the manual route reintroduces the token cost this guide removes.

```bash
# From the source repository root, copy into your project:
cp -r .claude/commands/ /path/to/your-project/.claude/commands/
cp -r .claude/skills/   /path/to/your-project/.claude/skills/
cp -r .claude/agents/   /path/to/your-project/.claude/agents/
cp .claude/settings.template.json /path/to/your-project/.claude/settings.json
```

Then replace the placeholders yourself --- see the placeholder table in
[TEMPLATE_SETUP.md](../TEMPLATE_SETUP.md) --- and run the three deterministic checks above. Adopting
into an existing repo is covered by
[docs/guides/WORKSPACE-ADOPTION-GUIDE.md](../docs/guides/WORKSPACE-ADOPTION-GUIDE.md).

---

**Version**: 2.0
**Last Updated**: 2026-07-09
