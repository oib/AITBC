# QA Validation Report — PILOT-23

**Date**: 2026-07-24  
**Validator**: qas  
**Branch**: `PILOT-23-auto`  
**Commit**: `713714dca31b16d679227adf35c9238733910d7a`  
**Verdict**: ✅ APPROVED

---

## Ticket Summary

**PILOT-23**: ABS-535-Folge: Skill-Pfad-Rewrite fehlt im --agent-Fallback (ORCH_AGENTS_ARG_MAX) — große Rollen-Defs poisonen weiter.

Root cause: The ABS-535 skill-path rewrite only applied on the `--agents` JSON inline path. Role defs exceeding `ORCH_AGENTS_ARG_MAX` (default 24000 B; be-developer/po-agent/tech-writer all exceed it) fell back to a bare `--agent <role>` that loaded the un-rewritten on-disk def. SESSION-POISONED despite ABS-535 fix.

---

## Acceptance Criteria — Verification

### AC1 — Rewrite on BOTH spawn paths (ABS-535 skill-path rewrite + ABS-174 commons + Read-allowlist applies on the `--agent` fallback path)

**Status**: ✅ PASS

Evidence (code inspection, commit `713714dc`):
- `build_agents_json` gains an `emit="def"` mode (line 205–206, 337–352 in `orchestrator-spawn-claude.sh`). This mode runs the same `rewrite_skills` awk filter and commons prepend as the `emit="json"` (inline) path, then emits a markdown agent def instead of JSON.
- The argv-size fallback (previously: bare `--agent $ROLE`) now: creates a throwaway `--plugin-dir` via `mktemp`, calls `build_agents_json def "$FALLBACK_AGENT"` to write the rewritten def to `$PLUGIN_DIR/agents/$ROLE.md`, and invokes the CLI with `--plugin-dir "$PLUGIN_DIR" --agent "$FALLBACK_AGENT"` (lines 433–439).
- No remaining bare `--agent "$ROLE"` fallback path exists in the script.
- `git grep ORCH_AGENTS_ARG_MAX=1000000`: **zero results** — OPFIX was a launcher env var, not a tracked file; this fix retires it.

### AC2 — Conformance case `ORCH_AGENTS_ARG_MAX=1` in `test-spawn-skill-path.sh` proving no `harness/claude/skills` load path survives

**Status**: ✅ PASS

Evidence (test run, this validation):
- AC5 block added at line 239–280 of `test-spawn-skill-path.sh`:
  - `spawn tech-writer env ORCH_AGENTS_ARG_MAX=1` forces the fallback path.
  - Asserts: `--agents` absent from argv (def travels in file, not argv); `--plugin-dir` present; unique `tech-writer__seat` selector used; def frontmatter carries `name: tech-writer__seat`; docs-station and stop-slop references rewritten to LIVE skills dir; no `harness/claude/skills/docs-station` or `harness/claude/skills/stop-slop` load paths in the materialized def; commons prepended; Read-allowlist emitted; no `--add-dir`.

### AC3 — Interim OPFIX `ORCH_AGENTS_ARG_MAX=1000000` retired

**Status**: ✅ PASS

Evidence: `git grep ORCH_AGENTS_ARG_MAX=1000000` → zero results. The OPFIX was a launcher environment variable override, not a tracked file. This fix makes it unnecessary; operator removes it from future pilot launches.

---

## Test Suite Results

**Command**: `bash tests/test-spawn-skill-path.sh`  
**Commit**: `713714dca31b16d679227adf35c9238733910d7a`  
**Result**: **32/32 passed** — ALL TESTS PASSED

AC5 detail (forced ORCH_AGENTS_ARG_MAX=1 fallback, 12 assertions):
- PASS: fallback forced: inline --agents omitted (argv stays under the Windows limit)
- PASS: fallback hands the def via a throwaway --plugin-dir
- PASS: fallback selects a UNIQUE agent name
- PASS: fallback def frontmatter carries the unique selector name
- PASS: fallback def: docs-station reference rewritten to the LIVE skills dir
- PASS: fallback def: stop-slop reference rewritten to the LIVE skills dir
- PASS: fallback def: no harness/claude/skills LOAD path remains for docs-station
- PASS: fallback def: no harness/claude/skills LOAD path remains for stop-slop
- PASS: fallback def: commons prepended too (ABS-174 parity)
- PASS: fallback def: mirror-parity glob mention survives verbatim (EDIT-scoped, not a load)
- PASS: fallback: Read-allowlist for the live skills dir still emitted
- PASS: fallback: no --add-dir (no WRITE grant to the governing skills)

**Command**: `bash tests/test-orchestrator.sh`  
**Commit**: `713714dca31b16d679227adf35c9238733910d7a`  
**Result**: **1286 passed / 0 failed** — ALL TESTS PASSED (aggregated over 4 shards)

---

## Additional Checks

| Check | Result |
|---|---|
| No `harness/claude/skills` load paths in fallback def | ✅ PASS (test AC5 + code inspection) |
| Unique `__seat` selector prevents project agent shadowing | ✅ PASS (test AC5 assertions) |
| Tool-narrowing parity (`--disallowedTools` backstop) | ✅ PASS (code: lines 441–444, behavior-identical to pre-PILOT-23 fallback) |
| ABS-174 commons prepend on fallback path | ✅ PASS (test AC5: "COMMONS: apply" assertion) |
| Fail-open preserved (no live skills dir → identity rewrite) | ✅ PASS (AC4 in test-spawn-skill-path.sh, 32/32) |
| ABS-251 argv-size contract intact (no regression) | ✅ PASS (test-orchestrator.sh 1286/0) |
| Scope: shell + docs + test only (no RLS/DB/TS surface) | ✅ Confirmed |
| `ORCH_AGENTS_ARG_MAX=1000000` OPFIX not in repo | ✅ `git grep` empty |

---

## Non-Blocking Limitation (Documented)

The fallback `mktemp` plugin dir is not cleaned up at process exit — the seam uses `exec claude`, so a cleanup trap cannot fire. Dirs are tiny; documented in the architect review and the commit message. Not a defect.

---

## Flags

- `design` flag: NOT set — exit target is **Story Acceptance** (not Design Test).

---

## Final Verdict

**APPROVED** — All three ACs verified. Both test suites green (32/32 + 1286/0) run independently on commit `713714dc` on `PILOT-23-auto`. No blocking findings. Transitioning to Story Acceptance.
