# Safe-Workflow Skill: On-Demand Branch/Commit/PR Conventions

**Shipped in**: ABS-201 (child of epic ABS-164); ABS-169 handled the CLAUDE.md swap
**Effective from**: harness v2.23.0 (next governor promotion)

---

## What Changed

Before ABS-169 and ABS-201, every obeying agent session loaded CONTRIBUTING.md up front as
a mandatory per-spawn read (24 KB, ~6k tokens). The `safe-workflow` skill already existed with
the full set of branch/commit/PR rules, but nothing pointed agents to use it instead.

ABS-169 swapped the directive in `CLAUDE.md`. ABS-201 mirrors that swap across the agent
definitions and docs guides:

| Surface | Before | After |
|---|---|---|
| `CLAUDE.md` L195 (ABS-169) | MANDATORY: Read CONTRIBUTING.md before any development | invoke the `safe-workflow` skill on demand; CONTRIBUTING.md is the reference |
| `.claude/agents/rte.md` — §5 Review Documentation | `` `CONTRIBUTING.md` — Complete workflow (MANDATORY) `` | Skill invocation reference |
| `.claude/agents/rte.md` — MUST READ section | Same mandatory directive | Skill invocation reference |
| `.claude/agents/tdm.md` — MUST READ | Same mandatory directive | Skill invocation reference |
| `AGENTS.md` — Key Documentation bullet | MANDATORY READ | Skill invocation reference |
| `AGENTS.md` — Quick Start line | Read CONTRIBUTING.md | Skill invocation reference |
| `docs/guides/AGENT_TEAM_GUIDE.md` — 4 locations | MANDATORY / `cat CONTRIBUTING.md` | Skill invocation reference |
| `harness/.claude/agents/tdm.md` (twin) | Same mandatory directive | Byte-identical to `.claude/` copy |

9 swap locations, 5 files (+1 harness twin). Per-spawn saving: ~6k tokens for every rte or tdm
spawn that previously obeyed the full-read directive.

---

## The Replacement Wording

Every swapped directive now reads:

> Branch/commit/PR conventions: invoke the `safe-workflow` skill (loads on demand).
> `CONTRIBUTING.md` is the reference, not a mandatory read.

This wording is identical across all 9 locations, matching the ABS-169 CLAUDE.md swap (commit
`b506ada`).

---

## The 5 Load-Bearing Rules

No rule was removed. All 5 remain reachable in `.claude/skills/safe-workflow/SKILL.md`
(unchanged by ABS-201):

| Rule | Location in SKILL.md |
|---|---|
| Branch naming: `AITBC-{number}-{short-description}` | L27 |
| Commit format: `type(scope): description [AITBC-XXX]` | L55 |
| Rebase-first workflow | L90 |
| "Rebase and merge" strategy only | L120 |
| Pre-PR CI validation checklist | L129 |

The skill is the canonical load point for these rules. CONTRIBUTING.md remains the human-readable
reference document and retains its full content unchanged.

---

## How Agents Invoke the Skill

Agents invoke the skill on demand when branch naming, commit format, or PR workflow guidance is
needed — not at session start as a blanket full-read:

```text
[invoke safe-workflow skill]
```

The skill runs as a standard skill invocation (not a fork — `context: main`). It surfaces
the relevant rule sections rather than requiring the agent to scan CONTRIBUTING.md.

---

## Scope Boundary

`agent_providers/claude_code/prompts/{rte,tdm}.md` still carry the old directive. They are
outside the BSA-declared scope for ABS-201 and are not an ALLOWED_DOMAIN in
`scripts/sync-claude-harness.sh`, so they were left unchanged (YAGNI). A future story may
sweep the provider prompts for consistency.

---

## Harness Twin Sync

`harness/.claude/agents/tdm.md` is byte-identical to `.claude/agents/tdm.md` (same git blob
hash). `harness/.claude/agents/rte.md` was NOT updated in the ABS-201 commit due to pre-existing
drift introduced by ABS-171 (a prior story that edited the harness copy but not the `.claude/`
copy); that pre-existing drift is outside this story's scope. The sync `--dry-run` shows no NEW
drift from ABS-201's changes.

---

## Governance References

- `.claude/skills/safe-workflow/SKILL.md` — skill definition with all 5 load-bearing rules
- `.claude/skills/safe-workflow/README.md` — skill overview and trigger keywords
- `CONTRIBUTING.md` — full contributor guide (reference, not mandatory per-spawn read)
- `docs/agent-outputs/qa-validations/ABS-201-qa-validation.md` — QAS verification report
- ABS-169 commit `b506ada` — CLAUDE.md swap (companion change)
- `adrs/agentic/ADR-A-0003-context-minimization.md` — context minimization as a workflow quality requirement
