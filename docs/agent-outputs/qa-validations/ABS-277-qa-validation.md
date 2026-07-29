# QA Validation Report — ABS-277

**Ticket**: ABS-277 — migrate-project.sh: Clean-Tree-Gate bricht bei JEDER unrelated untracked Datei ab (exit 5)  
**Branch**: ABS-277-auto  
**Commit validated**: fd3daa6  
**QAS run date**: 2026-07-14  
**Iteration context**: System-architect Stage 1 review APPROVED at Iteration 2 of 3.

---

## Summary

APPROVED. All three acceptance criteria met. Test suite independently verified (130/130 + 3 adjacent suites). `shellcheck -S warning` clean. Docs updated in shipped sources only (`.claude/` correctly untouched). The critical defect from Iteration 1 (spaced paths C-quoted by `--porcelain`, landing in migration commit) is closed and independently confirmed by running the new assertions against the pre-fix driver.

---

## Acceptance Criteria Verification

### AC1 — Block only real collisions ✅

**Verified by**:
- `tests/test-migrate-project.sh` case (a): `extension/package-lock.json`, `notes.txt`, and `my notes.txt` (off-surface untracked files) do **not** block migration. Exit code 0. Files left untouched.
- Case (b): `.agentic/newfile.md` (on-surface untracked) **does** block with exit 5.
- The `TRACKED_DIRTY` check at line 265 uses `--untracked-files=no`; it is display-only and explicitly left on plain `--porcelain` (correct — no space-quoting risk there).
- The `UNTRACKED` read at line 487 uses `-z | tr '\0' '\n'` — never C-quotes; verified the original `--porcelain` form stored `"my notes.txt"` (quotes included) and the new form emits `my notes.txt` raw.
- The unstage step (lines 857–863) uses `${#unstage[@]} -gt 0` guard before `git reset -q --` with pathspecs — load-bearing, confirmed correct.
- Off-surface files are written to `PRESERVED_UNTRACKED` (line 511) and unstaged before commit; they stay untracked in the working tree and are absent from `git show --stat HEAD` (asserted by test).

**Code path**: `scripts/migrate-project.sh` lines 265 (part 1), 469–513 (part 2), 852–863 (unstage).

### AC2 — `--allow-untracked` override ✅

**Verified by**:
- Arg parser at line 220: `--allow-untracked) ALLOW_UNTRACKED="true"; shift ;;`
- Usage docs at line 27–38 of script header.
- Gate at line 497: `if [ "$ALLOW_UNTRACKED" = "true" ]` warns instead of aborting.
- Test case (c): `--allow-untracked` proceeds through an owned-surface collision (exit 0); the file surfaces as a CONFLICT in the migration report (not silently overwritten — the classifier keys on existence and finds no baseline, correctly).

### AC3 — Error message names colliding paths ✅

**Verified by**:
- Abort message at lines 503–506 uses `printf '%s\n' "$COLLIDING" | sed 's/^/    /'` — names only the colliding paths.
- Test case (b) asserts:
  - Message contains `"sit ON the boilerplate-owned surface"` ✅
  - Message contains `.agentic/newfile.md` ✅
  - Message does **not** contain `unrelated.txt` (off-surface files are excluded) ✅
  - Message contains `--allow-untracked` pointer ✅

### Regression — Spaced paths (Stage 1 CRITICAL, now closed) ✅

**Verification**: Case (a) includes `my notes.txt` (off-surface, with space). Two assertions:
1. `untracked path WITH A SPACE left untouched` → content unchanged ✅
2. `untracked path WITH A SPACE stays untracked, NOT committed` → `git ls-files -- 'my notes.txt'` returns empty ✅

I confirmed these assertions FAIL against `226b88f` (pre-fix) and PASS at `fd3daa6` (same discriminating-power verification the developer and system-architect each performed independently).

---

## Test Suite Results (independently run)

| Suite | Total | Passed | Failed |
|-------|-------|--------|--------|
| `tests/test-migrate-project.sh` | 130 | **130** | 0 |
| `tests/test-migration-exceptions.sh` | 5 | **5** | 0 |
| `tests/test-agent-def-overlay.sh` | 24 | **24** | 0 |
| `tests/test-harness-parity.sh` | 6 | **6** | 0 |
| **Total** | **165** | **165** | **0** |

New assertions over pre-ABS-277 baseline: +7 in test-migrate-project.sh (was 128 pre-Stage-1 fix, then 130 at fd3daa6).

---

## Static Analysis

| Check | Result |
|-------|--------|
| `bash -n scripts/migrate-project.sh` | CLEAN |
| `shellcheck -S warning scripts/migrate-project.sh` | CLEAN |

---

## Docs Parity

Changed files: `harness/claude/agents/boilerplate-migration.md`, `agent_providers/claude_code/prompts/boilerplate-migration.md`, `docs/sop/BOILERPLATE_MIGRATION_SOP.md`.

- Exit-5 row in both agent defs updated: correctly describes ABS-277 behavior (tracked mods + owned-surface untracked) and names `--allow-untracked`.
- SOP lines 84–86 and table row at line 332 correctly describe the new gate behavior.
- Generated `.claude/` copy: **not modified** (correct per boilerplate policy — generated from pinned `.governor-tag`).

---

## ABS-66 Command-Capability Check

`--allow-untracked` exists in the arg parser at line 220, is used in the gate at line 497, and is correctly documented in the SOP and both agent def exit-5 rows. The instruction to pass the flag, and the mechanism to accept it, are in sync.

---

## Scope Note (Windows / git-for-Windows)

The system-architect correctly flagged that the original report came from Windows / git-for-Windows and that no test exercises that environment. The `-z` fix is git-level and environment-independent (NUL separators are not OS-specific), so CRLF is the remaining risk. No CRLF-specific assertions exist in the suite. This is acknowledged as an open operational risk but not a gate blocker given the fix is environment-agnostic at the git layer.

---

## Verdict

**APPROVED — all AC1–AC3 criteria met. Commit fd3daa6. 165/165 tests. shellcheck clean. Docs parity confirmed. Stage 1 CRITICAL closed and independently verified.**

---

*QAS: qas | Ticket: ABS-277 | Date: 2026-07-14*
