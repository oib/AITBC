# QA Validation — ABS-247

**Ticket**: ABS-247 — Runner: flag-konditionale Stationen im STATION-GUARD erzwingen  
**Branch**: ABS-247-auto @ ce0ec08  
**Validator**: qas  
**Date**: 2026-07-13  
**Verdict**: **APPROVED**

---

## Scope

Pure-bash runner change: `scripts/orchestrator.sh` (+84/-22), `tests/test-station-guard.sh` (+83). No DB/RLS/auth/migration/TypeScript surface.

Changed functions:
- New: `chain_station_mandatory <name> [active_flags]`, `active_conditional_flags <dump>`
- Updated: `first_skipped_mandatory` (optional 3rd `flags` arg), `forward_skip_illegitimate` (optional 3rd `flags` arg), `station_guard` (reads flags from dump, threads to both helpers, names flag in audit comment)

---

## Independent Validation

All commands run by QAS against the actual branch (not taken from prior handoff):

```
bash tests/test-station-guard.sh   → 96 passed / 0 failed
bash tests/test-iteration-guard.sh → 46 passed / 0 failed
bash tests/test-kill-guard.sh      → 31 passed / 0 failed
bash -n scripts/orchestrator.sh    → SYNTAX OK
```

`active_conditional_flags` verified against inline dumps:
- `flags: [design]`       → `"design"`
- `flags: [security]`     → `"security"`
- `flags: [data]`         → `"data"`
- `flags: [design, security, data]` → `"design security data"`
- `flags: []`             → `""`

2-arg backward-compat verified:
- `first_skipped_mandatory 7 9` (no flags) → `""` (Design Test still transparent)
- `forward_skip_illegitimate "In Test" "Story Acceptance"` (no flags) → green

---

## AC Verification

### AC1: design-flagged In Test → Story Acceptance → guard INTERVENES, redirect to Design Test, audit comment

**PASS.** End-to-end test `ABS-247 AC1` (6 assertions, all green):
- `station_guard` returns rc=0 (intervenes)
- intent log: `INTENT STATION-GUARD ticket=ABS-247D role=- to=Design Test`
- adapter calls: `TRANSITION ABS-247D Design Test` + `COMMENT ABS-247D --kind skip --actor orchestrator`
- audit comment body contains `"design"` (names the gating flag) and `"ABS-247"` (cites enforcement ref)

### AC2: unflagged ticket — behaviour unchanged, SKIP-FORWARD legit

**PASS.** End-to-end test `ABS-247 AC2` (3 assertions, all green):
- `station_guard` returns rc=1 (no-op)
- no INTENT log line
- `STUB_CALLS` file is empty (zero adapter writes)

Backward-compat also confirmed by existing pre-ABS-247 pure tests: `In Review -> In Test (all skipped stages conditional) -> no-op` still PASS.

### AC3: security/data flags → Security Review / Test Prep

**PASS.** Two end-to-end test sections, both green:
- security-flagged `In Review → In Test`: redirects to `Security Review`; audit comment contains `"security"`
- data-flagged `In Review → In Test`: redirects to `Test Prep`

Pure-logic assertions (in ABS-247 pure section):
- `chain_station_mandatory "Security Review" "design"` → false (unrelated flag: skippable)
- `chain_station_mandatory "Security Review" "security"` → true (mandatory)
- `chain_station_mandatory "Test Prep" "data"` → true (mandatory)
- `first_skipped_mandatory 4 6 "security"` → `"Security Review"`
- `first_skipped_mandatory 5 7 "data"` → `"Test Prep"`
- `first_skipped_mandatory 4 7 "data"` → `"Test Prep"` (Security Review still skippable without security flag)

### AC4: tests in tests/ covering both flagged and unflagged

**PASS.** `tests/test-station-guard.sh` gains three sections:
1. `ABS-247 — flag-conditional stations are enforced (pure logic)` — 20 assertions covering `chain_station_mandatory` + `first_skipped_mandatory` + `forward_skip_illegitimate` for all flag/no-flag combinations
2. `ABS-247 AC1 — design-flagged In Test → Story Acceptance end-to-end` — 6 assertions
3. `ABS-247 AC2 — same hop unflagged end-to-end` — 3 assertions
4. `ABS-247 AC3 — security-flagged / data-flagged end-to-end` — 4 + 2 assertions

All 96 tests pass in the full suite.

---

## Pre-existing Issues (not in diff, no regression)

- `test-wrong-entry-guard`: 5 failures pre-existed on pristine main (confirmed by be-developer against stashed tree); `wrong_entry_guard` is outside this diff.
- shellcheck warnings in orchestrator.sh lines 3857/4062/4103/4133: pre-existing, outside edited regions.

Neither constitutes a regression attributable to ABS-247.

---

## Summary

| Check | Result |
|---|---|
| AC1 design-flag enforcement | PASS |
| AC2 unflagged no-op / SKIP-FORWARD | PASS |
| AC3 security/data flag enforcement | PASS |
| AC4 guard suite tests present | PASS |
| bash syntax | PASS |
| Guard test suite 96/96 | PASS |
| Backward-compat (2-arg callers) | PASS |
| Pre-existing failures isolated | CONFIRMED |

**Verdict: APPROVED → Story Acceptance**
