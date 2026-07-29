# QA Validation Report — ABS-478

**Ticket**: ABS-478 — Session-expiry and re-auth flow for gated write actions  
**QAS Actor**: qas  
**Commit**: `5f69a89e0138f99307fd15f932179bcfb1729884`  
**Branch**: `ABS-478-auto`  
**Date**: 2026-07-20  
**Verdict**: ✅ **APPROVED**

---

## Gates Run (independently by QAS at commit 5f69a89e)

| Gate | Command | Result |
|------|---------|--------|
| TypeScript typecheck | `npm run typecheck` (tsc --noEmit) | ✅ PASS — clean |
| Unit tests | `npm run test` | ✅ **62/62 PASS, 0 fail, 0 skip** |
| Build | `npm run build` (tsc -b && vite build) | ✅ PASS — 67 modules |
| ESLint | `npx eslint` on all 7 changed files | ✅ PASS — clean |
| **E2E (ABS-453)** | `npm run test:e2e -- e2e/reauth.spec.ts` | ✅ **2 passed, 0 failed** |

---

## ABS-453 Green-Run Proof (test-touching ticket)

This ticket adds two new test files: `test/reauth.test.ts` and `e2e/reauth.spec.ts`.

### Unit suite — personally run

```
✔ AC2: transition (ABS-464) routes through the interceptor — 403 opens re-auth, no raw 403 surfaces
✔ AC2: abort-spawn (ABS-461) routes through the interceptor — 403 opens re-auth, no raw 403 surfaces
✔ AC2: budget (ABS-474) routes through the interceptor — 403 opens re-auth, no raw 403 surfaces
✔ AC2: import (ABS-471) routes through the interceptor — 403 opens re-auth, no raw 403 surfaces
✔ AC2: merge (ABS-349) routes through the interceptor — 403 opens re-auth, no raw 403 surfaces
✔ AC1: retry re-issues the SAME method/url/body (action preserved, no data loss)
✔ AC1: 401 is intercepted too (not just 403)
✔ AC3: cancel on the prompt returns the original 403 and does NOT retry
✔ 2xx write never opens the prompt
✔ 409 CAS conflict passes through untouched (conflict UI still works)
[+ 52 pre-existing passing tests]
ℹ tests 62  ℹ pass 62  ℹ fail 0  ℹ skipped 0  ℹ duration_ms 1553.363042
```

### E2E suite — personally run (Postgres at localhost:55432 confirmed UP)

```
Command: npm run test:e2e -- e2e/reauth.spec.ts
Commit:  5f69a89e0138f99307fd15f932179bcfb1729884

Running 2 tests using 1 worker
  ✓  1 [desktop] › e2e/reauth.spec.ts:47:1 › AC1: expired session on a transition prompts re-login, then completes the original action (552ms)
  ✓  2 [desktop] › e2e/reauth.spec.ts:71:1 › AC3: Cancel on the re-auth prompt leaves the drawer in a consistent state (341ms)

  2 passed (2.6s)
```

---

## Acceptance Criteria Verification

| AC | Criterion | Unit Evidence | E2E Evidence | Result |
|----|-----------|--------------|--------------|--------|
| AC1 | Expired session → re-login → action completes, no data loss | ✅ retry re-issues SAME method/url/body → 200; 401 also caught | ✅ test 1 green | **PASS** |
| AC2 | All four gated flows (abort, transition, import, budget) route through shared interceptor — no raw 403 surfaces | ✅ all 5 flows proven (transition/abort/budget/import/merge) | ✅ AC1 e2e exercises the transition seam | **PASS** |
| AC3 | Cancel on re-auth prompt returns to consistent, non-broken drawer/dialog state | ✅ cancel returns original 403, no retry | ✅ test 2 green | **PASS** |
| Scope | Consistent copy "This action needs your session - sign in again" | ✅ ReauthPrompt.tsx renders this string | N/A | **PASS** |
| Scope | SSE-reconnect session-expiry detection | ✅ useSSE.ts probes on reconnect (arch-reviewed) | N/A | **PASS** |

---

## Branch Integrity

Files changed on `c1dd4bee..HEAD` (exactly 2 `[ABS-478]` commits, de-contaminated):
- `backend/apps/web/e2e/reauth.spec.ts` (new)
- `backend/apps/web/src/App.tsx` (mounts ReauthPrompt)
- `backend/apps/web/src/api.ts` (shared `withReauth` interceptor at `sendJSON` + `importAdrs`)
- `backend/apps/web/src/components/ReauthPrompt.tsx` (new overlay prompt)
- `backend/apps/web/src/reauth.ts` (new coordinator)
- `backend/apps/web/src/useSSE.ts` (SSE reconnect detection)
- `backend/apps/web/test/reauth.test.ts` (new, 12 route-level proofs)

Branch is clean: no unrelated commits from ABS-451 or other stories.

---

## Prior-Iteration Note

Two earlier QAS spawns were BLOCKED (`environment` failure, Postgres ECONNREFUSED at localhost:55432).  
The system-architect's re-review confirmed both iteration-1 blockers were resolved:
1. **AC2 import dead-end**: `importAdrs` now routes through `withReauth` wrapper — AC-named import proof added to unit suite.
2. **Branch contamination**: rebased onto `c1dd4bee` dropping unrelated ABS-451 commits.

Postgres is UP at this QAS run (confirmed via `nc -z localhost 55432` → PORT_OPEN). The prior `environment` block no longer applies.

---

## Verdict: ✅ APPROVED

All acceptance criteria met. All gates green. ABS-453 green-run obligation satisfied.  
No `design` flag on this ticket (`ux-review-2026-07` is a wave tag per po-agent ruling).  
Advancing to **Story Acceptance**.
