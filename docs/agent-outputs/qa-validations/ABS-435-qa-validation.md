# QA Validation Report — ABS-435

**Ticket**: ABS-435 — Harden dashboard read surface: shared fail-closed `requireDashboardRead` allowlist  
**Branch**: `ABS-435-auto`  
**Commit reviewed**: `93b0276`  
**Base**: stacked on ABS-411 `be29552`  
**QAS run date**: 2026-07-18  
**Verdict**: ✅ **APPROVED**

---

## Validation Environment

| Item | Value |
|---|---|
| Worktree | `/tmp/ABS-435-work` |
| TypeScript check | `pnpm typecheck` EXIT_CODE=0 |
| ESLint | `npx eslint` on 4 changed files EXIT_CODE=0 |
| Unit suite | `guards.test.ts` — 5/5 PASS (no DB needed) |
| Integration suite | `guards.test.ts` + `dashboard-routes.test.ts` + `attention-routes.test.ts` — **46/46 PASS** against live Postgres `localhost:5432` |
| Pre-existing failures | `report-routes.test.ts` + `bootstrap-promotion.test.ts(AC4)` — confirmed pre-existing at base `c047775` (ABS-411 worktree), NOT introduced here |

---

## AC Matrix

### AC1 — Shared fail-closed allowlist in `guards.ts`; out-of-allowlist role → 403

**Status**: ✅ PASS

- `DASHBOARD_READ_ROLES = ["admin", "viewer", "maintainer"]` in `guards.ts`.
- `requireDashboardRead` checks `DASHBOARD_READ_ROLES.includes(principal.role)` — allowlist, not denylist.
- Unit test `"AC1: an out-of-allowlist role (future machine role) is REJECTED 403"` asserts `"future-machine"` role → 403 and `ok === false`. This is the decisive gap-(a) regression guard that a denylist would miss.
- Unit test `"AC1: machine roles agent + orchestrator are rejected 403"` asserts both roles → 403.

```
✔ AC1: an out-of-allowlist role (future machine role) is REJECTED 403, not admitted (1.30ms)
✔ AC1: machine roles agent + orchestrator are rejected 403 (0.07ms)
```

### AC2 — All four read routes use shared helper; agent + orchestrator → 403

**Status**: ✅ PASS

Call sites in `dashboard.ts` verified independently:
- `/board` → line 229: `if (!requireDashboardRead(request.principal!, reply)) return reply;`
- `/items/:key` → line 246: `if (!requireDashboardRead(p, reply)) return reply;`
- `/inbox` → line 342: `if (!requireDashboardRead(request.principal!, reply)) return reply;`
- `/attention` → line 590: `if (!requireDashboardRead(request.principal!, reply)) return reply;`

Integration test confirms machine principals get 403 on every route:
```
✔ ABS-435 AC2: agent + orchestrator sessions are 403 on EVERY read route (9.5ms)
```

### AC3 — Human dashboard-role sessions → 200 on each read route

**Status**: ✅ PASS

`admin`, `viewer`, `maintainer` sessions all admitted across all four routes:
```
✔ ABS-435 AC3: human dashboard sessions (admin/viewer/maintainer) are 200 on EVERY read route (36.4ms)
```

Note: `viewer` is present in `DASHBOARD_READ_ROLES` but absent from `WRITER_ROLES` — the read allowlist is correctly a superset of writers (unit test asserts this explicitly).

### AC4 — `via` posture documented and pinned by test (session-only)

**Status**: ✅ PASS

`#PATH_DECISION` documented in the `requireDashboardRead` doc comment in `guards.ts`:
> "`via` posture — SESSION-ONLY (#PATH_DECISION, ABS-435): … A human-role bearer token is therefore rejected 403 — pinned by test so it cannot silently drift (AC4)."

Tests pin the posture:
```
✔ AC4: session-only posture — a human-role BEARER token is rejected 403 (0.04ms)      [unit]
✔ ABS-435 AC4: session-only posture — a human-role BEARER token is 403 on every read route (3.7ms)  [integration]
```

The decision to match the write surface (session-only) is well-reasoned: one uniform read+write posture for a single auditable authorization boundary per ADR-A-0004/0005.

### AC5 — ABS-411 attention tests pass unchanged

**Status**: ✅ PASS

All 9 ABS-411 attention tests run and pass:
```
✔ AC1: endpoint returns counters + all item types with correct source refs (252.96ms)
✔ AC2: items are oldest-first and deduplicated (4.58ms)
✔ AC3: transitioning item out of Blocked removes it from attention on next fetch (12.48ms)
✔ AC4: response shape is stable — known type values are present in items (2.62ms)
✔ AC5: unauthenticated request → 401 (0.33ms)
✔ AC5: agent token → 403 (1.64ms)
✔ AC5: orchestrator token → 403 (1.16ms)
✔ AC5: admin session → 200 (2.46ms)
✔ AC5: agent with bearer token (no session) → 403 (1.21ms)
```

The ABS-411 inline denylist at `/attention` has been correctly replaced by the shared `requireDashboardRead` allowlist without behavioral regression.

---

## Pre-Existing Failures (Not Introduced by ABS-435)

| Test File | Failures | Confirmed Pre-Existing |
|---|---|---|
| `report-routes.test.ts` | 5 failures | ✅ Confirmed at base `c047775` (ABS-411 worktree) |
| `bootstrap-promotion.test.ts` | AC4 `403 !== 200` | ✅ Confirmed at base `c047775` (ABS-411 worktree) |

These are environmental failures requiring a pristine DB schema. The `bootstrap-promotion` AC4 failure was investigated: it hits `/agent/v1/projects/ANY/whoami` (not a dashboard route) and is a DB state isolation issue pre-dating this ticket.

---

## Additional Verification

- **Import**: `dashboard.ts` correctly imports `{ requireDashboardRead, requireHuman }` from `./guards.js`.
- **Gate placement**: The helper is the **first statement** in each handler — authz runs before any project resolution or data access, preventing enumeration leaks on 403.
- **Error shape**: Uniform `403 { error: "forbidden" }` + `return false`, consistent with `requireHuman`.
- **ABS-333 probe re-point**: `bearer /board → GET /api/v1/session` (whoami) — preserves the test's intent (session revoke ≠ token disable) under the new session-only read posture. Confirmed correct.

---

## Security Flag Verification

Both upstream security gates have passed:
- **system-architect** (Stage 1): APPROVED — guards unit 5/5, pattern-faithful, all four routes gated.
- **security-engineer** (Stage 2): PASS — independent audit, no blocking findings, 5/5 guards unit, source-verified call sites, one non-blocking follow-up filed for BSA (`GET /api/v1/projects` project-selector read — confirmed out of scope, not a vulnerability).

QAS independently confirms all security-engineer findings. No gaps.

---

## Summary

All 5 acceptance criteria met. TypeCheck + ESLint clean. **46/46 tests PASS** (guards unit + dashboard integration + attention integration, live Postgres). Pre-existing failures confirmed not introduced by this commit. The implementation is a clean, minimal, pattern-faithful security hardening — a direct twin of `requireHuman` applied to the read surface.

**Final verdict: APPROVED**  
**Next gate: Story Acceptance** (no `design` flag)
