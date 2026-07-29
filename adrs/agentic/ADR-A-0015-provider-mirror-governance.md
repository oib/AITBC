---
id: ADR-A-0015
title: Provider-mirror governance — one decision per mirror, drift-guarded
status: accepted
scope: agentic
date: "2026-07-08"
accepted_by: Raphael Sahann (POPM)
accepted_date: "2026-07-07"
---

## Context

The boilerplate ships one canonical governance source — `harness/.claude/` (agents, hooks,
skills, settings) — and several *provider mirrors* that adapt it for other tools:
`agent_providers/claude_code/`, `.codex/`, `.gemini/`, and the shared skills under `.agents/skills/`.
These mirrors were hand-maintained with **no generator and no drift guard**, and they rotted:

- `agent_providers/claude_code/prompts/`: 16 of 17 role prompts had drifted from
  `harness/.claude/agents/` (e.g. `tdm.md` pinned `model: sonnet` vs `opus`, missing the
  ADR-A-0003 context-sequence and Agent-Teams sections). `permissions/settings.template.json`
  was an ancient allow-list dump with no `hooks` block.
- `.codex/agents/`: only 11 of the 17 roles present, with no statement of whether that was
  intentional.
- Skills were forked three ways (`.claude/skills/`, `.agents/skills/`, `.gemini/skills/`) while
  `.agents/README.md` claimed `.agents/skills/` was the "canonical … do not fork per provider"
  source — a claim no script enforced.

The only generated pair in the repo — `harness/.claude/` → (`generate-governor.sh`) → `.claude/`
— was in perfect sync precisely because it is generated and drift-guarded. Everything else was
not. ABS-38 ("skills parity", Done) had already regressed. This ADR fixes the *governance model*,
not just the current drift, so it cannot regress silently again.

> **Terminology (added by PILOT-54, 2026-07-26).** The "mirror" governed by this ADR is the
> **provider-config-mirror** — a generated *view of the harness config* (`agent_providers/…`,
> `.codex/`, `.gemini/`) for other agent tools. It is a git-remote-independent concept and must
> not be confused with the other two "mirror" meanings in this repo: the **release mirror**
> (the Bitbucket `origin` remote that receives `main`+tag at release time — ADR-A-0030) and the
> **backend PR-mirror** (the backend's mirrored PR/MR state — ADR-A-0021). Read every "mirror"
> in this ADR as "provider-config-mirror".

## Decision

Every provider mirror gets **exactly one** recorded disposition, and every "kept" mirror gets a
drift guard wired into `scripts/pre-release-check.sh` (a failing guard blocks the release).

**1. `agent_providers/claude_code/` — GENERATED FROM HARNESS.** (POPM decision, 2026-07-07:
regenerate, do not delete.) It is a generated *view* of the working-tree harness source:

| source (`harness/.claude/`)     | mirror (`agent_providers/claude_code/`)   |
|---------------------------------|-------------------------------------------|
| `agents/<role>.md` (≠ README)   | `prompts/<role>.md`                        |
| `hooks/<name>`                  | `hooks/<name>`                             |
| `settings.template.json`        | `permissions/settings.template.json`       |

`scripts/generate-governor.sh --providers` regenerates it; `--providers --check` is a **byte-parity**
guard. The mirror tracks the *working tree* (current dev harness), not the `.governor-tag` pin, so
the mode is tag-independent. `scripts/promote-release.sh` regenerates and stages it at every
governor promotion, so it can never lag the harness. The ~30 doc references that assert
mirror↔harness parity therefore remain true (regenerate keeps them valid; delete would have
required repointing them).

**2. `.codex/agents/` — HAND-ADAPTED, 11-role subset intentional.** Codex CLI carries the
**core delivery** roles only: `be-developer, bsa, data-engineer, data-provisioning-eng,
fe-developer, qas, rte, security-engineer, system-architect, tdm, tech-writer`. The six harness
roles it omits (`boilerplate-migration, issue-enrichment, po-agent, qas-design, self-improvement,
ui-ux-design`) are harness-maintenance / design / orchestration roles not driven from a Codex CLI
seat. `.codex/README.md` documents this subset as intentional; `pre-release-check.sh` enforces
**roster-parity** against the documented list.

**3. Shared skills (`.agents/skills/`, `.claude/skills/`, `.gemini/skills/`) — HAND-ADAPTED,
canonical-claim corrected.** The three copies currently diverge and **no script generates any of
them**; within this repo the upstream sync engine (`sync-claude-harness.sh`) pulls skills *from*
upstream into a consuming project — it does not materialise the mirrors here. The false "canonical
… mirrored … do not fork" claim in `.agents/README.md:90` is rewritten to describe reality:
`.agents/skills/` is the *intended* provider-neutral source, the provider copies are
hand-maintained and may drift, and de-forking them is out of scope for this ADR (no new sync
engine — see guardrail below). No new byte-parity guard is added for skills here; that would
require a generator this ticket is explicitly told not to invent.

**4. `.gemini/` — HAND-ADAPTED, no new guard.** Same disposition as the skills copies; left
hand-maintained, no generator introduced.

## Guardrail

Do **not** invent a new sync engine. The drift guards extend the two existing mechanisms only:
`generate-governor.sh` (generation + `--check`) and `pre-release-check.sh` (release gate).
`tests/test-harness-parity.sh` carries the byte-parity guard's own test.

## Consequences

- `agent_providers/claude_code/` is now byte-identical to the harness and stays that way through
  promotion; a hand edit that skips regeneration fails `pre-release-check.sh`.
- `.codex/` roster changes must update `.codex/README.md` + this ADR + the check together.
- Skills drift is now *documented and acknowledged* rather than falsely claimed as unified;
  closing the fork is a separate, future decision.
