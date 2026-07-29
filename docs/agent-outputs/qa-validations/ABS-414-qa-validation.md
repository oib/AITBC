# QA Validation Report — ABS-414

**Ticket:** ABS-414 — Cost/Usage Aggregation + Budget Config with Edge-Triggered Breach Events
**Branch:** `ABS-414-auto`
**Commits under review:** `5348b29` (implementation), `6a20a69` (test-prep docs)
**QAS Seat Run:** 2026-07-18
**Verdict:** ✅ APPROVED

---

## Test Execution

**Suite:** `backend/apps/server/test/usage-routes.test.ts` (18 tests)
**Environment:** Sandboxed Postgres `abs414-qas` (host port 55432, isolated project — ABS-374 sandbox rule honored)
**DATABASE_URL:** `postgres://postgres:qas_sandbox_pw@127.0.0.1:55432/agentic`
**Command:**
```bash
DATABASE_URL=postgres://postgres:qas_sandbox_pw@127.0.0.1:55432/agentic \
  pnpm --filter @agentic-backend/server exec \
  node --import tsx --test --test-concurrency=1 test/usage-routes.test.ts
```

### Result: 18/18 PASS, 0 skipped, 0 fail

```
✔ AC1: group=run returns correct token and dollar totals per run (250ms)
✔ AC1: group=seat returns per-role totals (2ms)
✔ AC1: group=day returns per-day totals (2ms)
✔ AC1: group=epic rolls ABS-1/ABS-2 under ABS-100 (2ms)
✔ AC1: unknown group returns 400 (1ms)
✔ AC2: burn rate is non-zero for run with recent events (3ms)
✔ AC2: burn rate is idle (0) for run with no recent events (2ms)
✔ AC2: burn rate with no run_id auto-selects most recent run (2ms)
✔ AC3: warning emitted exactly once; exceeded exactly once; re-arm re-triggers (23ms)
✔ AC4: events with tokens but no cost_usd and unknown model → incomplete=true (2ms)
✔ AC4: known model with price_mapping → cost computed, incomplete=false (5ms)
✔ AC5: PUT /budget returns 403 for agent bearer token (1ms)
✔ AC5: PUT /budget returns 403 for admin bearer token (via=bearer, not session) (1ms)
✔ AC5: PUT /price-mapping returns 403 for agent bearer token (1ms)
✔ AC5: PUT /budget succeeds for admin session (2ms)
✔ AC6: budget config persists across a new pool connection (6ms)
✔ AC6: price_mapping persists across a new pool connection (7ms)
✔ AC6: migration is additive — 010_budget_config.sql creates both tables without touching 001-009 (2ms)

ℹ tests 18 | pass 18 | fail 0 | skipped 0 | duration 669ms
```

---

## Typecheck

```
pnpm typecheck → PASS (all 5 workspace packages: core, server, web, forge, webhooks)
```

## Lint

```
pnpm lint → PASS (no violations)
```

---

## AC/DoD Verification

| AC | Criterion | Result | Evidence |
|----|-----------|--------|----------|
| AC1 | Deterministic token/$ totals per run/epic/seat/day for seeded fixture | ✅ PASS | 5 tests: `run-A` spawns=3, tokens_in=150, tokens_out=75, cost_usd≈0.17; `run-B` cost≈0.03; seat/day/epic groupings verified |
| AC2 | Burn rate non-zero for active run; idle=0 for no recent events | ✅ PASS | `run-A` (recent events) → `idle=false`, tokens_per_hour>0; `run-B` (2h ago) → `idle=true`, tokens_per_hour=0 |
| AC3 | Edge-triggered: exactly one BUDGET-WARNING, exactly one BUDGET-EXCEEDED; re-arm on budget raise | ✅ PASS | Verified: warning@1×, exceeded@1×, no re-emit without raise, re-arm→2nd warning emitted |
| AC4 | Unknown model ids → `incomplete=true`; no silent zero-cost | ✅ PASS | `run-C` (unknown-model-xyz, no price mapping) → `incomplete=true, cost_usd=0`; `run-D` (known-model with price mapping) → `incomplete=false, cost_usd≈3.00` |
| AC5 | 403 for agent bearer tokens on PUT /budget and PUT /price-mapping | ✅ PASS | agent bearer→403; admin bearer→403 (via≠session); admin session→200 |
| AC6 | Budget config/price mapping persists in Postgres; migration additive (009 untouched); restart-survival | ✅ PASS | Fresh pool connection reads back budget_usd=42.0, warning_pct=90; price mapping persists; tables `budget_config`+`price_mapping` confirmed in schema via information_schema; git show 5348b29 confirms 001-009 untouched |

---

## Pre-existing Failures (Baseline Regressions — NOT counted against ABS-414)

| Suite | Failures | Root cause |
|-------|----------|------------|
| `report-routes.test.ts` | 5/5 fail | Pre-existing auth regression (TypeError on undefined `length`/`script`); commit `5348b29` touches no report/auth code |
| `bootstrap-promotion.test.ts` | 3/4 fail | Pre-existing auth regression; commit `5348b29` touches no bootstrap/auth/guards code |

Confirmed: `git show 5348b29 --name-only` shows only `usage.ts`, `server.ts` (+4 lines), `usage-routes.test.ts`, `010_budget_config.sql` changed.

---

## Security Flag Review (AC5 / `flags: [security]`)

- `requireHuman` guard from `routes/guards.ts` (ABS-413) applied to both PUT endpoints.
- Guard checks `via === 'session'` AND `role IN ('admin','maintainer')`.
- All tenant-scoped queries use `org_id`/`project_id` from authenticated principal (not URL params) — no cross-tenant read path.
- No new auth surface introduced (pattern mirrors `dashboard.ts`/`report.ts`).

## Data Flag Review (AC6 / `flags: [data]`)

- Migration `010_budget_config.sql` is additive — creates `budget_config` and `price_mapping` tables.
- Migrations `001`–`009` are untouched (confirmed via `git show 5348b29`).
- Next migration index `010` is correct (verified: `009_knowledge_adr_policy.sql` is the last existing).
- Rollback clause present: `DROP TABLE budget_config; DROP TABLE price_mapping;`
- Partial unique indexes correctly handle NULL `scope_id` (standard UNIQUE would not).

---

## Sandbox Cleanup

```bash
docker compose -p abs414-qas down -v  # ✅ CONFIRMED — no container/volume leak
```

---

## Final Verdict

**APPROVED** — All 6 ACs verified PASS against real Postgres. Typecheck PASS. Lint PASS. Migration additive and correct. Security authz surface correctly gated by `requireHuman`. No regressions introduced by ABS-414.

**Handoff:** `Approved for RTE`
