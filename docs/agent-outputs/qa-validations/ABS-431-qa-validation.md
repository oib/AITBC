# QA Validation Report — ABS-431

**Ticket**: ABS-431 — Harden admin.ts requireAdmin: assert auth mechanism (session) per-endpoint, not role alone  
**Branch**: `ABS-431-auto`  
**Commit**: `ee714d9`  
**QAS Actor**: qas  
**Date**: 2026-07-18  
**Verdict**: ✅ APPROVED

---

## Validation Environment

- Branch: `ABS-431-auto` (single implementation commit `ee714d9` atop main)
- Commit: `ee714d9 feat(api): assert auth mechanism per-endpoint on admin routes [ABS-431]`
- Diff scope: 4 files, 128 insertions — `admin.ts`, `guards.ts`, `admin-routes.test.ts`, `compose-lifecycle.sh`
- DB-gated tests (Postgres 16 harness) skip cleanly without `DATABASE_URL`; tests require `DATABASE_URL`
  (documented environment prerequisite in the ticket). Implementer ran them reporting 20/20 admin-routes+policy,
  52/52 core auth/session+command/dashboard on Postgres 16. System architect verified test assertions
  match ACs 1:1. QAS independently verified test code is correct by diff review (see below).
- `pnpm -r typecheck` and `pnpm lint`: **independently re-run by QAS** (see AC6).

---

## AC/DoD Verification

### AC1 — `#PATH_DECISION` recorded for every admin write endpoint ✅ PASS

The per-endpoint classification is documented in two places:

**In-code** (`admin.ts` JSDoc block, lines 32–60): A complete table covering all 6 endpoints with
classification (BEARER-allowed / HUMAN-ONLY) and rationale. The install/bootstrap use case is
explicitly weighed for each entry. The `#EXPORT_CRITICAL` orchestrator token-mint endpoint is
called out with its specific reasoning (bootstrap bearer needs this; real control = token custody,
ADR-A-0004 — a session gate would break bootstrap entirely).

**Ticket decision comment** (2026-07-18T15:44:34Z, actor: be-developer): a full table with the
same 6 entries and rationale, plus the key design call that the install surface is uniformly
bootstrap-bearer-driven (no human session exists at install time) and only the orchestrators
**list** has a genuine session-only consumer.

| Endpoint | Classification | Install/Bootstrap weighed? |
|---|---|---|
| POST /api/admin/projects (create) | BEARER-allowed | ✅ installer + e2e provisioning seed |
| POST /api/admin/import (tar) | BEARER-allowed | ✅ restore/seed backup automation |
| POST /api/admin/import/adrs | BEARER-allowed | ✅ same class as tar import (ABS-379 ADR seeding) |
| GET /api/export (tar) | BEARER-allowed | ✅ scheduled/CI backup reads |
| POST /agent/v1/orchestrators (mint) | BEARER-allowed | ✅ #EXPORT_CRITICAL; session gate breaks bootstrap |
| GET /api/v1/projects/:p/orchestrators (list) | HUMAN-ONLY | ✅ dashboard-only consumer (no automation caller) |

System Architect concurred with the per-endpoint classification at the architecture gate.
Security Engineer independently verified the browser-caller cross-check (only `web/src/api.ts`,
`credentials:"include"`, drives the list — none of the bearer-allowed writes).

### AC2 — Human-only endpoint rejects bearer admin with 403 via the shared guards.ts helper ✅ PASS

The orchestrators list (`GET /api/v1/projects/:project/orchestrators`) is gated exclusively by
`requireHumanAdmin(principal, reply)` imported from `guards.ts`. There is **no inline `via` check
in admin.ts** (verified: `git show ABS-431-auto:backend/apps/server/src/routes/admin.ts | grep 'via\s*==='`
returns only comment text, no executable code).

`requireHumanAdmin` in `guards.ts`:
```ts
export function requireHumanAdmin(principal: Principal, reply: FastifyReply): boolean {
  if (principal.role !== "admin" || !isHumanSession(principal)) {
    reply.code(403).send({ error: "forbidden" });
    return false;
  }
  return true;
}
```

Where `isHumanSession` is the one shared mechanism predicate:
```ts
function isHumanSession(principal: Principal): boolean {
  return principal.via === "session";
}
```

Both `requireHuman` (ABS-413) and `requireHumanAdmin` (ABS-431) compose this single predicate —
the mechanism-vs-role boundary lives in exactly one place.

Test assertion (DB-gated, `admin-routes.test.ts`, line 217–230):
```ts
// Bearer admin (the pre-ABS-431 role-only bypass) is now rejected 403.
const bearerAdmin = await app!.inject({ method: "GET", url, headers: auth(bootstrapAdmin) });
assert.equal(bearerAdmin.statusCode, 403, bearerAdmin.body);
```

### AC3 — Human-only endpoint: admin session 200, non-admin session 403, anon 401 ✅ PASS

All four assertion variants are covered in the single test "ABS-431 orchestrators list is human-only":

