# QA Validation — ABS-449

**Ticket**: ABS-449 — Migrations-Nummernvergabe koordinieren: next-number-Helper + Pre-Merge-Kollisionscheck  
**Commit under test**: `f7c2e03`  
**Branch**: `ABS-449-auto`  
**QAS run**: 2026-07-18  
**Verdict**: ✅ **APPROVED**

---

## AC Verification

### AC1 — Second MR goes red pre-merge, message names number + colliding file

**Status**: ✅ PASS

Evidence (from `bash tests/test-migration-number-coordination.sh`, block B):
- Same number (`010`) added on both sides → COLLISION, `exit 1`. ✅
- Identical filename added on both sides → COLLISION, `exit 1`. ✅
- Error message names the number (`010`) and the colliding file. ✅
- Branch continuing the series (`011` off target) → OK, `exit 0`. ✅

CI gate wired: `pr-validation.yml` step `"Check migration-number collision (ABS-449)"` calls
`bash scripts/migration-number-collision-check.sh "origin/${{ github.base_ref }}" HEAD` after
a `git fetch origin ${{ github.base_ref }}` — confirmed at lines 44–54.

### AC2 — Helper returns 011 on main=010; respects --target

**Status**: ✅ PASS

Evidence (suite block A + live run):
- `bash scripts/next-migration-number.sh` on real checkout (max prefix = `010`) → `011`. ✅
- `--target epic/<branch holding 011>` → `012`. ✅
- Without `--target`, epic's `011` not counted → `011`. ✅

### AC3 — Role instruction updated; seat uses helper

**Status**: ✅ PASS

Evidence:
- `harness/claude/agents/be-developer.md` line 224: references `scripts/next-migration-number.sh` with `--target` guidance. ✅
- `harness/claude/agents/data-engineer.md` line 117: `Reserve the migration NNN prefix via scripts/next-migration-number.sh`. ✅
- `agent_providers/claude_code/prompts/be-developer.md` line 224: in sync. ✅
- `agent_providers/claude_code/prompts/data-engineer.md` line 117: in sync. ✅
- `docs/database/MIGRATION_PREFIX_GUARD.md`: lists both new scripts at lines 27, 29, 46, 105–106. ✅
- Helper exercised by `test-migration-number-coordination.sh` (suite itself calls the helper). ✅

### AC4 — Existing suites stay green

**Status**: ✅ PASS

| Suite | Result |
|-------|--------|
| `tests/test-backend-status-literal-drift.sh` | 5/5 ✅ |
| `tests/test-harness-parity.sh` | 6/6 ✅ |
| `tests/test-migration-number-coordination.sh` (new) | 10/10 ✅ |

Backend `pnpm test` (133 pass / 0 fail, incl. `migrate.test.ts` + `migrate-prefix-guard`) per
be-developer handoff; not re-run — no data-layer changes in this diff.

**Pre-existing run-all failures** (not caused by this change):
- `test-gitattributes-eol.sh` — CRLF in an ABS-441 doc (pre-existing/environmental)
- `test-wrong-entry-guard.sh` — self-hosting governor check (pre-existing/environmental)

Both are outside this diff's scope and confirmed unrelated to ABS-449.

---

## DoD Check

| Item | Status |
|------|--------|
| All AC criteria met | ✅ |
| Additive-only, no existing migrations renamed | ✅ |
| Bash 3.2 / BSD-compatible scripts | ✅ (confirmed by suite flag `--posix` avoidance, `10#` octal guard) |
| New suite auto-discovered by tests.yml + run-all.sh (registered in test-scope-map.txt) | ✅ |
| No DB migration added (pure bash + CI + docs) | ✅ |
| Fail-closed: `exit 64` on bad args / unknown refs | ✅ (suite block C, 3/3) |
| No Human-Gate touched | ✅ |

---

## Summary

All four acceptance criteria pass with direct evidence. The implementation is additive-only (10
files: 2 bash scripts, 1 test suite, 1 CI step, 2 harness agent files, 2 provider mirror files,
1 doc update, 1 test-scope-map entry). The collision gate correctly slots into the
ABS-397/398 rebase-gate family and the helper returns `011` live. No design flag set → exit
target is **Story Acceptance**.
