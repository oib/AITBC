# First Live Orchestrator Run — Evidence (ABS-30 / ABS-58)

**Date**: 2026-07-04
**Operator**: human (Raphael Sahann) + coordinating agent
**Environment**: macOS (Darwin 25.5.0), bash 3.2, Claude Code CLI 2.1.201 (npm), keychain credentials
**Mode**: `scripts/orchestrator.sh --live`, `ORCH_MAX_SPAWNS_PER_RUN=6`, `ORCH_POLL_INTERVAL=15`, `ORCH_NOTIFY_TICKET=LIVE-1`, mock tracker adapter
**Ticket**: `LIVE-1` — "Live smoke: create live-run marker doc" (`--role be-developer`, agent-ready body with per-role lifecycle protocol)

## Result

**PASS.** Full gate walk driven by tracker events with zero human agent-invocation:

```text
Ready for Development -> In Progress -> In Review -> In Test -> Ready for Human Acceptance
        be-developer       (self)     system-architect   qas         po-agent (SPAWN-then-NOTIFY)
```

Runner intent log (attempt 2):

```text
INTENT SPAWN   ticket=LIVE-1 role=be-developer     to=Ready for Development
INTENT HANDOFF ticket=LIVE-1 role=be-developer     to=Ready for Development
INTENT SPAWN   ticket=LIVE-1 role=system-architect to=In Review
INTENT HANDOFF ticket=LIVE-1 role=system-architect to=In Review
INTENT SPAWN   ticket=LIVE-1 role=qas              to=In Test
INTENT HANDOFF ticket=LIVE-1 role=qas              to=In Test
INTENT SPAWN   ticket=LIVE-1 role=po-agent         to=Ready for Human Acceptance
INTENT HANDOFF ticket=LIVE-1 role=po-agent         to=Ready for Human Acceptance
INTENT NOTIFY  ticket=LIVE-1 role=- to=- note=po-agent check complete for LIVE-1 (Ready for Human Acceptance)
orchestrator: kill-switch present (...); finishing, no new spawns; exit 0
```

Verified behaviors:

- **Fresh subagent per gate** (ADR-A-0002): 4 spawns, each with a minimal context packet; every spawn returned a parseable `## Handoff` record that the runner posted back as a `kind: handoff` comment.
- **Agents drive the status machine themselves**: be-developer transitioned `Ready for Development -> In Progress -> In Review`; system-architect (read-only toolset via ABS-57 `ORCH_REVIEW_TOOLS`) approved to `In Test`; qas approved to `Ready for Human Acceptance`; po-agent stopped there (human boundary, ADR-A-0004) and the runner emitted the human NOTIFY.
- **Deliverable + evidence**: `docs/agent-outputs/live-runs/LIVE-1-marker.md` created verbatim; all 3 acceptance criteria re-verified independently at each gate (`gate-results` comments from system-architect and qas on the ticket).
- **Kill switch**: clean exit at the cycle boundary, no new spawns.
- **Cost posture** (ADR-A-0009): budget capped at 6 spawns; 4 consumed; wall time ≈ 3.5 minutes for the whole walk.
- **Permissions**: spawns ran `--permission-mode dontAsk` against a machine-local `.claude/settings.local.json` allowlist (scoped writes under `docs/agent-outputs/`, mock-tracker script, read-only git). No permission denial blocked the walk.

## Failure found and fixed: ABS-58 (attempt 1)

Attempt 1 failed before any model call: every spawn exited `Not logged in · Please run /login` in <1s. Root cause: the spawn seam passed `--bare`, which per `claude --help` skips **keychain reads** — on macOS that is exactly where the CLI's OAuth credentials live. A plain `claude -p` on the same machine worked.

By-product verification of spec §6 failure handling: the runner retried once, escalated (`INTENT ESCALATE-BLOCKED`), posted an explanatory `handoff` comment, and transitioned the ticket to `Blocked`; the kill switch then stopped the loop cleanly.

Fix (`scripts/orchestrator-spawn-claude.sh`): `--bare` removed from the default invocation, opt-in via `ORCH_CLAUDE_BARE=1` for file/env-credential environments. Spec §3.2 updated. Tracked as ABS-58.

## Follow-up observations (non-blocking)

- The background wrapper reported process exit code 10 after the kill-switch path, while the runner logs `exit 0` — cosmetic discrepancy, worth a look if exit codes are ever scripted against.
- `LIVE-1` mock-tracker state (`work/tickets/LIVE-1.md`) is deliberately left uncommitted (machine-local run state, per ABS-40 hygiene).