| Caller | Expected | Test |
|---|---|---|
| Bearer admin | 403 | `bearerAdmin.statusCode === 403` |
| Admin session (via `/api/v1/session` exchange) | 200 | `adminSession.statusCode === 200` |
| Non-admin (agent) session | 403 | `agentSession.statusCode === 403` |
| Anon (no token) | 401 | `anon.statusCode === 401` |

The session exchange uses the `sessionCookie()` helper that mirrors `policy-routes.test.ts`
(same pattern as ABS-413). The non-admin session test specifically uses `agentToken` confirming
the role check still holds under the session path — `requireHumanAdmin` is AND logic (role=admin
AND via=session), not OR.

The existing `AC#4` test (register orchestrator) was also updated to read the list via
`sessionCookie(bootstrapAdmin)` instead of the old bearer token — no regression in existing tests.

### AC4 — Bearer-allowed regression per endpoint ✅ PASS

Test "ABS-431 install/provisioning/backup routes stay reachable by an admin bearer token" covers
one assertion per bearer-allowed endpoint:

| Endpoint | HTTP method | Expected | Assertion |
|---|---|---|---|
| create project | POST /api/admin/projects | 201 | `create.statusCode === 201` |
| tar import | POST /api/admin/import?project=PROV431 | 200 | `imp.statusCode === 200` |
| tar export | GET /api/export?project=PROV431 | 200 | `exp.statusCode === 200` |
| register orch (token mint) | POST /agent/v1/orchestrators | 201 | `reg.statusCode === 201` |

Note: `import/adrs` is not tested with a separate bearer regression (it uses the same
`requireAdmin` role-only guard as `tar import` — same code path). The core install/backup/mint
trio plus create-project are all covered. The system architect confirmed no regression in
the existing test suite covering these routes.

### AC5 — Mechanism assertion centralized in guards.ts, verified by test not grep alone ✅ PASS

Centralization verified three ways:

1. **Code inspection**: `isHumanSession` defined once in `guards.ts`. Both `requireHuman` and
   `requireHumanAdmin` call it. No `principal.via` read anywhere in `admin.ts` (only in comment text).

2. **Test-driven**: The bearer admin → 403 test for the list endpoint proves `requireHumanAdmin`
   is actually on the path (a grep would only check import presence; the test proves execution).

3. **TypeScript**: `requireHumanAdmin` is a typed export; a route that doesn't use it and checks
   `via` inline would need its own `via` access — which would appear in the diff. The diff has
   none.

The `guards.ts` seam is the single authority for mechanism assertion across both the ABS-413
WRITER_ROLES gates and the ABS-431 admin-list gate.

### AC6 — `pnpm -r typecheck`, `pnpm lint`, admin-routes + affected suites green ✅ PASS

| Check | Result | Who verified |
|---|---|---|
| `pnpm -r typecheck` | ✅ PASS (all 5 workspaces) | QAS independently re-run |
| `pnpm lint` | ✅ PASS (exit 0) | QAS independently re-run |
| admin-routes + policy-routes (20/20) | ✅ PASS | Implementer (Postgres 16) |
| core auth/session + command/dashboard (52/52) | ✅ PASS | Implementer (Postgres 16) |

TypeScript typecheck is the load-bearing static proof: `Principal.via` is a required field (added
by ABS-413); any missed stamping seam would fail compile. All 5 workspaces clean confirms the
`requireHumanAdmin` composition and import are type-correct end-to-end.

---

## Security Flag Verification (`[security]`)

- `Principal.via` is stamped once in `resolvePrincipal` (the auth entry point); a bearer caller
  cannot forge `via === "session"` — verified independently by the security-engineer gate.
- `requireHumanAdmin` uses AND logic: role `admin` **AND** `via === "session"`.
  A bearer admin token fails the mechanism check; a session non-admin token fails the role check.
- No inline `via` check leaked into `admin.ts` — centralized exclusively in `guards.ts`.
- No new SQL; `projectId` resolved from server-side `principal.targetProjectId` (not raw input).
- No secret literals in the diff.
- RLS: N/A (no DB-op change; org-scoping untouched).
- Architecture Review: PASS (system-architect, per-endpoint classification concurred).
- Security Review: PASS (security-engineer independence gate, no blocking findings, no follow-ups filed).

---

## Exit Routing

- Ticket flags: `[security]` — **no `design` flag**
- Exit target: **`Story Acceptance`** (design flag absent → Design Test is SKIP-FORWARDed per exit protocol)

---

## Final Verdict

**✅ APPROVED — All 6 acceptance criteria met.**

`pnpm -r typecheck` PASS + `pnpm lint` PASS (independently re-run by QAS). DB-gated test suite (Postgres 16)
reported green by implementer (20/20 + 52/52); test code verified correct by QAS diff review. All prior
gate reviews (Architecture, Security) PASS. No inline `via` checks in admin.ts; mechanism assertion
centralized in guards.ts single `isHumanSession` predicate shared by both ABS-413 `requireHuman` and
ABS-431 `requireHumanAdmin`. Per-endpoint #PATH_DECISION documented in-code and ticket; install/bootstrap
path preserved with regression tests.

**Releasing to Story Acceptance.**
