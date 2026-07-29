# QA Validation Report — ABS-179

**Ticket**: ABS-179 — setup-template.sh Performance: Ein-Pass-Substitution + Verzeichnis-Excludes  
**QAS Run**: 2026-07-10  
**Branch**: `ABS-179-auto`  
**HEAD**: `a4a54a7 perf(setup): one-pass substitution + shared dir excludes [ABS-179]`  
**Diff scope**: HEAD~1..HEAD — 2 files, +112/-30  
**Verdict**: ✅ **APPROVED**

---

## Independent Verification Commands Run

```
bash -n scripts/setup-template.sh
shellcheck -S warning scripts/setup-template.sh
bash tests/test-setup-template.sh
```

All three passed before consulting the implementer/architect reports.

---

## Acceptance Criteria Verification

### AC1 — All three sweeps use the shared exclude list; node_modules/.git/dist/build/.next/vendor/worktrees/tmp not traversed

**Code evidence** (verified via Read, lines 113–131 + 495–508 + 514–518 + 668–672):

```bash
# Shared exclude list — built once, applied to every sweep
SWEEP_EXCLUDE_DIRS=(.git node_modules dist build .next vendor worktrees tmp)
GREP_SWEEP_ARGS=()
for _g in "${SWEEP_INCLUDE_GLOBS[@]}"; do GREP_SWEEP_ARGS+=(--include="$_g"); done
for _d in "${SWEEP_EXCLUDE_DIRS[@]}"; do GREP_SWEEP_ARGS+=(--exclude-dir="$_d"); done

# Sweep 1 — candidate scan (produces CANDIDATE_FILES)
grep -rl '{{' "$REPO_ROOT" "${GREP_SWEEP_ARGS[@]}" --exclude="setup-template.sh"

# Sweep 2 — idempotency check: reuses CANDIDATE_FILES (no re-traversal)
grep -q 'AITBC' "${CANDIDATE_FILES[@]}"

# Sweep 3 — REMAINING report: reuses CANDIDATE_FILES (no re-traversal)
grep -oh '{{[A-Z_]*}}' "${CANDIDATE_FILES[@]}"
```

**Test 14 evidence** (independently run):

```
=== Test 14: Directory excludes -- node_modules/dist never traversed [ABS-179] ===
  PASS  wizard exits 0 with placeholder files present in excluded dirs
  PASS  tracked README.md is still substituted with excludes in place
  PASS  placeholder in node_modules/ is NOT substituted (dir excluded)
  PASS  placeholder in dist/ is NOT substituted (dir excluded)
  PASS  node_modules-only placeholder is NOT listed in the REMAINING report (dir not traversed)
```

**Verdict**: ✅ PASS

---

### AC2 — One candidate scan + one sed call per file; dialect detection once per run

**Code evidence** (lines 95–106 + 596–623):

```bash
# Dialect detected ONCE at startup
if sed --version 2>/dev/null | grep -q 'GNU'; then
  SED_IS_GNU=true
else
  SED_IS_GNU=false
fi

# All 30 expressions accumulated into SED_EXPRS array
SED_EXPRS+=(-e "s|${OLD_ESC}|${NEW_ESC}|g")  # repeated per non-empty key

# ONE invocation per candidate file
for file in "${CANDIDATE_FILES[@]}"; do
  _sed_inplace "${SED_EXPRS[@]}" "$file"
done
```

The old code ran `find` 30 times (once per placeholder) and invoked `sed --version | grep GNU` inside every per-file `_sed_inplace` call.  
The new code: one `grep -rl` candidate scan, one accumulated `-e` chain, one `sed` per file, `SED_IS_GNU` resolved at startup.

**Verified via**:
- Code inspection (no `find` loop in replacement section)
- `shellcheck -S warning` clean (no spawning issues flagged)
- `bash -n` OK

**Verdict**: ✅ PASS

---

### AC3 — Benchmark: scratch project with real node_modules bootstraps in < 60s

**QAS-run benchmark** (synthetic, not relying on implementer report):

