# AITBC v0.20.0 Release Notes

**Date**: 2026-07-30
**Status**: Complete
**Scope**: Devin CLI boilerplate support
**Baseline**: v0.19.0 (commit `9c0d2d8da`)
**Tickets**: AITBC-65 (code review epic), AITBC-61 (project skills)

## Overview

v0.20.0 is a harness-only release that makes the SAFe Agentic Workflow (SAW) v2.35.0 boilerplate runnable through the Devin CLI. No application code is changed; the release adds the provider adapter, a `.devin/` skills and agents mirror, and a sync script.

## Major Changes

### 1. Devin CLI spawn adapter

- New `scripts/orchestrator-spawn-devin.sh` implements the §3.1 provider seam contract.
- Reads the same `.claude/agents/<role>.md` definitions as the Claude adapter.
- Maps `ORCH_MODEL` to Devin model names (`sonnet` → `claude-sonnet-4`, `opus` → `claude-opus-4.6`, `codex` → `codex`).
- Sets role-aware Devin permission mode:
  - `qas`, `qas-design`, `security-engineer` → `auto` (read-only)
  - all other seats → `accept-edits` (can edit workspace)
- Falls back to `ORCH_DEVIN_MODEL` and `ORCH_DEVIN_PERMISSION_MODE` for operator overrides.
- Uses `devin -p --prompt-file` with workspace trust disabled for non-interactive headless spawns.

### 2. `.devin/` skills and agents mirror

- New `scripts/mirror-claude-to-devin.py` converts `.claude/skills/` and `.claude/agents/` to the Devin CLI frontmatter format:
  - `allowed-tools` becomes a lowercase list of Devin tool names (`read`, `exec`, `grep`, `glob`, `write`, `edit`, `todo_write`, `mcp_call_tool`, etc.)
  - `tools` in agent defs becomes `allowed-tools`
  - `context`/`agent` are normalized; `agent: Explore` becomes `subagent: true`
  - `model` is mapped to Devin model names
  - References to `harness/claude/skills/`, `.claude/skills/`, `harness/claude/agents/`, and `.claude/agents/` are rewritten to `.devin/skills/` and `.devin/agents/`
- Generated trees:
  - `.devin/skills/` — 32 skills
  - `.devin/agents/` — 18 agent profiles
- New `scripts/sync-devin-harness.sh` regenerates `.devin/` from the live `.claude/` tree (or the shipped `harness/claude/` tree when `.claude/` has not yet been generated).

### 3. Orchestrator default provider detection

- `scripts/orchestrator.sh` now defaults to `orchestrator-spawn-devin.sh` when `devin` is on `PATH`.
- `claude` is still used when `devin` is absent.
- Explicit `ORCH_SPAWN_CMD` always wins, preserving test stubs and manual overrides.

### 4. `.devin/config.json`

- Project-level Devin config already shipped in v0.19.0; it imports `.claude/`, `.cursor/`, and `.windsurf/` rules and always-on context.

## Files Added or Modified

- `scripts/orchestrator-spawn-devin.sh`
- `scripts/mirror-claude-to-devin.py`
- `scripts/sync-devin-harness.sh`
- `scripts/orchestrator.sh`
- `.devin/skills/*`
- `.devin/agents/*`
- `docs/releases/v0.20.0/AGENTS.md`
- `docs/releases/v0.20.0/RELEASE_v0.20.0.md`

## Known Issues

- `CLAUDE.md` has uncommitted working-tree modifications.
- `work/.gitea-events-state.current.*` temp files remain untracked.
- The Devin seat has been syntax- and command-validated but not yet live-burned through a full ticket lifecycle on this provider.

## Verification

```bash
bash scripts/sync-devin-harness.sh
bash -n scripts/orchestrator-spawn-devin.sh
bash -n scripts/sync-devin-harness.sh
python3 -m py_compile scripts/mirror-claude-to-devin.py
./venv/bin/python -m ruff check .
```

---

*Generated with [Devin](https://devin.ai)*
