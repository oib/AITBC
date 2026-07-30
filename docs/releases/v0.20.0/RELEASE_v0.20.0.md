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
- Shipped harness source:
  - `harness/devin/skills/` — 32 skills
  - `harness/devin/agents/` — 18 agent profiles
- Generated consumer trees:
  - `.devin/skills/` — 32 skills
  - `.devin/agents/` — 18 agent profiles
- New `scripts/sync-devin-harness.sh` regenerates `.devin/` from the shipped `harness/devin/` tree (falling back to `harness/claude/` or `.claude/` when no Devin harness has been published).

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
- `harness/devin/skills/*`
- `harness/devin/agents/*`
- `.devin/skills/*`
- `.devin/agents/*`
- `tests/test-spawn-devin.sh`
- `docs/releases/v0.20.0/AGENTS.md`
- `docs/releases/v0.20.0/RELEASE_v0.20.0.md`

### 5. Provider-seam parity fixes found by testing the adapter

The first cut of the adapter launched Devin correctly but silently dropped several load-bearing parts of the §3.1 seam contract that the Claude binding implements. All are now fixed and covered by `tests/test-spawn-devin.sh` (20 assertions).

| Gap | Impact | Fix |
|-----|--------|-----|
| `_common-rules.md` was never prepended (ABS-174) | Every Devin seat ran without the cross-seat rules all Claude seats receive, including evidence discipline and the anti-slop gate | Compose `commons -> role def -> overlay` |
| `ORCH_TOOLS` was ignored (ABS-57) | The In Review seat reuses the write-capable `system-architect` role; it could edit the code it was reviewing | A write-free `ORCH_TOOLS` override now forces `--permission-mode auto` |
| `ORCH_TARGET_REPO` was ignored (ABS-92) | In the self-hosting lane the seat ran in the wrong repo | cwd is `ORCH_SPAWN_CWD`, else `ORCH_TARGET_REPO`, and a failed `cd` is fatal |
| `ORCH_OVERRIDES_DIR` overlay was ignored (ABS-258) | A project could not refine an agent def without forking it | `<role>.append.md` is appended after the role body |
| Underscore roles were spawnable (ABS-174) | A stray role label could resolve `_common-rules` as an agent | Underscore-prefixed roles are rejected |
| `opus`/`sonnet` were pinned to `claude-opus-4.6`/`claude-sonnet-4` | Silent model downgrade: Devin resolves `opus` to the current Opus family, so the mapping moved seats to an older model | Aliases pass through untouched |

### 6. Verified Devin CLI behaviour relied on by the adapter

Measured against Devin CLI 3000.3.22, because the enforcement choice depends on it:

- `--permission-mode auto` in `-p` mode **does** block a write: the call is rejected with `rejected a tool call that requires confirmation` and the file is not created. This is the mechanical read-only gate for QAS / Security Engineer / write-free `ORCH_TOOLS` seats.
- `--agent-config` with `allowed-tools: [read, grep, glob]` **did not** block the `write` tool — the file was created. Same for `permissions.deny: ["write", "edit"]` and `permissions.deny: ["Write(**)"]`.
- Therefore read-only enforcement uses the permission mode only, never an `--agent-config` allowlist.
- `--agent-config` accepts exactly `system-instructions`, `allowed-tools`, `permissions`, `mcp-servers`, `extensions` (unknown fields are rejected).
- Devin has no `--max-turns` equivalent, so the `ORCH_MAX_TURNS` ceiling (ABS-150) is not enforceable as a turn cap. The runner already enforces `ORCH_AGENT_TIMEOUT`/`ORCH_AGENT_MAX_LIFETIME` as a wall-clock watchdog; the Devin adapter now additionally wraps `devin` in `timeout(1)`/`gtimeout(1)` when those values are exported, providing a last-resort SIGTERM/SIGKILL bound.

## Known Issues

- `ORCH_MAX_TURNS` (ABS-150) has no Devin equivalent, so a runaway Devin seat is not capped by a turn count. The runner's wall-clock `ORCH_AGENT_TIMEOUT` and the adapter's `timeout(1)` wrapper bound total runtime, but not the number of turns.
- `--agent-config` tool restrictions are not enforced by Devin CLI 3000.3.22 (see section 6). If a future release fixes this, the adapter should additionally pass an allowlist so a read-only seat is narrowed at the tool level, not only by permission mode.
- A single seat has been spawned end-to-end against the live CLI (it composed the commons, produced a `## Handoff` record, and correctly refused an unverifiable request). A full multi-stage epic has not yet been burned on this provider.
- `CLAUDE.md` has uncommitted working-tree modifications.
- `work/.gitea-events-state.current.*` temp files remain untracked.

## Verification

```bash
bash tests/test-spawn-devin.sh          # 20/20 provider-seam contract assertions
bash tests/test-spawn-tmpdir.sh         # Claude seam unaffected
bash tests/test-spawn-skill-path.sh     # Claude seam unaffected
bash scripts/sync-devin-harness.sh
bash -n scripts/orchestrator-spawn-devin.sh
bash -n scripts/sync-devin-harness.sh
python3 -m py_compile scripts/mirror-claude-to-devin.py
./venv/bin/python -m ruff check .
```

---

*Generated with [Devin](https://devin.ai)*
