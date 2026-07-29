# QA Validation Report — ABS-273

**Ticket**: ABS-273 — Consumer-Integritätscheck: durch den alten Treiber token-verfälschte Kopien reparieren (setup-template.sh REPLACEMENT_KEYS)  
**Branch**: `ABS-273-auto`  
**Commits reviewed**: `7b843fa` (initial), `e74c75e` (M1/L1 fix), `05329f2` (AC4 — report hand-check entry-wise predicate)  
**QAS seat date**: 2026-07-14 (updated; prior QAS seat covered 7b843fa+e74c75e)  
**Verdict**: ✅ **APPROVED**

---

## Validation Matrix

### Test Suites (independently re-run on 05329f2)

| Suite | Result | Count |
| --- | --- | --- |
| `tests/test-migrate-project.sh` | ✅ PASS | 130/130 |
| `tests/test-migration-exceptions.sh` | ✅ PASS | 5/5 |
| `tests/test-agent-def-overlay.sh` | ✅ PASS | 24/24 |
| `bash -n scripts/migrate-project.sh` | ✅ PASS | syntax OK |
| `shellcheck -S warning scripts/migrate-project.sh` | ✅ PASS | 0 warnings |

### Acceptance Criteria

| # | Criterion | Verdict | Evidence |
| --- | --- | --- | --- |
| AC1 | Array-scoped detection of instantiated REPLACEMENT_KEYS (not whole-file check) | ✅ PASS | `AC1: instantiated wizard detected as CORRUPT` + `AC1 regression: corrupt copy still contained {{TOKEN}}s — detection is array-scoped` both PASS |
| AC1 partial | Partial substitution (e.g. 27/30 keys) also detected as CORRUPT | ✅ PASS | `AC1: PARTIALLY instantiated wizard detected as CORRUPT` PASS; driver uses entry-wise `TOKENS/ENTRIES` predicate |
| AC1 fail-open | Fail-open guard: if wizard declaration renamed/reformatted, guard fires closed | ✅ PASS | ABS-249 parity block extended: driver's own `wizard_key_block()` run against real `setup-template.sh`; finds 30 literal keys. Touch function or reshape wizard → test fails. |
| AC2 | Repair path: wizard restored verbatim from upstream (CONFLICT → REPLACE) | ✅ PASS | `AC2: wizard's literal replacement keys restored`, `AC2: repaired wizard is NOT left as a recurring conflict`, `AC2: conflicts=0` all PASS |
| AC2 partial | Partial corruption also triggers restore | ✅ PASS | `AC2: partially corrupted wizard is restored from upstream too` + `conflicts=0` PASS |
| AC2 exception | Project-owned exception: report-only, never overwritten | ✅ PASS | Else branch in driver confirmed; reports `Repair by hand` + `cp` instruction |
| AC3 | Residue in `promote-release.sh` / `sync-claude-harness.sh` reported, never auto-repaired | ✅ PASS | `AC3: incomplete substitution in an adopted copy is reported` + `AC3: residue class is report-only — the file is not rewritten` PASS |
| AC3 graceful | No manifest → residue detection degrades gracefully | ✅ PASS | No manifest → no mapped tokens → no false-positive residue; wizard check works with or without manifest |
| AC4 | Report's hand-check snippet uses the driver's own entry-wise predicate | ✅ PASS | Report emits `TOKENS/ENTRIES` form; `AC4: the report's hand-check legend is entry-wise`, `AC4: the report's snippet compares token-shaped entries against ALL entries`, `AC4 regression: the superseded all-or-nothing legend is gone` all PASS. Parity assertion: `grep -qF` pins the token-shape pattern in BOTH the driver source AND the emitted report. |

### Definition of Done

| Item | Status |
| --- | --- |
| Report always carries `## Integrity Check (adopted copies, ABS-273)` section | ✅ `ABS-273: report always carries the integrity section` PASS |
| Healthy target shows clean verdict | ✅ `ABS-273: healthy adopted copies -> clean verdict` PASS |
| SOP §3.1.2 documents array-scoped hand-check, severity distinction, repair path | ✅ Confirmed: SOP §3.1.2 uses `TOKENS/ENTRIES` entry-wise procedure, matching the driver |
| L1 (7→10) fixed in all three locations | ✅ Driver comment (line 554), SOP §3.1.2 (line 227), test fixture comment (line 424) all say 10 |
| ABS-249 parity block extended with fail-open guard (M1) | ✅ Guard eval's driver's own `wizard_key_block()` against real file; drift on either side fails closed |
| AC4: report hand-check agrees with driver predicate (no fourth generation) | ✅ 6 assertions pin the text; parity assertion (`grep -qF`) pins the pattern in both places |

