# QA Validation Report — ABS-413

**Ticket**: ABS-413 — Harden human-only WRITER_ROLES gates: assert auth mechanism (session) not role alone  
**Branch**: `ABS-413-auto`  
**Commit**: `c671799`  
**QAS Actor**: qas  
**Date**: 2026-07-18  
**Verdict**: ✅ APPROVED

---

## Validation Environment

- Worktree: `/Users/sahan/local_projects/agentic-development-boilerplate/tmp/ABS-413-work`
- Branch: `ABS-413-auto` (verified via `git branch --show-current`)
- Commit: `c671799 feat(auth): require human session mechanism on WRITER_ROLES write gates [ABS-413]`
- DB-gated tests (Postgres 16 harness) skip cleanly without `DATABASE_URL`; the implementer's
  harness evidence is accepted per the ABS-287 CI guard (throws if CI set without DATABASE_URL).
- `pnpm -r typecheck` green is the load-bearing independent correctness proof: `Principal.via` is
  a **required** field on `Principal`, so any missed stamping seam would fail compile.

---

## AC/DoD Verification

### AC1 — Auth-model decision recorded ✅ PASS

- `docs/agent-outputs/ABS-413-auth-mechanism-gate-decision.md` committed in `c671799`
- Decision: mechanism assertion chosen (bearer → rejected 403; session required in addition to role)
- Alternative explicitly weighed and rejected: role-only + provisioning discipline (status quo)
- Correctly classified as a documented team decision (not a formal ADR): hardens existing
  convention, changes no ADR, adds no role/surface — matches the PO guardrail
- System Architect and Security Engineer both concurred in their gate reviews

### AC2 — `Principal.via` stamped by both auth paths + unit tests ✅ PASS

- `Principal.via: 'bearer' | 'session'` added as a **required** field in `core/src/auth.ts`
- `authenticate()` (bearer path) → passes `"bearer"` to `resolvePrincipal()`
- `authenticateSession()` (session path in `sessions.ts`) → passes `"session"` to `resolvePrincipal()`
- `resolvePrincipal()` receives `via` as a required parameter, stamps it onto the returned `Principal`
- Never read from client input — stamped only at the single `resolvePrincipal` seam
- Unit tests in `backend/packages/core/test/auth.test.ts`:
  - `"the bearer path stamps principal.via = 'bearer'"` (DB-gated, skips cleanly without DB)
  - `"the session path stamps principal.via = 'session'"` (DB-gated, skips cleanly without DB)
- Typecheck green proves `via` propagation is complete (required field — any missed seam fails compile)

### AC3 — Bearer admin/maintainer token → 403 on every human-only write surface ✅ PASS

Per-gate bearer-rejection tests added and verified present:

| Gate | Test | Status |
|------|------|--------|
| policy create | ABS-413: bearer admin/maintainer 403 on policy create/update/status | ✅ DB-gated |
| policy update | same test covers update | ✅ DB-gated |
| policy status | same test covers status | ✅ DB-gated |
| commands enqueue | ABS-413: enqueue rejects bearer admin/maintainer token (403) | ✅ DB-gated |
| dashboard transition | ABS-413: bearer admin/maintainer 403 on every dashboard write | ✅ DB-gated |
| dashboard comments | same test covers comments | ✅ DB-gated |
| dashboard labels | same test covers labels | ✅ DB-gated |
| dashboard merge | same test covers merge; requireHuman fires BEFORE merge-gate | ✅ DB-gated |

No-mutation assertion on dashboard: rejected calls leave `status='Backlog'`,
`orchestration_state='excluded'` unchanged.

### AC4 — Genuine session succeeds; role/anon negatives hold ✅ PASS

- Existing `policy-routes`, `command-routes`, `dashboard-routes`, `merge-routes` tests retain:
  - Maintainer/admin session → `200`/`201` ✅
  - Agent/orchestrator token → `403` ✅
  - Viewer → `403` ✅
  - Anon → `401` ✅
- Pre-existing `command-routes` test helper fixed (used raw token as session id, broken since
  ABS-333 opaque sessions); command-routes was 8/16 failing at baseline, now 17/17.
- No regression.

### AC5 — Single shared `requireHuman`, no gate role-only ✅ PASS

- `git grep` confirms `WRITER_ROLES` and `requireHuman` defined **only** in
  `backend/apps/server/src/routes/guards.ts`
- All three route files (`policies.ts`, `commands.ts`, `dashboard.ts`) import from `./guards.js`
- Zero local definitions of `const WRITER_ROLES` or `function requireHuman` in route files
- `guards.ts` check: `!WRITER_ROLES.includes(principal.role) || principal.via !== "session"` —
  both role AND mechanism required (AND logic: both conditions must be satisfied)

### AC6 — `pnpm -r typecheck`, `pnpm lint`, affected suites green ✅ PASS

| Check | Result | Notes |
|-------|--------|-------|
| `pnpm -r typecheck` | ✅ PASS | Independently re-run by QAS; all 5 projects clean |
| `pnpm lint` | ✅ PASS | Independently re-run by QAS; exit 0 |
| core auth (6/6) | ✅ PASS | 4 non-DB pass + 2 DB-gated skip cleanly per ABS-287 |
| policy-routes (10/10) | ✅ PASS | Implementer harness (Postgres 16) |
| command-routes (17/17) | ✅ PASS | Implementer harness (was 8/16 at baseline pre-fix) |
| dashboard-routes (29/29) | ✅ PASS | Implementer harness |
| merge-routes (9/9) | ✅ PASS | Implementer harness |

---

## Security Flag Verification

Flags: `[security]` — independently verified:

- `Principal.via` never sourced from client input ✅
- `requireHuman` assertion is logical AND (role ∈ WRITER_ROLES **AND** `via === 'session'`) ✅
- WRITER_ROLES is a static allowlist (deny-by-default for new roles) ✅
- RLS N/A (agentic-backend `pg`/org-scoped stack, not Prisma) ✅
- Security Review gate: PASS (security-engineer independence gate, no blocking findings)
- Architecture Review gate: PASS (system-architect Stage 1 gate)
- One non-blocking follow-up (ABS-431): `admin.ts requireAdmin` — correctly fenced OOS

---

## Exit Routing

- Ticket flags: `[security]` — **no `design` flag**
- Exit target: **`Story Acceptance`** (design flag absent → Design Test is SKIP-FORWARDed)

---

## Final Verdict

**✅ APPROVED — All 6 acceptance criteria met. typecheck + lint green (independently re-run).
All prior gate reviews (Architecture, Security) PASS. Releasing to Story Acceptance.**
