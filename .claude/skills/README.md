# AITBC Skills

These skills are part of the **AITBC™** multi-agent harness.

## License

**License:** MIT (see [/LICENSE](/LICENSE))
**Copyright:** © 2026 J. Scott Graham ([@cheddarfox](https://github.com/cheddarfox)) / [ByBren, LLC](https://github.com/bybren-llc)
**Attribution:** Required per [/NOTICE](/NOTICE)

## Intellectual Property

The skill system architecture and AITBC harness methodology are the intellectual property of J. Scott Graham and ByBren, LLC.

SAFe® is a registered trademark of Scaled Agile, Inc.

## Skills Included

| Skill | Purpose |
|-------|---------|
| safe-workflow | Branch naming, commits, PR workflow |
| release-patterns | PR creation, CI/CD validation |
| pattern-discovery | Search patterns before implementing |
| agent-coordination | Agent assignment, blockers |
| rls-patterns | Row Level Security enforcement |
| spec-creation | Specs with acceptance criteria |
| orchestration-patterns | Multi-step task orchestration |
| testing-patterns | Jest and Playwright patterns |
| security-audit | RLS validation, vulnerability scanning |
| duplicate-detection | Mandatory dedup gate for ticket creation |
| issue-enrichment | Agent-ready ticket formatting and guardrails |
| jira-sop | Jira ticket management via Atlassian MCP |
| linear-sop | Linear ticket management |
| migration-patterns | Database migrations with RLS |
| frontend-patterns | Next.js, Clerk, shadcn/ui |
| api-patterns | API routes with Zod validation |
| git-advanced | Rebase, bisect, cherry-pick |
| stripe-patterns | Payment integration, webhooks |
| deployment-sop | Deployment workflows |
| confluence-docs | ADRs, runbooks, docs |
| team-coordination | Agent Teams orchestration (experimental) |
| ponytail | Minimal-change discipline for coding agents — YAGNI, shortest path, reuse-first (ADR-A-0010) |

## Creating New Skills

See [/docs/guides/SKILL_AUTHORING_GUIDE.md](/docs/guides/SKILL_AUTHORING_GUIDE.md).

## Adding a New Skill — Propagation Checklist

This directory (`.claude/skills/`) is the **canonical source** for all skills. When adding a new skill:

1. **Create in `.claude/skills/`** — Add your skill with SKILL.md and README.md
2. **Copy to `.agents/skills/`** — For agentic CLI: copy skill dir, include SKILL.md only (no README.md, no assets)
3. **Copy to `.gemini/skills/`** — For Gemini CLI: copy skill dir, include SKILL.md + create README.md following the template below
4. **CI verification** — Run `.github/workflows/pr-validation.yml` skill parity check locally before pushing

### README.md Template for `.gemini/skills/`

```markdown
# [Skill Name]

![Status](https://img.shields.io/badge/status-production-green)
![Harness](https://img.shields.io/badge/harness-v2.35.0-blue)
![Provider](https://img.shields.io/badge/provider-Gemini_CLI-orange)

> [One-line description from SKILL.md frontmatter]

## Quick Start

[Copy from SKILL.md "When to Use" section, adapting trigger keywords]

## What This Skill Does

[Copy from SKILL.md "Purpose" section]

## Provider Compatibility

| Provider | Status |
|----------|--------|
| Gemini CLI | ✅ Native |
| Claude Code | ✅ Equivalent skill in `.claude/skills/` |

## Related Skills

[List 2-3 related skills with links]

## Maintenance

| Field | Value |
|-------|-------|
| Last Updated | [YYYY-MM-DD] |
| Harness Version | v2.35.0 |

---

*Full implementation details in [SKILL.md](SKILL.md)*
```

### Provider-Specific Notes

- **`.agents/skills/`** — Minimal: SKILL.md only. May include `assets/`, `references/`, `scripts/` subdirs if present in source.
- **`.gemini/skills/`** — Always include README.md with provider badge and consistent structure.
- **`.claude/skills/`** — Full skill with README.md (can be verbose) and optional assets/subdirs.
