# QA Validation Report — ABS-446

**Ticket**: ABS-446 — Bug: board S9 release-toggle checkbox does not toggle state (ABS-241) — restore Freigabe action  
**Branch**: `ABS-446-auto`  
**Commit**: `9079607` (`fix(ui): flip board S9 release-toggle optimistically so it toggles [ABS-446]`)  
**QAS Run Date**: 2026-07-18  
**Verdict**: ✅ **APPROVED**

---

## Gate Checks

| Check | Command | Result |
|-------|---------|--------|
| TypeScript typecheck | `pnpm typecheck` (all packages) | ✅ PASS — 0 errors |
| ESLint | `pnpm lint` | ✅ PASS — 0 warnings/errors |
| Unit tests (all packages) | `pnpm test` | ✅ PASS — 0 failures (7+126+6+18+6 = 163 passing across core/server/forge/webhooks/web) |
| E2E — board.spec.ts | `playwright test e2e/board.spec.ts` (fresh Postgres DB at 55446) | ✅ PASS — 2/2 |
| E2E — S9 specifically | `board.spec.ts:74 › S9 (ABS-241): human transition + release toggle…` | ✅ PASS |

---

## Acceptance Criteria Verification

### AC1 — Clicking/`.check()`-ing the release-toggle changes its checked state
**Result**: ✅ PASS

`board.spec.ts:74` calls `page.getByTestId("release-toggle").check()`. With the fix (`releaseOverride` state), the DOM checkbox flips immediately (optimistic) before the async write completes. Playwright `.check()` observes the synchronous state change. Test passes.

**Evidence**: `board.spec.ts:74:1 › S9 (ABS-241): human transition + release toggle from the drawer, orchestrator sees it next poll` — **PASS** in independent QAS run.

### AC2 — Toggling triggers the correct human-gated release write with `actor=human` (#EXPORT_CRITICAL)
**Result**: ✅ PASS

- Write path: `api.setLabels(project, key, next ? [RELEASE_LABEL, ...freeLabels] : freeLabels)` → `sendJSON("PATCH", .../labels, {...}, credentials:"include")` → `PATCH /api/v1/.../labels`
- `HUMAN_ACTOR` is set server-side in `updateItem()`; the client cannot spoof the actor
- `requireHuman` gate enforces writer-role ALLOWLIST + `via === "session"` (HttpOnly cookie, ABS-413 defence-in-depth)
- The optimism is client DOM state only; a `!res.ok` (incl. 403) reverts `releaseOverride` to `null` (server truth)
- S9 test polls `GET /agent/v1/projects/${project}/items?label=orchestrator-ready` and asserts the card appears → confirms the write succeeded via the authenticated session path

**Evidence**: Security Review passed by independent security-engineer (comment 2026-07-18T17:50:21Z); S9 poll assertion in board.spec.ts passes independently.

### AC3 — `backend/apps/web/e2e/board.spec.ts` S9 executes and PASS in the web e2e suite
**Result**: ✅ PASS

QAS ran `playwright test e2e/board.spec.ts` independently on a fresh Postgres DB (Docker `abs446-qas-pg`, port 55446, migrated with 9 migrations, SPA built from this branch). Result: **2 passed (2.1s)**.

```
✓  1 e2e/board.spec.ts:39:1 › login → board → live update › detail drawer (353ms)
✓  2 e2e/board.spec.ts:74:1 › S9 (ABS-241): human transition + release toggle from the drawer, orchestrator sees it next poll (544ms)

2 passed (2.1s)
```

---

## Security Review Verification (#EXPORT_CRITICAL)

- **Diff scope**: `backend/apps/web/src/components/TicketDrawer.tsx` (+24/-2) — single client component, no server/route/`/api/**`/auth files touched
- **Authorization path**: unchanged — `api.setLabels` → `PATCH /api/v1/.../labels`, `HUMAN_ACTOR` set server-side, `requireHuman` enforces writer-role + `via===session`, bearer token gets 403
- **Optimism scope**: client DOM state only, fails safe on `!res.ok/403` (reverts override + surfaces note)
- **Security flag**: independent Security Review gate passed (security-engineer, 2026-07-18T17:50:21Z)
- **ABS-241 `actor=human` path**: NOT weakened ✅

---

## Pre-existing Out-of-Scope Failures

`spawns.spec.ts` DAC-14/15/16/17 — 4 failures with HTTP 500 on `POST /agent/v1/.../spawns`. These are the **spawns `spawn_id` UUID contract defect** explicitly called out as out of scope in the ticket ("paired spawns `spawn_id` UUID contract defect (separate follow-up)"). These failures pre-date ABS-446 and are unchanged by this commit.

---

## Implementation Review

The fix is minimal and correct:
1. `const [releaseOverride, setReleaseOverride] = useState<boolean | null>(null)` — new optimistic state
2. `const releaseChecked = releaseOverride ?? eligible` — uses optimistic value while pending, falls back to server truth
3. `toggleRelease` flips `releaseOverride` on click, then awaits `api.setLabels`, reconciles to `null` on success (server truth via `onChanged()` reload), reverts on failure
4. Checkbox: `checked={releaseChecked}` instead of `checked={eligible}`
5. `isWriter(role)` gate on the whole Actions panel — unchanged; non-writers never see the toggle

Root cause confirmed: the original `checked={eligible}` only updated after async server write + `onChanged()` reload, so Playwright `.check()` never observed a synchronous state transition.

---

## Verdict

**✅ APPROVED** — All 3 ACs pass, all gate checks pass. `flags: [security]` → Security Review already completed. No `design` flag → releasing to `Story Acceptance`.
