---
type: index
resource: knowledge/
timestamp: 2026-07-03
---

# Knowledge index

<!-- One line per concept: - [name](name.md) — hook. Agents read this file first (level 1 of
     the mandatory context sequence) and open only the concept that owns their question. -->

- [capabilities-and-profiles](capabilities-and-profiles.md) — Which of the 10 neutral
  capabilities exist, and how a profile binds one to a concrete provider?
- [ticket-lifecycle-and-statuses](ticket-lifecycle-and-statuses.md) — What are the 26 canonical
  ticket statuses (10 v1 core + 16 v3 workflow), what triggers on each transition, and what must
  a ticket contain before it's ready for development?
- [harness-sync-and-manifest](harness-sync-and-manifest.md) — How does a fork keep its
  `.claude/`/`.gemini/`/`.codex/`/`.cursor/` harness in sync with upstream without losing local
  customizations?
- [agent-roster-and-gates](agent-roster-and-gates.md) — Who are the 17 agents, what's the
  standard gate chain from spec to merge, and which roles can never be collapsed into an
  implementer?
- [loop-termination](loop-termination.md) — How is a QAS/QAS-Design bounce loop classified,
  capped, and mechanically stopped from looping forever?
- [approval-boundaries](approval-boundaries.md) — Which decisions (including credential
  provisioning) are human-only no matter how much autonomy an agent has, and how is each one
  enforced?
- [bootstrap-flow](bootstrap-flow.md) — What does the setup wizard actually do today versus the
  three-mode bootstrap the blueprint describes, and what's the known gap?
- [evolution-loop](evolution-loop.md) — How does the opt-in Evolver profile feed the
  Self-Improvement Agent without becoming a second self-improvement mechanism?
- [orchestrator-hardening-abs-111](orchestrator-hardening-abs-111.md) — How do the ABS-111
  orchestrator seams work (async spawns, session resume until acceptance, depends_on/worktree
  gates, per-seat overrides, the run.log event stream) and which env var disables each?
