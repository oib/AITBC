# ABS-414 — Test Prep (Data Provisioning) Handoff

**Seat:** data-provisioning-eng (Test Prep) · **Branch:** `ABS-414-auto` @ `5348b29`
**Goal:** give QAS a zero-setup path to validate all 6 ACs against real data.

The ABS-414 suite (`backend/apps/server/test/usage-routes.test.ts`, 18 tests) is
**self-seeding** — every fixture, token, and session is created in its `before()`
hook. There is no external fixture file to load. The one thing the suite needs and
does not create is a **reachable Postgres** (`DATABASE_URL`); without it all 18 tests
skip green (CI fails closed per ABS-287). This note documents how to provision that DB
**inside the ABS-374 sandbox rule** so QAS runs the suite for real.

## 1. Provision a sandboxed Postgres (never the operator's live stack)

`docker-compose.yml` derives its project name from the `backend/` directory, so a bare
`docker compose up` REPLACES the operator's live containers/volume on ports 8420/5432
(ABS-374). QAS MUST use an isolated project name and a non-taboo host port:

```bash
cd backend
SBX=abs414-qas
POSTGRES_HOST_PORT=55432          # any free port that is NOT 5432/8420
POSTGRES_PASSWORD=qas_sandbox_pw  # throwaway
docker compose -p "$SBX" up -d db                         # ONLY the db service is needed
# wait for healthy:
until [ "$(docker inspect -f '{{.State.Health.Status}}' "$(docker compose -p "$SBX" ps -q db)")" = healthy ]; do sleep 2; done
```

The server itself is NOT provisioned — the tests build Fastify in-process via
`buildServer(pool)` and connect directly with `DATABASE_URL`.

## 2. Run the suite (tests EXECUTE, not skip)

```bash
export DATABASE_URL="postgres://postgres:qas_sandbox_pw@127.0.0.1:55432/agentic"
pnpm --filter @agentic-backend/server exec \
  node --import tsx --test --test-concurrency=1 test/usage-routes.test.ts
```

Migrations (incl. additive `010_budget_config.sql`) run inside `before()` against a
fresh, uniquely-named schema (`usage_test_<epoch>`), which `after()` drops — no residue.

## 3. Seeded data (created by the test's `before()` hook)

- **Telemetry** — 4 `SPAWN-USAGE` `run_event` rows: `run-A` (3 spawns, tokens_in 150 /
  out 75, cost $0.17, `occurred_at = now` → inside burn window), `run-B` (1 spawn,
  cost $0.03, `occurred_at = 2h ago` → outside burn window ⇒ idle). Two more runs
  (`run-C` unknown-model, `run-D` known-model) are seeded mid-test for AC4.
- **Epic rollup** — `work_item` epic `ABS-100` parenting tickets `ABS-1`/`ABS-2` so
  `group=epic` rolls up by the `ticket` field (not labels).
- **Budget/price config** — `budget_config` + `price_mapping` rows written through the
  PUT endpoints during AC3/AC4/AC6.

## 4. Auth / RLS test contexts (agentic-backend = Postgres pool, not Prisma-RLS)

`requireHuman` (writer role AND `via === 'session'`) is the authz gate for the two
mutating routes. The suite exercises three principals:

| Context | How it's built | Used for |
|---|---|---|
| **admin-bearer** | `createToken(pool,{orgId,projectId:null,role:'admin'})` | GET reads; proves admin-bearer is still **403** on writes (via≠session) |
| **agent-bearer** | `createToken(pool,{orgId,projectId,role:'agent'})` | AC5 — **403** on `PUT /budget` and `PUT /price-mapping` |
| **admin-session** | `POST /api/v1/session` with the admin bearer → opaque `session=` cookie | the only principal allowed to write (AC5 200) |

Every query is tenant-scoped by `org_id`/`project_id` off the authenticated principal;
the `:project` URL param is echoed, never trusted for scoping.

## 5. Verified result (this seat, sandboxed run 2026-07-18)

- **ABS-414 suite: 18/18 pass, skipped 0** (they truly executed against Postgres).
- **Pre-existing failures — NOT ABS-414 regressions, do not count against this story:**
  `report-routes.test.ts` (5/5 fail) and `bootstrap-promotion.test.ts` (3/4 fail).
  Confirmed pre-existing: commit `5348b29` adds only `usage.ts`, `server.ts` (+4 lines),
  `usage-routes.test.ts`, `010_budget_config.sql` — it touches **no** report/bootstrap/
  auth/guards code. These fail on the baseline (auth regression predating ABS-414).

## 6. Cleanup (mandatory — no container/volume leak)

```bash
docker compose -p "$SBX" down -v
```
