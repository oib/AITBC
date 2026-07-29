---
id: ADR-A-0016
title: Apply path for .claude / harness agent-def deliverables under permission-mode dontAsk
status: proposed           # accepted when a human merges this ADR's PR (adrs/README.md)
scope: agentic
date: "2026-07-10"
---

## Context

Claude Code hard-denies writes to any directory named `.claude` when a headless seat runs under
`--permission-mode dontAsk`. A probe-spawn in a worktree (recorded on ABS-170/171/172) confirmed
that Write, Edit, and `Bash cp` targeting `harness/.claude/agents/*.md` were all DENIED, even with
explicit allowlist entries (`Write(harness/**)`, `Write(.claude/**)`) and a bare `Write` allow;
`docs/` targets under the same run were ALLOWED. The protection keys on the `.claude` path
segment, not on the allowlist.

The effect: every ticket whose deliverable was an edit to the agent-def source under
`harness/.claude/**` (the three slimming seats ABS-173, ABS-174, ABS-168) could not finish in a
seat. Each correctly escalated to Blocked, and a human operator applied the finished draft by hand
(`cp` into place, `generate-governor.sh --providers`, the byte-parity test, then a commit). That
per-ticket operator-apply cost recurs for the whole class of agent-def / harness deliverables.

Three options were on the table (ABS-196):

1. **Scoped `--permission-mode bypassPermissions` for worktree spawns.** Worktree isolation as the
   only guardrail.
2. **Move the agent-def source out of the `.claude`-named path** into an unprotected path, with
   `generate-governor.sh` mapping it to the provider mirror and the live `.claude/`.
3. **Formalize an Operator-Apply SOP station** — the seat drafts into `tmp/`, a human applies.

## Decision

Adopt **Option 2**. The shipped agent-def / harness source lives at **`harness/claude/`** (no
leading dot), an ordinary repo path a seat can write under `dontAsk`. The `.claude`-named tree
stays a *generated artifact*, never a hand-edited source.

This is already implemented and merged: commit `d37fad5`
("refactor(harness): rename harness/.claude to harness/claude (headless-editable source)") moved
the whole tree repo-wide, and `harness/.claude/` no longer exists. This ADR records the decision
that the code already carries.

**Apply path a seat follows for an agent-def / harness edit (no operator-apply):**

1. Edit the source under `harness/claude/**` — writable under `dontAsk`.
2. Run `scripts/generate-governor.sh --providers` — regenerates
   `agent_providers/claude_code/` (prompts/hooks/permissions), an ordinary writable path.
3. Commit both. `generate-governor.sh --providers --check` is the byte-parity guard (ADR-A-0015).

The live `.claude/` is **not** touched per ticket. It is `generated(pin)` from the release tag in
`.governor-tag` and is refreshed only at governor promotion (`scripts/promote-release.sh`,
ABS-94/95) — a release step, not seat work. So no seat ever needs to write the protected
`.claude/` path.

**Options 1 and 3 rejected.**

- Option 1 weakens a permission boundary for all worktree work to solve one deliverable class;
  the security regression is disproportionate and would need a standing security sign-off. The
  boundary stays intact.
- Option 3 keeps a per-ticket human-in-the-loop cost for the whole class — the exact friction this
  ticket removes. It remains available only as a fallback when a deliverable genuinely must land in
  a `.claude`-named path (none currently do, since the source moved).

## Consequences

- Agent-def / harness tickets complete end-to-end in a seat under `dontAsk`: edit `harness/claude`,
  regenerate the provider mirror, commit. No operator-apply.
- `harness/claude/**` diverges freely as inert work product; parity is enforced against
  `agent_providers/claude_code/` by `--providers --check` and against the pinned live `.claude/`
  by `tests/test-harness-parity.sh` (unchanged by this ADR).
- The three Wave-2 tickets that paid the manual operator-apply cost — **ABS-173, ABS-174,
  ABS-168** (all Done) — are the last of that class to need it; future ones follow the apply path
  above. Related evidence: ABS-170/171/172 (probe + operator-apply records), ABS-154 (worktree
  allowlist), epic ABS-164.
- AC2 (a `.claude`-class editing ticket runs live without operator-apply) is demonstrated by this
  ticket itself: the seat edited `harness/claude/README.md` (the apply-path note) and committed it
  under `dontAsk` with no operator step.

## Related decisions

**ADR-A-0008, Amendment 2026-07-14 (ABS-248) — harness surface in the ownership map.** This ADR makes
`harness/claude/` the **seat-edit source**. It does *not* make it the migration source: consumers have
a `.claude/` directory and **no `harness/` directory**, and the pinned live `.claude/` at a release tag
is the promoted, governor-generated artifact. The migration ownership map therefore maps **`.claude/`**,
never `harness/claude/`. Repointing the map at `harness/claude/` would break every consumer — see
ADR-A-0008 Amendment 2026-07-14, Q1.
