# QA Validation Report — ABS-480

**Ticket**: ABS-480 — Renumber duplicate 011 migration prefix (migrate-prefix-guard RED on main)
**QAS Actor**: qas
**Date**: 2026-07-19
**Commit under review**: `33d5f2a100f0513f4f314f0e70178b91c929fd16`
**Branch**: ABS-480-auto
**Verdict**: ✅ APPROVED

---

## Acceptance Criteria — Verification

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| 1 | `migrate-prefix-guard.test.ts` passes: `findDuplicateMigrationPrefixes(files)` returns `[]` | ✅ PASS | 4/4 green — all tests pass incl. "real migration series carries no ungrandfathered duplicate prefix" |
| 2 | Second-merged migration renumbered to next free prefix (`014_seat_spawn_id_text.sql`) | ✅ PASS | `011_seat_spawn_id_text.sql` → `014_seat_spawn_id_text.sql`; 012/013 already on main, so 014 is correct next-free |
| 3 | SQL content byte-identical (only filename prefix changed) | ✅ PASS | MD5 `945042a28517fd7567af2db689d255ef` on both the pre-commit 011 and current 014 file; `git show --stat` reports `\| 0` |
| 4 | Migrations apply cleanly and in order on fresh DB | ✅ PASS | `migrate.test.ts` 7/7 GREEN on fresh ephemeral sandboxed Postgres (abs480qas / port 55481, ABS-374 compliant, `down -v` teardown verified) |
| 5 | No wire/schema/behaviour change; grandfather list unchanged | ✅ PASS | `GRANDFATHERED_DUPLICATE_PREFIXES = new Set(["004"])` — `011` NOT added; pure rename + 1-line test-array update |

---

## Test Run Evidence

### Gate 1: migrate-prefix-guard.test.ts (no DB)

```
command: node --import tsx --test --test-concurrency=1 test/migrate-prefix-guard.test.ts
commit:  33d5f2a100f0513f4f314f0e70178b91c929fd16

✔ real migration series carries no ungrandfathered duplicate prefix (2.561792ms)
✔ simulated collision goes RED (guard detects a new duplicate) (0.143709ms)
✔ grandfathered 004 pair does not trip the guard (0.050125ms)
✔ non-.sql and unnumbered files are ignored (0.065291ms)
ℹ tests 4 | pass 4 | fail 0 | skipped 0
```

### Gate 2: migrate.test.ts (fresh ephemeral DB — abs480qas / port 55481)

```
command: DATABASE_URL="postgres://postgres:<pw>@localhost:55481/agentic" \
         node --import tsx --test --test-concurrency=1 test/migrate.test.ts
commit:  33d5f2a100f0513f4f314f0e70178b91c929fd16

✔ first run applies every migration in order; all §2 tables exist (171.415958ms)
✔ bigserial + generated tsvector + GIN indexes are present (AC#2) (5.789583ms)
✔ second run is a no-op — idempotent (AC#1) (2.783584ms)
✔ AC#5: priority defaults to 'normal' when unset (3.338917ms)
✔ AC#5: every operator-specified priority value is accepted (4.635166ms)
✔ AC#5: an invalid priority is rejected by the enum (1.774666ms)
✔ AC#5: priority is NOT NULL and indexed (5.60025ms)
ℹ tests 7 | pass 7 | fail 0 | skipped 0
```

### Gate 3: TypeScript check

```
command: npx tsc --noEmit (backend/packages/core)
result:  PASS — no output (clean)
```

### Gate 4: Lingering-reference sweep

```
command: git grep -r "011_seat_spawn" -- .
result:  NO_REFERENCES_FOUND
```

### Gate 5: SQL byte-identity

```
MD5 of pre-commit 011_seat_spawn_id_text.sql: 945042a28517fd7567af2db689d255ef
MD5 of current  014_seat_spawn_id_text.sql:   945042a28517fd7567af2db689d255ef
Commit diffstat: {011_seat_spawn_id_text.sql => 014_seat_spawn_id_text.sql} | 0
```

---

## Additional Checks

- **Migration series on disk** (sorted): `001`, `002`, `003`, `004`×2 (grandfathered), `005`–`011`, `012`, `013`, `014` — no ungrandfathered duplicates.
- **Grandfather list**: `GRANDFATHERED_DUPLICATE_PREFIXES = new Set(["004"])` — `011` not added (renumbered, not grandfathered; per scope).
- **`migrate.test.ts` expected order**: array correctly ends `"011_command_reason_length.sql", "012_budget_config.sql", "013_seat_heartbeat.sql", "014_seat_spawn_id_text.sql"`.
- **Sandboxed DB teardown**: `docker compose -p abs480qas down -v` — containers + volume confirmed removed, no leftover state.

---

## Verdict

**APPROVED** — All 5 acceptance criteria verified independently. Guard green (4/4), fresh-DB apply-in-order green (7/7), SQL byte-identical (MD5 match), no lingering references, grandfather set `{"004"}` unchanged, `011` not grandfathered.

**No `design` flag** → exit to `Story Acceptance`.

