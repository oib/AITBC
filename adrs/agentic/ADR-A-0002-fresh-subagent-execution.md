---
id: ADR-A-0002
title: Every task runs in a fresh task-scoped subagent
status: proposed
scope: agentic
date: "2026-07-02"
---

## Context

Long-running agents accumulate hidden context: state that exists only in a context window,
invisible to humans and unrecoverable after interruption. That state rots, bloats token usage,
and makes work non-resumable and non-auditable.

## Decision

We will execute every task — ticket, subtask, code review, test task, documentation task,
migration task, follow-up extraction, duplicate detection, quality-gate investigation — in a
fresh, disposable subagent with a clean context window, fed a minimal context packet
(`.agentic/schemas/context-packet.schema.json`). Only the Coordinator spawns subagents. Every
subagent writes a handoff record before terminating. No long-running hidden agent context may be
required to understand project state; durable state lives in tickets, ADRs, PRs, handoff
records, and audit-relevant repository files.

## Consequences

All project state is inspectable and resumable by construction (the resumability invariant,
`.agentic/handoff/README.md`). Cost: packet assembly and handoff writing overhead per task —
accepted as the price of auditability. Poor handoffs surface immediately as failed resumes and
are tracked as workflow defects.

## Amendment 2026-07-06 (ABS-111)

"Fresh subagent per task" is precise about the **task boundary**: a task ends at its
**acceptance**, not at each intermediate agent reply. Within one task, resuming the SAME
underlying session is conformant and is now implemented in the orchestrator
(`scripts/orchestrator.sh`, seam in `scripts/orchestrator-spawn-claude.sh`):

- **Rework bounces** (e.g. `Story Acceptance -> Ready for Development`, an `In Review` /
  `In Test` re-review) resume the stored session for the same `(ticket, role, status)` — the
  agent continues with warm context instead of paying a cold restart.
- **Handoff repair** — a spawn that exited cleanly but emitted no parseable handoff resumes the
  same session with a tiny (4-turn) budget to re-emit only the handoff block.
- **Retries after a failed attempt are always FRESH.** Resuming a session that just failed or
  timed out would only repeat the failure mode.

**The task boundary is acceptance.** Entering `Merging`/`Done` (acceptance passed) deletes all
stored sessions for the ticket (`clear_sessions`); every spawn after that is fresh. The default
is on; `ORCH_SESSION_RESUME=0` restores strictly-fresh-per-spawn behavior.

**Rationale.** The original decision optimized for auditability and resumability, not for paying a
context cold-start on every single bounce. Live-run-1 evidence
(`docs/agent-outputs/live-runs/ABS-102-run1-pause-state.md`) showed cold restarts on
implement↔review↔accept bounces as a real cost and latency sink. The invariants this ADR protects
are unharmed: durable state still lives in tickets/handoffs (a resumed session still writes a
handoff comment), and there is **no context bleed across task boundaries** because sessions are
deleted at acceptance — a later, unrelated task on the same ticket can never inherit a prior
task's window. Only Coordinator-driven spawns resume; agents never spawn or resume each other.

## Related Decisions

- **ADR-A-0023 — Session invalidation gates on session-baked inputs** (ABS-254). Constrains *when
  a stored session must be discarded* before the resume triggers above may fire: the config
  generation hashes only inputs a resume freezes (runner, spawn seam, agent defs — not the live
  permission surface), and a session whose spawn hit a permission denial is not stored at all.
