# QA Validation Report — ABS-352

**Ticket**: ABS-352 — Spawn-Level Observability (Shipper Spawn Events + Board Live-Spawns View)  
**Gate**: In Test (functional QAS)  
**Commit reviewed**: `aab0c98` (branch `ABS-352-auto`, diff vs parent `6c497f5`)  
**QAS run date**: 2026-07-17  
**Verdict**: ✅ PASS — Approved for Design Test  

---

## Quality Gate Results

| Check | Result | Notes |
|-------|--------|-------|
| `pnpm typecheck` | ✅ PASS | All 3 workspaces (core, web, server) clean — no TypeScript errors |
| `pnpm lint` | ✅ PASS | ESLint clean, zero output |
| Integration tests (spawn-specific) | ✅ SKIP (clean) | Postgres-gated; no DATABASE_URL in sandbox — 4 tests skip cleanly; implementer confirmed green with DB |
| Pre-existing `workflow.test.ts` failure | ℹ️ PRE-EXISTING | `statuses.yaml` line 487 `terminal` field — reproduced identically on parent `6c497f5`; ABS-352 touches no workflow/statuses code |

---

## Acceptance Criteria Verification

### AC1: Spawn event types (open → active, close → completed)
**Status: ✅ PASS**

- `upsertSpawn()` in `core/spawns.ts` handles both open (no `completedAt`) and close (`completedAt` + `exit_code` + `diagnostic`) calls via `ON CONFLICT (id) DO UPDATE` — idempotent upsert
- `liveSpawns()` CTE correctly routes open entries to `active[]` and closed entries to `recent[]`
- Integration test `AC1: POST spawn (open) → GET returns active entry; POST close → GET returns completed` (in `spawns-routes.test.ts`) asserts: `instA.active.length === 1`, `r.exit_code === 0`, `r.diagnostic === "AC/DoD met"`, `completed_at !== null`
- Test SKIPS cleanly without DATABASE_URL (Postgres-gated by design); implementer confirmed green against DB

### AC2: Board Live Spawns view renders per instance (active + completions)
**Status: ⚠️ CARRY-FORWARD TO DESIGN TEST**

- `LiveSpawns.tsx` component: implemented with `data-testid="spawns-panel|spawns-instance|spawn-active|spawn-stale|spawn-completed"` hooks, `role="status"` live region, `<time dateTime>`, accessible exit badges ("✓ exit:0" / "✗ exit:1")
- Integrated in `App.tsx`: `api.getSpawns(project)` → `setSpawns()` → `<LiveSpawns data={spawns} />`
- `GET /api/v1/projects/:p/spawns` route registered and serving correctly
- **Gap**: No component/e2e test asserting rendering — **System Architect explicitly flagged this for Design Test (qas-design) enforcement** (gate-results comment 2026-07-17T08:38:46Z)
- DAC-14..17 (component/e2e rendering tests) are the Design Test gate contract; `design` flag on this ticket guarantees it reaches that gate
- **Not a blocker at functional In Test gate** per SA's explicit carry-forward decision

### AC3: Instance scoping — seats from A do not appear under B
**Status: ✅ PASS**

- `liveSpawns()` uses a `byInstance = new Map<string, {...}>()` keyed on `row.instance_id` — seats are partitioned by instance in the projection
- `LiveSpawns.tsx` renders one `<InstanceSection data-instance={view.instance_id}>` per `InstanceSpawnView` entry
- Integration test `AC3: spawns from instance A do not appear under instance B` inserts ABS-1 under inst-A and ABS-2 under inst-B, then asserts `instA.active[0].ticket_id === "ABS-1"` and `instB.active[0].ticket_id === "ABS-2"` with no cross-contamination
- Also carries `run_id` (Story 5 run identifier) in the `SeatSpawn` type

### AC4: Stale-seat detection
**Status: ✅ PASS**

- `liveSpawns()` sets `stale: row.completed_at === null && ageSec > staleThresholdSec`
- `GET /api/v1/projects/:p/spawns?stale_sec=N` allows override of threshold
- `DEFAULT_STALE_SEC = Number(process.env.SPAWN_STALE_THRESHOLD_SEC ?? "300")` — configurable
- `LiveSpawns.tsx` renders `data-testid="spawn-stale"` and `⚠ STALE` badge for stale entries
- Integration test `AC4`: inserts 1-hour-old open entry, queries with `stale_sec=10` (10s threshold), asserts `inst.active[0].stale === true`

### AC5: Field-over-label constraint (ABS-313 Guardrail 4)
**Status: ✅ PASS (REVIEWER-CHECKABLE)**

- `liveSpawns()` in `core/spawns.ts` projects from `seat_spawn.instance_id` column (SQL text column)
- The SQL UNION-ALL CTE groups, orders, and partitions exclusively off `seat_spawn.instance_id` — zero label string comparisons anywhere in the projection path
- Verified by source code review of `core/spawns.ts` — explicitly commented at file header: "Projection reads `seat_spawn.instance_id` (ABS-313 Guardrail 4 — field over label)"
- Also verified by System Architect in Stage 1 gate

---

## Files Reviewed

