# QA Validation — ABS-249
**Migration-Treiber: Token-Normalisierung vor dem Diff**

- **Branch:** `ABS-249-auto`
- **Commit reviewed:** `17a6558` (working tree clean)
- **Prior approved commit:** `820a2f4` (AC1/AC2/AC3 + write-path scope-add)
- **Validation date:** 2026-07-13
- **Verdict:** APPROVED

---

## What Changed Since the Prior Approved Commit

Commit `17a6558` is a +5-line rebase-integration fix. ABS-249's token-normalization
refactor removed `hash_file()`/`hash_adr_content_file()` because no code on the
ABS-249 branch called them. ABS-259 (fork budget) landed on the epic afterward and
`exception_defork_state()` calls both — so the merged driver crashed with
`hash_file: command not found`. The fix restores the two one-line helpers verbatim
at their original positions (l.69 / l.90). No other line in `migrate-project.sh` moved.

**Verified independently:**
- `git show 17a6558 --stat` → `scripts/migrate-project.sh | 5 insertions(+)`, no other file.
- The two restored helpers match the epic tip's definitions byte-for-byte.
- `hash_file()` and `hash_adr_content_file()` are called ONLY by
  `exception_defork_state()` (lines 619/621). ABS-249's token-normalization stays
  scoped to the `norm_upstream|hash_stdin` path (lines 459–468) — no
  cross-contamination.

---

## Acceptance Criteria

### AC1 — Substitute baseline with setup-tokens + CR-normalize before hash compare: PASS

`build_token_sed()` (line 138) builds the sed script from three sources:
- `SUBST_PAIRS` + `IDENTITY_PAIRS` from `.harness-manifest.yml` (parsed by `parse_yaml_map`)
- `DERIVED_PAIRS`: TICKET_PREFIX_LOWER, GITHUB_REPO_URL, AUTHOR_INITIALS, computed from
  manifest values
- `HARNESS_VERSION` via `printf 's|{{%s}}|%s|g\n' HARNESS_VERSION "$hv"` (line 149)

Two sed scripts are built: `SED_BASE` (v\<FROM\>) and `SED_CUR` (v\<TO\>). `norm_upstream()`
(line 171) applies the selected script and strips CR (`tr -d '\r'`). The diff path applies
`SED_BASE` to the baseline and `SED_CUR` to the current source before hashing (lines 459–468).

`is_substitutable()` gates which files enter the normalization path — mirrors setup's sweep
set exactly, including the self-exclusion of `setup-template.sh`.

Unchanged from approved commit `820a2f4`.

### AC2 — Instantiation-only file classified as unmodified: PASS

After normalization, `tgt_hash == baseline_hash` → classified `already_current` (n_skip,
line 471–472). The file is not written.

Test suite (96/96, run independently):
```
PASS  AC2: token-only file is classified unmodified (already-current, not rewritten)
PASS  AC2: token-only file keeps its instantiated content
PASS  AC2: CRLF-only difference is NOT a conflict (CR normalization)
PASS  AC2: unmodified instantiated script replaced with the v2 content
```

### AC3 — Real drift stays a conflict: PASS

When `tgt_hash != baseline_hash` → `CONFLICT_LIST` (line 477–479). The drifted file is
never overwritten.

Test suite:
```
PASS  AC3: real drift in an instantiated file IS still a conflict
PASS  AC3: drifted instantiated file left untouched (not overwritten)
PASS  AC3: conflict hunks show instantiated incoming content, not token noise
PASS  AC3: conflict diff shows the local line
PASS  AC3: conflict diff shows the incoming line
```

### Write-path scope-add (ticket comment scope): PASS

`copy_file()` (line 492) calls `subst_in_place()` at line 500.
`copy_adr_preserving_frontmatter()` (line 505) calls `subst_in_place()` at line 523;
comment there: "same substitution pipeline as the hash compare (ABS-249)".