---

## Independent Verification

### AC4 Verification (05329f2)

The prior QAS report (covering e74c75e) identified OBS-1: the inline report's hand-check used `grep -c '{{'` with "healthy: non-zero · corrupt: 0", which grades a partially-corrupt wizard (e.g. 27/30 keys substituted) as HEALTHY. Commit 05329f2 fixes this and closes OBS-1.

I independently executed the report's hand-check snippet against:

| Wizard | Command output | Legend says | Correct? |
| --- | --- | --- | --- |
| Pristine (real 700-line wizard) | `30/30 replacement keys still literal` | healthy: TOKENS == ENTRIES | ✅ correctly healthy |
| Subset-substituted (27/30 keys) | `27/30 replacement keys still literal` | corrupt: any shortfall | ✅ correctly CORRUPT |

The old snippet (`grep -c '{{'`) on the same subset-substituted target prints `27` (non-zero) → old legend called it healthy. That is the exact lie the fix eliminates.

### AC1 Detection Logic (entry-wise predicate)

Driver's `wizard_is_instantiated()` at `scripts/migrate-project.sh:566` computes:
- `tokens` = entry count in `REPLACEMENT_KEYS` block matching `'^[[:space:]]*"{{[A-Z_]*}}"'`
- `entries` = total entry count in the same block

Returns 0 (corrupt) if `tokens < entries`. Partial corruption (`27/30`) is correctly detected. The parity guard in tests pins `"{{[A-Z_]*}}"` as the literal substring in BOTH driver source and report text, so the two cannot drift apart.

### L1 Resolution (7 vs 10) — Both Numbers Verified

- `10`: `sed '/^declare -a REPLACEMENT_KEYS=(/,/^)/d' scripts/setup-template.sh | grep -c '{{'` → **10** (pristine; lines outside the array carrying `{{`)
- `7`: on a subset-substituted copy: `grep -c '{{'` over whole file minus corrected array keys = **7** (the non-array lines survive the consumer's sed)
- System-architect confirmed both during Stage-1 re-review. All three locations (driver comment, SOP prose, test comment) now say 10 (pristine) consistently.

### Blast-Radius Confirmation

- `test-migration-exceptions.sh`: 5/5 — existing exception-handling tests unaffected
- `test-agent-def-overlay.sh`: 24/24 — overlay logic unaffected (system-architect noted 19/24 in their environment, confirmed pre-existing on main at f7c9a68; not a regression from ABS-273)

---

## Files Changed (full branch, f7c9a68..05329f2)

| File | Purpose |
| --- | --- |
| `scripts/migrate-project.sh` | Step 4b: `wizard_key_block()`, `wizard_is_instantiated()`, `has_mapped_residue()`, integrity check loop, report section; AC4: emits `TOKENS/ENTRIES` snippet |
| `tests/test-migrate-project.sh` | 22 new assertions: AC1/AC2/AC3 + partial-corruption + fail-open guard + AC4 parity (130 total, was 108) |
| `docs/sop/BOILERPLATE_MIGRATION_SOP.md` | §3.1.2 Integrity Check of Adopted Copies (new subsection; AC4: hand-check is `TOKENS/ENTRIES` entry-wise) |

**Pre-existing, not introduced here**: `docs/sop/BOILERPLATE_MIGRATION_SOP.md:158` MD013 line-length warning (verified identical on main baseline f7c9a68).

---

## Final Verdict

**✅ APPROVED** (all commits: 7b843fa + e74c75e + 05329f2)

All three ACs are met, plus AC4 closes the one OBS the prior QAS identified. The implementation is correct, well-tested (130/130, up from 108 baseline), and both findings from the Stage-1 bounce (M1 fail-open guard, L1 number correction) are resolved. AC4's parity assertion makes a fourth-generation predicate drift impossible.

Ticket has no `design` flag → transitioning to **Story Acceptance**.
