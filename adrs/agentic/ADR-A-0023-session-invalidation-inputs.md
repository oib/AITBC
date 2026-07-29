---
id: ADR-A-0023
title: Session invalidation gates on session-baked inputs, not on the live permission surface
status: proposed
scope: agentic
date: "2026-07-13"
---

## Context

A resumed Claude session (`claude -p --resume <id>`) carries some state from its birth spawn and
re-reads the rest. ABS-117 introduced a **config generation** (`compute_config_generation`,
`scripts/orchestrator.sh`) — a hash stamped onto every stored session; a resume across a
mismatch is refused (fresh is always allowed, ADR-A-0002).

Which inputs belong in that hash has been decided twice, on contradictory premises:

- **ABS-117 (2026-07-06)** hashed `settings.local.json`, on the header-comment claim that "a
  pre-allowlist-fix dev session stayed tracker-denied on every resume while fresh spawns worked".
- **Retro 2026-07-10** removed it again: an allowlist edit cold-started the entire session store.
  Its stated mechanism: "the allowlist is read fresh from the settings files at every spawn — it
  never shapes a stored session's system prompt".

Both cannot be true. Consumer feedback (CSV item 13, epic ABS-245) then reported the symptom that
motivated ABS-117 in the first place: after a workspace-trust/settings fix, seats resumed over
**6+ spawns** still reporting `Read denied` phantom blockers, escalating into demands for blanket
write allowlists. The proposed fix — fingerprint workspace-trust state into the generation, keep
the allowlist out — assumes trust is baked into a session. That assumption was never tested.

**We tested it** (Claude Code CLI, `claude -p`, 2026-07-13):

1. Workspace with `settings.local.json` denying `Bash(echo:*)` → spawn → tool call **denied**
   (`permission_denials: [{tool_name: "Bash", ...}]`), session id retained.
2. Allowlist edited to **allow** `Bash(echo:*)` → **same session resumed** by id → the tool call
   **succeeded**, `permission_denials: []`.
3. `~/.claude.json` holds trust per project path (`hasTrustDialogAccepted`). The test workspace
   has **no entry at all** — yet its headless spawns loaded `settings.local.json` and executed
   Bash normally.

Two facts follow. **The live permission surface is re-read on resume** — a resume is a new OS
process; the retro's mechanism is correct and ABS-117's header comment is a misdiagnosis. And
**workspace trust is not consulted in headless `-p` mode at all** — the only mode the
orchestrator ever spawns.

The 6+ spawn denial loop therefore had a different cause. What a resume *does* carry is the
**conversation transcript**: the agent re-reads its own history of `Read denied` tool errors and
its own conclusion that the environment is broken, and keeps reporting the blocker — after the
permission engine has already been fixed underneath it. The poison is the denial *history*, not
the current config. **No config-input fingerprint can fix that**, because the poisoned session's
config inputs may be identical to a healthy one's.

## Decision

**1. Classify every input, and hash only what a session bakes.**

| Input | Class | In the generation? |
|---|---|---|
| `settings.local.json` permissions / allowlist | spawn-fresh (proven: step 2) | **No** — retro 2026-07-10 upheld |
| Workspace trust (`~/.claude.json`) | not read in `-p` mode (proven: step 3) | **No** |
| `--permission-mode`, `--allowedTools`, `--model`, `--max-turns` | spawn-fresh (passed on every resume) | No |
| Runner (`orchestrator.sh`) + spawn seam | session-baked (shaped the prompt) | Yes |
| Agent definitions | session-baked (`--agents` omitted on resume) | Yes |
| Conversation transcript | session-baked | n/a — see rule 3 |

The rule: **an input belongs in `compute_config_generation` iff a resume freezes it.** Inputs the
resumed process re-reads must stay out — hashing them buys no correctness and cold-starts the
store for free.

**2. Reject the trust fingerprint (ABS-254 AC2, which was conditional on the design confirming).**
Trust is neither session-baked nor read in headless mode; hashing it would add a dead input, and
would make the generation depend on a per-machine file outside the repo (`~/.claude.json`),
invalidating the store across hosts for reasons unrelated to the runner. `compute_config_generation`
stays as it is.

**3. Invalidate the poisoned sessions instead — precisely, and by the signal we already have.**
The spawn result JSON already reports `permission_denials`. A session whose spawn hit a permission
denial has a transcript that will keep telling it the environment is broken. Therefore: **do not
store a session whose spawn result carried a non-empty `permission_denials` array.** The next
spawn for that `(ticket, role, status)` starts fresh, reads the fixed permission surface, and has
no denial history to inherit. Kill-switch `ORCH_SESSION_POISON_GUARD=0` restores the old
behaviour.

This is the whole fix. It touches the two session-store sites in `attempt_spawn`
(`scripts/orchestrator.sh`), where the full spawn result is already in hand; it changes
`compute_config_generation` not at all.

**4. Correct the ABS-117 header comment** (`scripts/orchestrator.sh`), whose "stayed
tracker-denied on every resume" rationale is now known to be a misdiagnosis and would otherwise
invite the next agent to re-add the allowlist to the hash.

## Consequences

The consumer's actual failure mode — phantom-blocker loops across many spawns — is fixed at its
cause, with a blast radius of exactly the affected sessions. A healthy session store is never
cold-started by a permission edit: the retro's cost concern is preserved, now on a proven
mechanism rather than a contested one.

The cost: a session that hit a *benign* denial (the agent probed something out of scope, was
denied, worked around it, delivered fine) is also dropped, so the next bounce on that seat pays a
cold start instead of a warm resume. This is the accepted trade — fresh is always safe
(ADR-A-0002), a cold start costs tokens, and a phantom-blocker loop cost 6+ spawns and produced a
push for blanket write permissions, which is a security regression.

Two live-observed rationales in the codebase are now settled by test rather than by inference, so
the allowlist question should stop re-opening.

## Related Decisions

- **ADR-A-0002 — Every task runs in a fresh task-scoped subagent.** Owns session-resume policy
  (Amendment 2026-07-06, ABS-111). This ADR constrains *when a stored session must be discarded*;
  it does not change the task boundary or the resume triggers.
- **ADR-A-0010 — Minimal-change default.** The rejected fingerprint would have added a config
  input with no behavioural effect; rule 3 is the smaller change that actually addresses the
  report.

## References

- `scripts/orchestrator.sh` — `compute_config_generation`, `refresh_config_generation`,
  session-store sites in `attempt_spawn`; `SESSION-INVALIDATED` run.log event.
- `scripts/orchestrator-spawn-claude.sh` — `--resume` omits `--agents`; `--permission-mode` /
  `--allowedTools` are passed on every spawn including resumes.
- ABS-117 (config generation), retro 2026-07-10 (allowlist exclusion), ABS-254 (this decision),
  epic ABS-245 / consumer-feedback CSV item 13.
- Reproduction: deny `Bash(echo:*)` in a workspace's `settings.local.json`, spawn `claude -p`
  (denied), flip the rule to `allow`, `--resume` the same session id → the call succeeds.
