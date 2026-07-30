# AITBC v0.20.4 Release Notes

**Date**: 2026-07-30
**Status**: Complete
**Scope**: Devin harness hardening and drift-guard completion
**Baseline**: v0.20.0
**Tickets**: AITBC-65

## Overview

v0.20.1 through v0.20.4 are harness-only patch releases that stabilize the Devin CLI adapter introduced in v0.20.0. They set the default Devin model, fix skill/agent frontmatter conversion, and complete the drift-guard that keeps `.devin/`, `harness/devin/`, and `.claude/` in sync.

## Changes

### v0.20.1 — Default Devin agent model + frontmatter fixes

- All `.devin/agents/` and `harness/devin/agents/` profiles now default to `swe-1.7-medium`.
- `scripts/mirror-claude-to-devin.py` preserves `subagent`/`context` fields across passes.
- Claude `Skill` references are now mapped to lowercase Devin `skill`.
- Pre-commit hook hardened (`set -euo pipefail`).
- Governor promoted to v0.20.1.

### v0.20.2 — Drift-guard implementation (5 suggestions)

- True Devin-to-Devin passthrough for `harness/devin/` → `.devin/` with `--passthrough` flag.
- Semantic lint via `--lint` (YAML validity, tool/model validity, subagent/skill preservation).
- Bidirectional drift guard for `.claude/` vs `harness/claude/` across skills, agents, commands, hooks, and top-level files.
- Coverage expanded to `commands/`, `hooks/`, `README.md`, `TROUBLESHOOTING.md`, `SETUP.md`, `AGENT_OUTPUT_GUIDE.md`, `hooks-config.json`, `settings.template.json`.
- `_common-rules.md` and underscore-prefixed shared fragments are passthrough-copied in both conversion and passthrough modes.

### v0.20.3 — QAS hardening (TEST-DEVIN-2)

- `mirror-claude-to-devin.py` type-checks frontmatter before linting (prevents crash on non-dict YAML).
- `scripts/sync-devin-harness.sh` removes dead `-f` branch and detects per-source passthrough format.
- Removes no-op `harness/devin/config.json` top-file check.
- Adds negative drift-injection tests (content drift, unknown tool, Claude alias, lost subagent).
- Expands `VALID_DEVIN_TOOLS` to full Devin CLI tool set (browser, notebook, mcp, etc.).
- Fixes `normalize_tool` for PascalCase MCP tools (`McpCallTool` → `mcp_call_tool`).
- Removes redundant `rewrite_tree` after `_passthrough_copy` in `mirror_skills`.

### v0.20.4 — SecEng hardening (TEST-DEVIN-3)

- **HIGH**: Adds `_assert_no_symlink` guards before all writes to prevent symlink traversal attacks.
- **MEDIUM**: Validates `_symlink_tree` paths stay within `temp_root` (prevents temp dir escape).
- **MEDIUM**: Adds `MAX_FRONTMATTER_BYTES` (256 KiB) and catches `RecursionError`/`MemoryError` to mitigate YAML billion-laughs DoS.
- **LOW**: `normalize_tool` now rejects unknown tool names (returns `None` instead of passthrough).
- Fixes test backup/restore with `EXIT` trap, only-backup-once logic, and explicit restore before post-check.

## Three-round Devin review

| Round | Seat | Ticket | Findings | Version |
|-------|------|--------|----------|---------|
| 1 | BSA | TEST-DEVIN-1 | 5 bugs (Skill mapping, subagent loss, haiku, pre-commit, double-conversion) | v0.20.0→v0.20.1 |
| 2 | QAS | TEST-DEVIN-2 | 7 issues (type check, sync heuristic, no-op check, no negative tests, incomplete tools, PascalCase, redundant I/O) | v0.20.2→v0.20.3 |
| 3 | SecEng | TEST-DEVIN-3 | 4 vulnerabilities (symlink traversal, temp escape, YAML DoS, tool passthrough) + test robustness | v0.20.3→v0.20.4 |

**Total: 16 issues found and fixed across 3 independent Devin review seats.**

## End-to-end validation

| Test | Ticket | Task | Result |
|------|--------|------|--------|
| E2E-1 | TEST-DEVIN-E2E-1 | Tech-writer: verify release notes vs git log | Gap found (no v0.20.1–v0.20.4 notes), draft produced |

## Files Added or Modified

- `scripts/mirror-claude-to-devin.py` — passthrough, lint, symlink guards, YAML DoS, tool allowlist
- `scripts/check-devin-harness-drift.sh` — bidirectional check, wider coverage, lint integration
- `scripts/sync-devin-harness.sh` — per-source passthrough detection
- `tests/test-devin-harness-drift.sh` — 8 tests (3 happy + 4 negative + 1 restoration)
- `harness/claude/hooks/pre-commit` — hardened to `set -euo pipefail`
- `harness/devin/agents/_common-rules.md` — new (S5: shared fragment passthrough)
- `.devin/agents/_common-rules.md` — new (live consumer copy)
- `.governor-tag` — v0.20.4
- `CLAUDE.md` — banner stamped v0.20.4
- `README.md` — badge stamped v0.20.4

## Verification

```bash
bash tests/test-harness-parity.sh        # 6/6 passed
bash tests/test-devin-harness-drift.sh   # 8/8 passed
bash tests/test-spawn-devin.sh           # 20/20 passed
```
