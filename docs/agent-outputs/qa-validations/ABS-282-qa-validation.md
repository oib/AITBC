# QA Validation Report — ABS-282

**Ticket**: ABS-282 — Backend: dev-default bootstrap token survives promotion — revoke org-wide admin residue on non-dev boot  
**QAS run date**: 2026-07-14  
**Branch**: `ABS-282-auto`  
**Commit under review**: `8b84d3c`  
**Verdict**: ✅ **APPROVED**

---

## Gate Execution Summary

All three mandatory gates re-run independently by QAS against live Postgres 16
(`backend/docker-compose.yml`, `DATABASE_URL=postgres://postgres:postgres@localhost:5432/agentic`).
Tests were **not taken on trust** from prior seat reports — this is a security ticket whose
predecessor (ABS-262) shipped with 0 DB-gated tests executing, so independent re-verification
is mandatory.

| Gate | Result | Evidence |
|------|--------|----------|
| `pnpm -r test` (live Postgres) | ✅ PASS | 46/46 pass, **skipped 0** |
| `pnpm typecheck` | ✅ PASS | exit 0, no errors |
| `pnpm lint` | ✅ PASS | exit 0, no output |

### Live Postgres test breakdown

```
packages/core  tests 35  pass 35  fail 0  skipped 0
apps/server    tests 11  pass 11  fail 0  skipped 0
```

**Key verification**: The 4 promotion tests in `apps/server/test/bootstrap-promotion.test.ts`
all EXECUTED (not skipped). These are the tests that encode the defect directly:
- `(1) dev boot seeds the dev default, and it authenticates (AC5)` → **PASS** (175.7ms)
- `(2) non-dev boot on the SAME DB revokes the residue (AC1, AC2, AC3)` → **PASS** (4.4ms)
- `(3) a second non-dev boot is a clean no-op (AC4)` → **PASS** (3.1ms)
- `fresh DB, non-dev boot: seeds exactly one row, never the dev default` → **PASS** (52.1ms)

The skip gate (`{ skip: !BASE_URL }`) was not triggered — `DATABASE_URL` was set for all tests.

---

## Acceptance Criteria Verification

| # | Criterion | Result | Notes |
|---|-----------|--------|-------|
| AC1 | dev-seeded DB + non-dev boot → dev default REJECTED 401 | ✅ MET | Test (2): `authStatus(DEV_BOOTSTRAP_TOKEN) === 401` (was 200 before fix) |
| AC2 | No dev-default `auth_token` row remains after non-dev boot | ✅ MET | Test (2): `devDefaultRows === 0` against live Postgres |
| AC3 | Strong token authenticates; revocation logged without token value | ✅ MET | Test (2): `authStatus(STRONG_TOKEN) === 200`; `index.ts` log: row count only, no token string |
| AC4 | Idempotent: second non-dev boot revokes 0 rows, boots normally | ✅ MET | Test (3): `revokedDevDefault === 0`, both auth assertions hold |
| AC5 | Dev unchanged: default seeded, continues to authenticate | ✅ MET | Test (1): `revokedDevDefault === 0`, `authStatus(DEV_BOOTSTRAP_TOKEN) === 200` |
| AC6 | Promotion path tested against live Postgres (not skipped) | ✅ MET | `bootstrap-promotion.test.ts` executed fully, 0 skipped (verified independently) |
| AC7 | Gates green: `pnpm -r test`, `pnpm typecheck`, `pnpm lint` | ✅ MET | All three pass (see above) |

**All 7 ACs met.**

---

## Definition of Done Verification

- [x] All ACs met (see above)
- [x] Promotion path proven against **live Postgres** — not only unit tests. The defect is
  a DB-state defect and cannot be seen from a pure unit test; this requirement is satisfied.
- [x] `pnpm lint` green
- [x] `pnpm typecheck` green

---

## Implementation Quality Notes

### Seed-then-revoke ordering (no-lockout guarantee)
The ordering is correct AND provably safe for a deeper reason: `loadConfig` (already enforced
by ABS-262) throws outside dev when `bootstrapToken === DEV_BOOTSTRAP_TOKEN`, so
`hashToken(config.bootstrapToken) != hashToken(DEV_BOOTSTRAP_TOKEN)` is invariant. The DELETE
cannot target the row just seeded. The ordering then adds crash-safety on top. Both halves hold.

### `isDevEnv` is an allowlist (fail-closed)
The security reviewer verified (and QAS confirmed in the test suite) that `isDevEnv` is an
explicit allowlist of dev markers, not a denylist of production/staging. This means:
- `NODE_ENV=""`, `"staging"`, `"development-staging"`, `"devel"` all resolve non-dev → revoke.
- **An operator who forgets `NODE_ENV` entirely still revokes the dev default.** This is the
  fail-closed property the fix must have.

### `001_init.sql` pg_trgm SCHEMA public
The SQL edit is `IF NOT EXISTS`-guarded, and `migrate.ts` keys `schema_migrations` on filename
only (no checksum), so the edit never causes a re-run on already-migrated databases. The reason
for the edit is valid: without a schema specifier the extension lands in the first schema of
`search_path`, breaking multi-schema test isolation. Confirmed safe as documented by the
System Architect.

### `BootstrapResult` replacing `boolean`
`ensureBootstrapToken` now returns `{ seeded, revokedDevDefault }` instead of `boolean`. This
is a justified API expansion: the boot seam needs two distinct outcomes to reach the log line.
No over-engineering; the extra field is directly consumed by `index.ts`.

---

## Items Carried Forward (non-blocking)

These were surfaced by prior seats and are correctly out of scope for this ticket:

1. **ABS-281** (`.env.example`/compose dev-artifact hardening) — currently `In Progress`.
   ABS-281 and ABS-282 are jointly necessary to fully close the promotion hole. ABS-282 alone
   handles the DB-state residue; ABS-281 handles the `cp .env.example .env` dev-mode risk.
   Status: tracked, not a QAS bounce criterion.

2. **Migration runner checksum gap** — `schema_migrations` keys on filename only, so migration
   drift is undetectable class-wide. Flagged by Security Engineer for a follow-up ticket on
   epic ABS-278. Not a defect in this story; no bounce.

---

## Exit

No `design` flag on this ticket → exit target is **Story Acceptance**.

**Verdict: APPROVED. Transitioning ABS-282 → Story Acceptance.**
