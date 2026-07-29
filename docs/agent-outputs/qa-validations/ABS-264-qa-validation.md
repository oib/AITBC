# QA Validation Report — ABS-264

**Ticket:** ABS-264 — De-Fork: consumer-declarable forks via `ownership.local.yaml` (map union) + sync-harness exception honoring + SOP §3.2 fix
**Branch:** `ABS-264-auto` @ `61a8c6f`
**Validated by:** QAS
**Date:** 2026-07-13
**Verdict: APPROVED**

---

## Test Results (independently run)

| Suite | Count | Result |
|---|---|---|
| `bash tests/test-migrate-project.sh` | 83/83 | PASS |
| `bash tests/test-migration-exceptions.sh` | 5/5 | PASS |

---

## AC Verification

### AC1 — Local-map fork honored: PRESERVED + appears in Fork Budget table

**Test:** `tests/test-migrate-project.sh` — ABS-264 block, three assertions:
- "fork declared only in ownership.local.yaml is PRESERVED (not replaced)" — PASS
- "a local-map exception is never a CONFLICT" — PASS
- "local-map fork appears in the ## Fork Budget table with its verdict" — PASS

**Code confirmed:** `migrate-project.sh` lines 288–291 — `parse_exceptions_table` runs on both SOURCE `ownership.yaml` and TARGET `ownership.local.yaml`; the result goes into one `EXCEPTIONS_TABLE`. Both the classifier (`is_exception`) and the fork-budget report read from this single table, so report and actual file disposition cannot diverge.

### AC2 — Subtract-only invariant enforced: PASS

**Test:** `tests/test-migrate-project.sh`:
- "an undeclared upstream-owned file still migrates (local map only subtracts)" — PASS
- "a local boilerplate_owned: block is IGNORED with a warning (never extends the managed surface)" — PASS

**Code confirmed:** `migrate-project.sh` lines 278–279 — the presence of a `boilerplate_owned:` block in the local map triggers a `warn … SUBTRACT-ONLY` message; only `project_owned_exceptions` is unioned, never `boilerplate_owned`. `boilerplate_owned` is sourced exclusively from `$SOURCE` at line 261.

### AC3 — `ownership.local.yaml` is `kind: structural`: PRESERVED + graded STRUCTURAL

**Test:** `tests/test-migrate-project.sh`:
- "ownership.local.yaml is PRESERVED byte-for-byte through migration" — PASS
- "ownership.local.yaml is graded STRUCTURAL in the report" — PASS

**Code confirmed:** `.agentic/upgrade/ownership.yaml` lines 88–93 — `ownership.local.yaml` is declared with `kind: structural` under `project_owned_exceptions`. The structural classification means it is carried through migration without conflict surface and graded `STRUCTURAL` (never `UNJUSTIFIED`/`STALE`) in the fork-budget table.

### AC4 — Delegated sync honors unioned exception list for `.claude/**`: PASS

**Test:** `tests/test-migration-exceptions.sh` (5/5):
- "a .claude/** file exception is PRESERVED through the delegated sync (not overwritten)" — PASS
- "a .claude/** directory exception preserves the whole subtree" — PASS
- "a NON-exception .claude file is still synced (report-only invariant for non-exception paths)" — PASS
- "the sync reports the driver exception as skipped" — PASS
- "without MIGRATE_EXCEPTIONS the .claude file IS synced (exception honoring is load-bearing)" — PASS

**Code confirmed:**
- `migrate-project.sh` line 442: `MIGRATE_EXCEPTIONS="$EXCEPTIONS" bash "$SOURCE/scripts/sync-claude-harness.sh" sync --yes` — the full unioned list passes as an env var to the delegated sync.
- `sync-claude-harness.sh` lines 1446–1464: `is_migration_exception` reads `MIGRATE_EXCEPTIONS`, qualifies domain-relative vs root-relative paths using `CURRENT_DOMAIN`, then prefix-matches (exact file or directory subtree). Line 1484: `is_migration_exception "$file" && return 0` fires before manifest-protected or `.sync-exclude` checks — honored regardless of manifest presence.

No report/classifier divergence for `.claude/**` exceptions: the path the budget grades as an exception is the same path the sync skips.

### AC5 — SOP §3.2 corrected: PASS

**Confirmed:** `docs/sop/BOILERPLATE_MIGRATION_SOP.md` lines 175–188 now instruct consumers to declare forks in `.agentic/upgrade/ownership.local.yaml` (not the boilerplate-owned `ownership.yaml`). The text covers: subtract-only, structural exception (zero conflict surface), fork-budget grading, and `.claude/**` honoring via the delegated sync. The described flow is the one AC1 and AC4 tests exercise.

### AC6 — Report-only invariant preserved (ABS-259 carry-over): PASS

**Test:** `tests/test-migrate-project.sh`:
- "AC6: exit code unchanged (report-only) with a local map present" — PASS

**Confirmed:** The union read is performed at parse time; no exception path alters the migration exit code or changes CONFLICT/REPLACE/ADD/SKIP counts for non-exception paths.

---

## Additional Verification

**ADR-A-0008 Amendment 2026-07-13 (ABS-264):** `adrs/agentic/ADR-A-0008-boilerplate-ownership-and-upgrades.md` — amendment committed at `61a8c6f`, status `proposed` (human acceptance required per ADR-A-0004). Covers: union read, subtract-only, structural exception, delegated-sync honoring, SOP correction. Backward-compatible: a project with no `ownership.local.yaml` sees no change in behavior.

**No divergence between report and classifier:** A single `EXCEPTIONS_TABLE` (built once from both maps at lines 288–291) feeds `EXCEPTIONS` for `is_exception` and the fork-budget grading loop. There is no second parse that could produce a different set.

**Design adherence (system-architect pre-decided):** All five pre-decided design decisions implemented as specified — union read, `boilerplate_owned` stays SOURCE-authoritative, subtract-only enforced, `ownership.local.yaml` structural, `.claude/**` latent gap closed, SOP §3.2 corrected.

---

## Verdict

**APPROVED.** All 6 ACs pass. Both test suites green (83/83 + 5/5). Implementation matches the pre-decided design; no classifier/report divergence; no report-only invariant violation. Approved for Story Acceptance.