```
Environment: boilerplate tree (193 candidate files) + synthetic node_modules
  (2,802 files across 80 scoped packages, each with AITBC in README.md)
Total file count: 3,852
Elapsed: ~1s   (AC: < 60s)
Exit code: 0

node_modules/pkg-0001/README.md AITBC count after wizard: 1
(placeholder survived — dir excluded correctly)
```

The implementer's 11k-file claim (2s) exceeds the synthetic test size but is structurally sound: `grep -rl` with `--exclude-dir` terminates the moment it enters an excluded dir without reading its contents.

**Verdict**: ✅ PASS

---

### AC4 — Idempotency: second run prints "Nothing to replace"; no file changes

**Live evidence** (QAS-run second pass on the benchmark fixture):

```
Exit code: 0
Output: "  Nothing to replace -- no AITBC tokens remain (already bootstrapped)."
```

Test 9 (run independently, PASS) confirms hash-equivalent behavior:

```
=== Test 9: Run-twice idempotency [ABS-50] ===
  PASS  first run exits 0
  PASS  second (idempotent) run exits 0
  PASS  first run performs replacement
  PASS  second run detects nothing to replace
  PASS  README stays correctly substituted after two runs
  PASS  wizard copy survives two runs (no default self-delete)
```

**Verdict**: ✅ PASS

---

### AC5 — Byte-identical substitution result vs old method on the boilerplate tree

**Reasoning verified** (code inspection + test suite):

- Old method: N sequential sed passes over each file (one per placeholder), no cross-line state, no hold-space operations.
- New method: one sed invocation with N `-e` expressions — byte-identical output when there is no cross-line state (sed applies each expression left-to-right on every line; no ordering difference for non-overlapping substitutions).
- Declared key order (longer/more-specific keys first) is preserved in the `SED_EXPRS` array construction.
- Empty/equal-value skip (lines 604–607) preserved from old code.

System architect verified `git ls-files` shows **zero tracked files** under `dist/build/.next/vendor/worktrees/tmp`, so the broader exclude list drops no real substitution targets vs the old `node_modules/.git`-only `find` loop.

Tests that cover substitution correctness (all passing in QAS-run 87/87):
- Test 1: basic substitution
- Test 3: full-value manifest correctness
- Test 9: idempotency after substitution

**Verdict**: ✅ PASS

---

### AC6 — Existing bootstrap tests green; new Test 14 for exclude-list coverage

**QAS-run test output** (full independent run):

```
$ bash tests/test-setup-template.sh

  Total:  87
  Passed: 87
  Failed: 0

  ALL TESTS PASSED
```

Test 14 adds four assertions covering the exclude-list regression:
1. Wizard exits 0 with placeholder files in excluded dirs (stability)
2. Tracked README.md still substituted (excludes do not over-exclude)
3. Placeholder in `node_modules/` **not** substituted
4. Placeholder in `dist/` **not** substituted
5. `node_modules`-only token absent from REMAINING report

All five assertions PASS in the QAS-run.

**Verdict**: ✅ PASS

---

## Additional Validation

| Check | Result |
|-------|--------|
| `bash -n scripts/setup-template.sh` | OK |
| `shellcheck -S warning scripts/setup-template.sh` | Clean (exit 0) |
| Out-of-scope audit (manifest/gap-report logic) | Neither performs full-tree scan; manifest uses collected values, gap report reads only `profile.yaml` — no exclude change needed, consistent with Out-of-scope note |
| REPLACEMENT_KEYS count | 30 keys (verified via code, matches ticket's ~30 estimate) |
| Non-blocking note from SA (newline-in-filename robustness) | `grep -rl` newline-delimited vs old `find -print0` — nil impact in a template repo; no boilerplate filenames contain newlines. Not a gate condition. |

---

## Final Verdict

**ALL 6 ACCEPTANCE CRITERIA: PASS**

```
AC1  Shared exclude list on all three sweeps  ✅ PASS
AC2  One scan + one sed/file + dialect once   ✅ PASS
AC3  Benchmark < 60s                          ✅ PASS  (~1s measured)
AC4  Idempotency preserved                    ✅ PASS
AC5  Byte-identical substitution result       ✅ PASS
AC6  87/87 tests green incl. new Test 14      ✅ PASS
```

**ABS-179: APPROVED for RTE.**