Test suite:
```
PASS  write path: no literal {{TOKEN}} written into the target
PASS  write path: derived GITHUB_REPO_URL instantiated on write
PASS  write path: HARNESS_VERSION instantiated to the NEW version on write
PASS  write path: substituted script keeps its executable bit
```

---

## Critical Fix from Iteration 1 — Still Intact

`build_token_sed()` at line 149 uses `printf 's|{{%s}}|%s|g\n' HARNESS_VERSION "$hv"`.
No literal replacement key appears in the driver source.

**Token-free probe:**
```
git grep -onE '\{\{[A-Z_]+\}\}' -- scripts/migrate-project.sh
```
Returns only `{{TOKEN}}` (lines 94, 128, 154, 175, 701) and `{{FOO}}` (line 119).
Neither appears in setup's `REPLACEMENT_KEYS` array. Verified: `setup-template.sh` lists
29 keys (`oib` through `AITBC`); `{{TOKEN}}` and
`{{FOO}}` are absent.

**Guard assertion** (`tests/test-migrate-project.sh:346`): reads `REPLACEMENT_KEYS`
from setup's own array; asserts each key is absent from the driver source.
```
PASS  driver source carries NO literal setup replacement key (it is swept by setup)
```

---

## setup-template.sh Exclusion — Confirmed Correct

`is_substitutable()` excludes `setup-template.sh` (line 156–158). The wizard's
`REPLACEMENT_KEYS` array at lines 522–553 contains the literal tokens as data. Line 507
excludes the wizard from its own sweep. Substituting it would corrupt the wizard;
token-normalizing it on compare would make it a permanent phantom conflict. Parity test:
```
PASS  sweep parity: token-carrying wizard is NOT a conflict
PASS  sweep parity: wizard still gets the upstream v2 content
PASS  sweep parity: wizard's literal {{TOKEN}} data is NOT substituted on write
```
The ticket's Group-3 note to substitute `setup-template.sh` is superseded. The real
Group-3 complaint (`promote-release.sh`, `sync-claude-harness.sh`) is fixed.

---

## Rebase-Integration Fix — No Cross-Contamination

`hash_file()` (l.69) and `hash_adr_content_file()` (l.90) are called only at lines
619/621, inside `exception_defork_state()`. That function uses RAW hashing (no token
normalization) — ABS-259's tested behavior. ABS-249's token-normalization path
(`norm_upstream|hash_stdin`, l.459–468) does not call these helpers. The two paths are
separate.

---

## Full Test Run

```
tests/test-migrate-project.sh: 96/96 PASS (run independently, not taken from handoff)
```

The 22 additional tests (74 → 96) are ABS-259's fork-budget suite; they cover
`exception_defork_state()` and the restored helpers.

## Shellcheck

```
shellcheck scripts/migrate-project.sh
```
4 info-level findings: lines 216 (SC2015), 567 (SC2012), 767 (SC2295), 776 (SC2295).
All pre-existing. None in the ABS-249 normalization code (lines 60–179) or in the
+5-line forward-fix (lines 68–90).

---

## Gate Checklist

- [x] AC1 — Token substitution before hash compare (baseline + source), CR-normalize: PASS
- [x] AC2 — Instantiation-only file classified unmodified: PASS
- [x] AC3 — Real drift stays a conflict: PASS
- [x] Write-path scope-add — `subst_in_place` runs on both `copy_file` and `copy_adr_preserving_frontmatter`: PASS
- [x] Critical fix — driver source carries no literal replacement keys (guard enforces): PASS
- [x] setup-template.sh exclusion — correct per self-exclusion at `setup-template.sh:507`: CONFIRMED
- [x] Forward-fix — `hash_file`/`hash_adr_content_file` restored verbatim, called only by ABS-259's `exception_defork_state()`, no cross-contamination with ABS-249's normalization path: PASS
- [x] Tests: 96/96 PASS (independently run)
- [x] shellcheck: 4 info-level findings, all pre-existing, none in new code: PASS
- [x] Driver is token-free: VERIFIED (only `{{TOKEN}}`, `{{FOO}}` — not in REPLACEMENT_KEYS)
