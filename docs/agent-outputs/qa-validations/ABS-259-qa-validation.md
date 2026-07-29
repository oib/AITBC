# QA Validation — ABS-259

**Branch**: `ABS-259-auto` at `ad241f3`  
**Date**: 2026-07-13  
**QAS actor**: qas

---

## Verification method

Re-ran all tests independently (not from agent memory); read implementation
source directly; confirmed exit-code invariant in source.

---

## Test suite results

| Suite | Result |
| --- | --- |
| `tests/test-migrate-project.sh` | **75/75 PASS** |
| `tests/test-adr-status.sh` | **27/27 PASS** |
| `shellcheck -S error scripts/migrate-project.sh` | **exit 0** |

---

## AC checklist

### AC1 — `ownership.yaml` schema extended (ADR-A-0008-Amendment)

**PASS**

`.agentic/upgrade/ownership.yaml` gains block-mapping entries with fields `path` / `kind` /
`upstream_ref` / `since`. `kind` defaults to `fork`, so every legacy bare-path entry (`-
scripts/foo.sh`) stays a valid exception and migration never touches it — but it grades
`UNJUSTIFIED` in the budget. The two real exceptions are annotated `kind: structural`.
Header documents the schema with a worked example.

ADR-A-0008 Amendment 2026-07-13 committed at `54105c7`, section `Status: proposed`
(human acceptance pending, ADR-A-0004 — base frontmatter untouched at `accepted`).

### AC2 — Report shows Exception-Aging + De-Fork verdict

**PASS**

`scripts/migrate-project.sh` lines 562–580: `## Fork Budget (project_owned_exceptions)`
section, table with columns Verdict / Path / Kind / upstream_ref / Age (days). Six
verdicts: DE-FORK / UNJUSTIFIED / STALE / JUSTIFIED / STRUCTURAL / ORPHAN.

Budget: 90d default, `MIGRATE_FORK_MAX_AGE_DAYS` overridable; non-numeric value warns
and falls back to 90 (no silent misgrade). Age computed with awk days-from-civil
(`exception_defork_state` / age calc) — no `date -d` / `date -j`. De-fork check
compares target hash against current source content (conservative: no false
"deletable" verdicts).

Exit-code invariant confirmed in source: the budget block only writes to `$REPORT`;
no status variable is mutated; `n_conflict`, `n_replace`, `n_add`, `n_skip` are
untouched.

### AC3 — Test cases: justified / unjustified / de-forkable

**PASS**

`tests/test-migrate-project.sh` lines 375–382 cover:
- `JUSTIFIED` — `upstream_ref` + `since`, within 90d (line 375)
- `UNJUSTIFIED` — legacy bare-path entry, no `upstream_ref` (line 376)
- `DE-FORK` — target content byte-for-byte matches current source (line 377)
- `ORPHAN` — upstream ships no file at the path (line 378)
- `STRUCTURAL` — grades STRUCTURAL, never UNJUSTIFIED or STALE (lines 379–382)

Additional tests: DE-FORK outranks UNJUSTIFIED; budget override (`MIGRATE_FORK_MAX_AGE_DAYS=0`
turns JUSTIFIED → STALE); de-fork verdict is independent of age budget; stale fork never
blocks migration (exit code unchanged).

---

## Both ADR design traps verified

1. `kind: structural` is **explicit** — no inference from "upstream ships no file
   here". `structural` exceptions are never red. Verified at test lines 379–382.
2. Age is **awk days-from-civil** — no `date -d` / `date -j`. Verified in source
   and by the leap-February assertion (test: 100-day span across Feb 2024 counts
   correctly).

---

## Pre-existing data-loss fix (in-scope)

`parse_yaml_list` now strips trailing comments **before** stripping quotes.
Previously `- "scripts/foo.sh"  # note` left `scripts/foo.sh"` with a stray
quote; `is_exception` never matched; the pinned file was silently overwritten.
Regression test at lines 391–392 confirms the fix. Routing both classifier and
report through a single parser makes report/classifier divergence structurally
impossible — the fix closes a whole class of failure, not just the bug.

---

## Flagged finding (pre-existing, non-blocking)

The ownership map is read only from `$SOURCE` (`migrate-project.sh:170`). A
consumer cannot declare a fork in their own map — their declaration is silently
ignored; both their fork and the edited map land as CONFLICT. The budget therefore
grades only upstream's list. This is **pre-existing (ABS-227)**, **outside the
ADR cut**, and requires an ownership-semantics decision. The system-architect
adjudicated it in the In Review gate: follow-up story under ABS-245
(`ownership.local.yaml` union). Not a bounce.

---

## Verdict

**APPROVED** for Story Acceptance.

AC1 ✅ AC2 ✅ AC3 ✅  
Tests: 75/75 + 27/27  
Shellcheck: clean  
Exit-code invariant: confirmed in source  
ADR traps: both honored  
Data-loss fix: verified and regression-tested  
