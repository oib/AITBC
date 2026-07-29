# QA Validation Report — ABS-442

**Ticket:** ABS-442 — Gate `GET /api/v1/projects` with `requireDashboardRead`  
**Branch:** `ABS-442-auto`  
**Commit:** `988fde7` (`feat(api): gate GET /api/v1/projects with requireDashboardRead [ABS-442]`)  
**Validated by:** QAS  
**Date:** 2026-07-18  
**Verdict:** ✅ APPROVED

---

## Validation Summary

| Check | Result | Detail |
|---|---|---|
| `pnpm typecheck` (5 workspaces) | ✅ PASS | All workspaces clean; zero type errors |
| `eslint` on changed files | ✅ PASS | No lint errors on dashboard.ts / dashboard-routes.test.ts / AGENTIC-BACKEND-API.md |
| `dashboard-routes.test.ts` (AC3 + AC4) | ✅ **35/35 PASS** | Incl. all 3 new ABS-442 AC3 pinning tests |
| `guards.test.ts` (AC4 regression) | ✅ **14/14 PASS** | No regression on ABS-435 guard logic |
| `attention-routes.test.ts` (AC4 regression) | ✅ Included in 14/14 | No regression |
| Pre-existing failures (out of scope) | ⚠️ 8 failures confirmed pre-existing | `report-routes.test.ts` (5) + `bootstrap-promotion.test.ts` (3); ABS-442 diff touches none of these files |

---

## Acceptance Criteria Verification

### AC1 — Consumer check (gates the `#PATH_DECISION`) ✅

**QAS independent verification:**

- `git grep "api/v1/projects" ABS-442-auto -- . ':!backend/apps/server/src/routes' ':!backend/apps/web' ':!docs'`
  → Only test files hit (all call sub-paths like `/api/v1/projects/:project/board`, `/api/v1/projects/:project/attention` etc.) — **no machine-role client calls the bare `/api/v1/projects` list endpoint**.
- `git grep "listProjects\|/api/v1/projects" ABS-442-auto -- backend/apps/web/src/`
  → `backend/apps/web/src/api.ts:79 getJSON("/api/v1/projects")` is the **sole caller**.
  → `getJSON` uses `credentials: "include"` (session cookie); confirmed by `api.ts:38`.
- `backend/README.md` curl example targets `/api/v1/projects/ABS/orchestrators` (a sub-path, not the list endpoint).

**Decision: posture (A) — gate it.** ✅ Correct; no machine consumer, gating breaks nothing.

---

### AC2 — Posture documented ✅

Route doc comment (`dashboard.ts:215–223`) documents:
- Posture label: "GATED, session-only human read (ABS-442, posture A)"
- Rationale: sole consumer is the dashboard SPA via session cookie; AC1 consumer check found no machine-role enumerator
- References `requireDashboardRead` allowlist joining `/attention`, `/board`, `/inbox`, `/items/:key`
- ADR-A-0004/0005 citations

`AGENTIC-BACKEND-API.md` updated endpoint contract:
- Authentication: "human dashboard session required — `requireDashboardRead` (roles `admin`/`viewer`/`maintainer`, `via === "session"`)"
- Rejection: "Machine roles (`agent`/`orchestrator`) and human-role bearer tokens are rejected `403`"
- Error table updated: `403` added for non-human-session principal

---

### AC3 — Posture pinned by test (posture A) ✅

Three integration tests in `dashboard-routes.test.ts` (all verified green, 35/35 total):

| Test | Expected | Actual |
|---|---|---|
| agent + orchestrator sessions → `GET /api/v1/projects` | 403 | ✅ 403 |
| admin/viewer/maintainer sessions → `GET /api/v1/projects` | 200 + org projects in body | ✅ 200 |
| human-role bearer token (admin) → `GET /api/v1/projects` | 403 | ✅ 403 |

All three tests use the same session fixtures as ABS-435 (`agentSid`, `orchestratorSid`, `adminSid`, `viewerSid`, `maintainerSid`, `adminToken`). No new infrastructure added.

---

### AC4 — No regression ✅

| Suite | Count | Result |
|---|---|---|
| `guards.test.ts` | 14/14 | ✅ PASS |
| `attention-routes.test.ts` | included in 14/14 | ✅ PASS |
| `dashboard-routes.test.ts` (all, incl. ABS-435 block) | 35/35 | ✅ PASS |

ABS-435 tests (`requireDashboardRead` for `/attention`, `/board`, `/inbox`, `/items/:key`) pass unchanged. No gate logic modified — only an additional call site added to `dashboard.ts`.

---

## Pre-existing Failures (Out of Scope)

The full suite produces 8 failures, **none** attributable to ABS-442:

- `report-routes.test.ts` (5 failures): `TypeError: Cannot read properties of undefined` — present on the pre-ABS-442 tree; ABS-442 diff does NOT touch `report-routes.test.ts` or any report code.
- `bootstrap-promotion.test.ts` (3 failures): dev-boot seeding tests — pre-existing environment-state dependency; ABS-442 diff does NOT touch this file.

Both sets were confirmed pre-existing: the ABS-442 commit (`git show 988fde7 --stat`) modifies exactly 3 files: `dashboard.ts`, `dashboard-routes.test.ts`, `AGENTIC-BACKEND-API.md`.

---

## Implementation Quality Notes

- `requireDashboardRead` is the handler's **first statement** (`dashboard.ts:225`) — fail-closed before any query or logic runs.
- The guard checks BOTH `DASHBOARD_READ_ROLES.includes(principal.role)` AND `principal.via === "session"` — correctly rejects human-role bearer tokens (not just machine roles).
- `request.principal!` non-null assertion is safe: the global `onRequest` hook at `server.ts:147` rejects unauthenticated requests with 401 before routing and populates `principal`.
- No change to response shape, org-scoping (`WHERE org_id = $1`), or parameterization — exactly in-scope.

---

## Verdict

**✅ APPROVED — all four ACs met, all in-scope tests green, typecheck and lint clean. Pre-existing failures documented and out of scope. Advancing to Story Acceptance.**