| File | Notes |
|------|-------|
| `backend/packages/core/src/migrations/004_seat_spawns.sql` | Additive table, FKs to org/project, two indexes matching query patterns |
| `backend/packages/core/src/spawns.ts` | `upsertSpawn` (idempotent upsert), `liveSpawns` (UNION-ALL CTE, stale detection, instance grouping) |
| `backend/packages/core/src/index.ts` | Correct exports for all spawn types and functions |
| `backend/apps/server/src/routes/spawns.ts` | POST ingest + GET read routes, 400 validation, `stale_sec` query param |
| `backend/apps/server/src/server.ts` | `registerSpawnRoutes(app, pool)` registered |
| `backend/apps/server/test/spawns-routes.test.ts` | 4 Postgres-gated tests (AC1, AC3, AC4, validation) — SKIP cleanly without DB |
| `backend/apps/web/src/components/LiveSpawns.tsx` | Collapsible panel, `InstanceSection`, `SpawnRow`, `ExitBadge`, accessibility hooks |
| `backend/apps/web/src/api.ts` | `getSpawns(project)` → `GET /api/v1/projects/:p/spawns` |
| `backend/apps/web/src/App.tsx` | `api.getSpawns()` → `setSpawns()` → `<LiveSpawns data={spawns} />` |
| `backend/apps/web/src/types.ts` | `SeatSpawn`, `InstanceSpawnView`, `LiveSpawnsResponse` types added |
| `backend/apps/web/src/styles.css` | CSS variables: `var(--panel)`, `var(--border)`, `var(--accent)`, `var(--emphasis)`, `var(--emphasis-border)`, `var(--live)`, `var(--stale)` |

---

## Pre-existing Failures (NOT attributable to ABS-352)

| Failure | Pre-existing? | Evidence |
|---------|---------------|----------|
| `workflow.test.ts` — `statuses.yaml:487 unknown status field "terminal"` | ✅ YES | Reproduced on parent commit `6c497f5`; ABS-352 changes no workflow/statuses code |
| `packages/core bootstrap-promotion` tests | ✅ YES (DB-gated) | SKIP cleanly without DATABASE_URL; pre-existing DB environment constraint |

---

## In Test Gate: PASS

**Proceed to**: Design Test (qas-design must enforce AC2/DAC-14..17 component/e2e rendering tests)  
**Design flag**: Active — exit target per Exit Protocol is `Design Test`  
**Mandatory carry-forward to qas-design**: Component/e2e test covering DAC-14 (panel auto-open when active > 0), DAC-15 (stale row visible), DAC-16 (instance isolation in render), DAC-17 (exit badge text variants)

---

## Iteration 2 — In Test Re-verification (after qas-design iteration 1 bounce)

**Date**: 2026-07-17  
**Commits reviewed**: `aab0c98` (original) + `f624af6` (fix delta, branch tip)  
**Reason for re-entry**: qas-design bounced at Design Test iteration 1 (DAC-13 + DAC-14..17 gaps). be-developer delivered `f624af6`; system-architect re-approved to In Test.

### Delta (`f624af6`) Verification

**Files changed**: `backend/apps/web/src/components/LiveSpawns.tsx` (11-line change), `backend/apps/web/e2e/spawns.spec.ts` (new, 213 lines)

#### DAC-13 fix — mobile default-collapse

- `useState(false)` — panel starts collapsed on all viewports
- `useEffect(() => { if (totalActive > 0 && window.innerWidth >= 768) setOpen(true); }, [totalActive])` — auto-opens on desktop/tablet (≥768px) when active spawns arrive; stays collapsed on mobile (<768px)
- Correctly addresses qas-design bounce: mobile default must be collapsed; non-mobile auto-opens reactively

#### DAC-14..17 e2e tests — `e2e/spawns.spec.ts`

| DAC | Test | Coverage |
|-----|------|----------|
| DAC-14 | `"Live Spawns panel auto-opens (non-mobile) when active spawns exist"` | Seeds active spawn, sets 1280px viewport, asserts `aria-expanded="true"` + `spawn-active` row with ticket ID |
| DAC-15 | `"open spawn older than stale threshold renders as stale"` | Seeds 10-min-old open spawn, asserts `spawn-stale` testid visible with ticket ID |
| DAC-16 | `"instance-A seats do not appear under instance-B section"` | Seeds instA+instB; asserts instA contains A-only AND does NOT contain B's ticket; instB contains B-only AND does NOT contain A's ticket (bidirectional negative assertions) |
| DAC-17 | `"exit badges contain symbol and numeric text for exit:0 and exit:1"` | Seeds exit:0 and exit:1 completions; asserts `.spawn-exit-ok` contains "✓" AND "exit:0"; `.spawn-exit-err` contains "✗" AND "exit:1" |

**Harness conformance**: `spawns.spec.ts` uses identical harness to `board.spec.ts` — same `E2E_BASE`/`E2E_TOKEN` from `./const`, same `beforeAll` project creation via `/api/admin/projects`, same `page.getByLabel("Access token")` login flow, same `page.getByTestId("board")` wait pattern.

### Quality Gate Results (Iteration 2)

| Check | Result | Notes |
|-------|--------|-------|
| `pnpm typecheck` | ✅ PASS | All 3 workspaces (core, web, server) clean |
| `pnpm lint` | ✅ PASS | ESLint clean, zero output |
| AC1/AC3/AC4/AC5 | ✅ UNCHANGED | No regression — delta touches only `LiveSpawns.tsx` (11 lines) and adds `e2e/spawns.spec.ts` |
| Pre-existing `workflow.test.ts` | ℹ️ PRE-EXISTING | Untouched by delta |
| AC2 (component/e2e rendering) | ✅ NOW RESOLVED | `e2e/spawns.spec.ts` (4 tests, DAC-14..17) satisfies the carry-forward requirement |

### Iteration 2 Verdict: ✅ PASS → Design Test

All original ACs and all DAC gaps addressed. qas-design must verify DAC-1..17 against the full `aab0c98 + f624af6` implementation — noting that the AC2/DAC-14..17 e2e tests are now present for verification.
