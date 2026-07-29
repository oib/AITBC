# QA Validation Report — PILOT-51

**Ticket:** PILOT-51 — ADR-Duplikatpruefung auf die Dateinamen-Id umstellen + Frontmatter verpflichtend
**Jira twin:** ABS-560
**Branch:** PILOT-51-auto
**Commit under test:** 092da3d4
**QAS run date:** 2026-07-26
**Verdict:** ✅ APPROVED

---

## Scope

Single-file test-only change: `tests/test-adr-id-uniqueness.sh`.  
No product source, no RLS/DB/auth, no `scripts/orchestrator.sh` touch, no shared-file edit.  
Closes the ABS-558 blind spot (double-0028 ADR went undetected because the old dupe check keyed on the frontmatter `id:` and skipped frontmatterless files via `$1 != ""`).

---

## Acceptance Criteria Verification

### AC1 — Dupe check keys on filename id (not frontmatter id)

**Result: ✅ PASS**

`check_dupes` now builds rows via `name_id()` for EVERY file and uses the awk
rule `{ count[$1]++; files[$1] = files[$1] " " $2 }` with no `$1 != ""` filter.
A frontmatterless file still has a number in its filename; it is now counted.
Independently verified by reading the implementation at lines 67–78 of the
current file and confirmed by self-check (a) and (d) both passing.

### AC2 — Missing frontmatter is a FAIL, not just a note

**Result: ✅ PASS**

`check_names` emits `"$(basename "$f"): missing frontmatter id:"` when `fid` is
empty (line 63). Section 2 of the main run body turns any non-empty `check_names`
output into `fail()` calls (lines 99–103). Self-check (c) creates a file with no
`id:` in its frontmatter (`---\nstatus: proposed\n---`) and asserts
`check_names` returns non-empty → "missing frontmatter id is caught" PASS.

### AC3 — Falsifying fixture: two files with same number, one frontmatterless → BOTH named

**Result: ✅ PASS**

Self-check (d) creates:
- `ADR-A-0028-eventbus-a.md` — valid frontmatter `id: ADR-A-0028`
- `ADR-A-0028-eventbus-b.md` — NO frontmatter at all (bare body text)

Then asserts `check_dupes` output contains both basenames. This is a direct replay
of the ABS-558 incident. The check passes, proving the guard now catches the
double-0028 shape.

### AC4 — ADR import still aborts cleanly, no duplicates

**Result: ✅ PASS (non-regression)**

The commit touches only `tests/test-adr-id-uniqueness.sh`. The importer
(`docs/sop/ADR-IMPORT-RUNBOOK.md`) is untouched. The runbook specifies:
- Missing `id:` → file skipped (fail-closed), sibling files continue unaffected.
- `id` must be unique per project; violations abort that file (unique-key
  constraint), not the whole tar.

No behavioural change to the import path. Non-regression confirmed.

---

## Test Suite Run (independent, this QAS spawn)

```
Command: unset BACKEND_URL BACKEND_TOKEN TRACKER_CMD ORCH_INSTANCE_ID && bash tests/test-adr-id-uniqueness.sh
Commit:  092da3d4c6d9d33aaa35d2dde37be1804e79c2c3

=== ADR id uniqueness guard (ABS-283) ===

repo ADR ids are unique
  PASS  no duplicate ADR id across 29 ADR file(s)

frontmatter id matches filename id
  PASS  every ADR's frontmatter id agrees with its filename

guard bites synthetic violations (proves the check is live)
  PASS  clean fixture: no false duplicate
  PASS  clean fixture: no false id/filename mismatch
  PASS  duplicate filename number across two files is caught
  PASS  frontmatter/filename id mismatch is caught
  PASS  missing frontmatter id is caught
  PASS  duplicate number with a frontmatterless file is caught and names both files

=== ADR id uniqueness guard: 8 passed, 0 failed ===

exit: 0
```

**8 passed / 0 failed. Exit 0.** ✅

---

## DoD Checklist

| Item | Status |
|------|--------|
| AC1: dupe check keys on filename id | ✅ PASS |
| AC2: missing frontmatter is FAIL | ✅ PASS |
| AC3: fixture names BOTH files (ABS-558 incident reproduced) | ✅ PASS |
| AC4: ADR importer non-regression | ✅ PASS |
| Test suite green (8/0, exit 0) | ✅ PASS |
| Only test file modified (no orchestrator.sh, no shared files) | ✅ PASS |
| Backend env vars unset per operator guardrail | ✅ PASS |
| Commit on `PILOT-51-auto` branch | ✅ PASS |
| Dead `id_table` helper removed (net code reduction) | ✅ PASS |

---

## Verdict

**APPROVED for Story Acceptance.**

All four acceptance criteria met. Test suite green (8/0, exit 0) confirmed by
independent QAS run on commit `092da3d4`. The ABS-558 double-0028 blind spot is
mechanically closed. No scope creep, no RLS/DB surface, no shared-file edits.
