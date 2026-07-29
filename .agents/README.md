# Antigravity Configuration

This directory contains the configuration for [Google Antigravity](https://antigravity.google/), Google's agentic IDE. It is also the repo's **provider-neutral canonical skills directory**: `.agents/skills/` is shared by Antigravity, Codex CLI, and any other tool that supports the `.agents/` convention.

## Quick Start

1. **Install Antigravity**

   Download from [antigravity.google](https://antigravity.google/) and sign in with your Google account.

2. **Copy this directory into your project**
   ```bash
   cp -r .agents/ /your-project/.agents/
   ```

3. **Open the project in Antigravity**

   That's it. Antigravity automatically discovers `AGENTS.md` at the repo root, skills from `.agents/skills/`, rules from `.agents/rules/`, and workflows from `.agents/workflows/`. No additional configuration is needed.

## How Antigravity Discovers Context

| Source | Path | Purpose |
|--------|------|---------|
| System instructions | `AGENTS.md` (repo root) | Agent roles, SAFe workflow, pattern discovery protocol |
| Skills | `.agents/skills/*/SKILL.md` | Domain knowledge, auto-loaded when relevant (18 skills) |
| Rules | `.agents/rules/*.md` | Standing guidance applied to agent behavior (7 rules) |
| Workflows | `.agents/workflows/*.md` | Reusable step-by-step procedures invoked on demand (5 workflows) |

There is **no** Antigravity-specific instructions file. Antigravity reads the same `AGENTS.md` used by Codex CLI and the rest of the SAFe harness.

See the official [Rules and Workflows documentation](https://antigravity.google/docs/rules-workflows) for details.

## Directory Structure

```
.agents/
├── README.md           # This file - setup guide
├── rules/              # 7 stack-independent rules (plain markdown)
│   ├── 00-core-principles.md
│   ├── 01-git-workflow.md
│   ├── 02-pattern-discovery.md
│   ├── 20-agent-architect.md
│   ├── 21-agent-backend.md
│   ├── 22-agent-qas.md
│   └── 23-agent-security.md
├── workflows/          # 5 core SAFe workflow procedures
│   ├── start-work.md
│   ├── pre-pr.md
│   ├── end-work.md
│   ├── check-workflow.md
│   └── update-docs.md
└── skills/             # 18 shared skills (provider-neutral canonical location)
    ├── safe-workflow/
    │   └── SKILL.md
    ├── pattern-discovery/
    │   └── SKILL.md
    └── ... (18 total, each with SKILL.md + optional scripts/references/assets)
```

## Rules

Rules are plain markdown files that provide standing guidance. The set here mirrors the stack-independent Cursor rules (`.cursor/rules/00-02, 20-23`):

| Rule | Purpose |
|------|---------|
| `00-core-principles` | SAFe methodology, round-table philosophy, quality gates |
| `01-git-workflow` | Branch naming, commit format, rebase-first workflow |
| `02-pattern-discovery` | Mandatory pattern discovery before implementation |
| `20-agent-architect` | System Architect role: pattern validation, Stage 1 review |
| `21-agent-backend` | Backend Developer role: API implementation, RLS enforcement |
| `22-agent-qas` | QAS role: independent gate owner, AC verification |
| `23-agent-security` | Security Engineer role: OWASP, RLS audits, zero tolerance |

Stack-specific rules (Cursor rules `10-16`) are **not** ported here — that content belongs to the `saw-stack` profile and reaches Antigravity through the auto-loaded skills instead.

## Workflows

Workflows are step-by-step procedures Antigravity can execute on demand. They port the core `.claude/commands/` workflow commands:

| Workflow | Purpose |
|----------|---------|
| `start-work` | Start work on a ticket: AC/DoD gate, branch creation |
| `pre-pr` | Full validation checklist before creating a PR |
| `end-work` | Complete a work session: commit, document, update ticket |
| `check-workflow` | Quick traffic-light health check of workflow state |
| `update-docs` | Identify and update documentation affected by current work |

## Skills

`.agents/skills/` is the **intended provider-neutral source** for this repo's skills: it is discovered directly by Antigravity and Codex CLI, and treat it as the place to author skill content. The parallel copies under `.claude/skills/` and `.gemini/skills/` are **hand-maintained per provider** — no script generates or byte-syncs them within this repo, and they currently drift from `.agents/skills/` (the upstream sync engine, `sync-claude-harness.sh`, pulls skills *into* a consuming project; it does not materialise these mirrors here). When you change a skill, update every copy that carries it. De-forking the three copies behind a single generator is tracked separately and is out of scope here (ADR-A-0015 — no new sync engine).

Each skill follows this structure:

```
.agents/skills/my-skill/
├── SKILL.md           # Required: YAML frontmatter (name, description) + instructions
├── scripts/           # Optional: executable scripts
├── references/        # Optional: reference documentation
└── assets/            # Optional: templates, resources
```

See the skill table in [.codex/README.md](../.codex/README.md#available-skills-18) for the full list of 18 skills.

## Workspace vs. Global Scope

| Scope | Location | Applies To |
|-------|----------|------------|
| Workspace | `AGENTS.md`, `.agents/skills/`, `.agents/rules/`, `.agents/workflows/` | This repository only |
| Global | `~/.gemini/config/skills/` | All projects (personal skills) |

Everything in this repo is workspace-scoped: it travels with the clone and works for every contributor. Use the global scope for personal skills you want available across projects; global rules and workflows are managed through the Antigravity settings UI (see the [official docs](https://antigravity.google/docs/rules-workflows)).

## Relationship to Other AI Tool Configs

This `.agents/` directory works alongside `.claude/`, `.gemini/`, `.codex/`, and `.cursor/` for teams using multiple AI tools:

| Feature | Antigravity | Claude Code | Gemini CLI | Codex CLI | Cursor IDE |
|---------|-------------|-------------|------------|-----------|------------|
| System Instructions | `AGENTS.md` (project root) | `CLAUDE.md` | `GEMINI.md` | `AGENTS.md` (project root) | `.cursor/rules/*.mdc` |
| Skills | `.agents/skills/*/SKILL.md` | `.claude/skills/*/SKILL.md` | `.gemini/skills/*/SKILL.md` | `.agents/skills/*/SKILL.md` | N/A (rules serve as skills) |
| Rules | `.agents/rules/*.md` | N/A (CLAUDE.md) | N/A (GEMINI.md) | N/A (AGENTS.md) | `.cursor/rules/*.mdc` |
| Commands / Workflows | `.agents/workflows/*.md` | `.claude/commands/*.md` | `.gemini/commands/*.toml` | N/A (natural language) | N/A (use `@rule-name`) |

All tools can coexist in the same repository.

## Upstream Sync

This directory is already listed as a sync domain in `.harness-manifest.yml`, so
the multi-domain sync engine (v2.10.0+) covers Antigravity automatically:

```yaml
sync:
  sync_scope:
    - ".claude/"
    - ".agents/"
```

See [Harness Sync Guide](../docs/HARNESS_SYNC_GUIDE.md) for details.

## License

MIT License - See [LICENSE](../LICENSE) for details.

Copyright (c) 2024-2026 J. Scott Graham (@cheddarfox) / ByBren, LLC
