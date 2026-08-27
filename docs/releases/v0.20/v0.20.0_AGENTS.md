# AITBC v0.20.0 Release Agent Plan

**Release**: v0.20.0 — Devin CLI boilerplate support
**Status**: Complete
**Tickets**: AITBC-65 (code review epic), AITBC-61 (project skills)
**Baseline**: v0.19.0 (commit `9c0d2d8da`)

## Release Scope

This release is a harness-only, no-application-code change. It makes the SAW v2.35.0 boilerplate compatible with the Devin CLI by:

1. Shipping a Devin CLI spawn adapter for the orchestrator.
2. Generating and maintaining a `.devin/` mirror of the `.claude/` skills and agents.
3. Updating the orchestrator provider default to prefer Devin CLI when it is on `PATH`.

## Agent Assignments

| Role | Responsibility | Evidence |
|------|----------------|----------|
| System Architect | Pattern/ADR validation of the `.devin/` conversion and `orchestrator.sh` default change | No ADR required — the change follows the existing `orchestrator-spawn-cursor.sh` adapter pattern |
| QAS | Verify `scripts/sync-devin-harness.sh` regenerates `.devin/` from `.claude/` and the adapter handoff contract is preserved | `./venv/bin/python -m pytest tests/unit -q` + `bash scripts/sync-devin-harness.sh` |
| RTE | PR shepherd and release notes publication | This release file is committed and pushed to `gitea` |
| HITL | Merge to `main` | Already on `main` via the release-train commit |

## Known Limitations

- The Devin seat is verified to invoke `devin -p --prompt-file` and produce a `## Handoff` record; it has not yet been live-burned through a full epic on this provider.
- MCP tool grants in the Claude agent frontmatter are dropped in the `.devin/agents/` copy because the headless seat already uses `TRACKER_CMD` (`scripts/gitea-tracker.sh`) for all tracker operations.

## Verification

```bash
bash scripts/sync-devin-harness.sh          # regenerates .devin/ without drift
bash -n scripts/orchestrator-spawn-devin.sh
bash -n scripts/sync-devin-harness.sh
python3 -m py_compile scripts/mirror-claude-to-devin.py
./venv/bin/python -m ruff check .             # as before
```
