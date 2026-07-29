# QA Validation Report — ABS-483

**Ticket:** ABS-483 — Fix agent create-item API contract vs board.spec.ts:128  
**Validator:** qas (orchestrator-spawned In Test gate)  
**Commit reviewed:** `695bc23d` on branch `ABS-483-auto` (based on epic tip `cee670cc`)  
**Date:** 2026-07-20  
**Verdict:** ✅ APPROVED

---

## Diff Verification

**Files changed:** `backend/apps/web/e2e/board.spec.ts` (2 lines only)  
Confirmed via `git diff HEAD~1 HEAD --name-only`.

**PATH_DECISION chosen:** Option 1 (recommended) — fix the test to read the bare-key contract.  
No API/contract change; no consumer risk; no architect loop required.

**Change summary:**
- Removed broken comment ("create returns the item's frontmatter markdown (plain text); read its id")
- Replaced `/^id:\s*(\S+)/m` regex match (could never match a bare key) with `(await mk.text()).trim()`

**Contract independently verified by QAS:**
- `createItem` (`packages/core/src/items.ts:362`) returns bare `key` string (line 415: `return key;`)
- `POST /items` (`apps/server/src/routes/items.ts:85-107`) emits it via `reply.type("text/plain; charset=utf-8").send(...)` through the `send()` helper
- **Pattern compliance:** `home.spec.ts:36` (`const key = (await r.text()).trim();`) and `inbox.spec.ts:459` (`const newKey = (await r.text()).trim();`) use the identical convention — `board.spec.ts:128` was the lone anomaly; the fix conforms it to the established sibling pattern

---

## Acceptance Criteria Validation

### AC1 — `board.spec.ts:128` passes green
**Status: ✅ PASS**

```
Command: DATABASE_URL=postgres://postgres:postgres@localhost:5432/agentic \
         E2E_DB_NAME=agentic_e2e_abs483_qa CI=1 \
         pnpm --filter web test:e2e board.spec.ts
Result: Running 3 tests using 1 worker — 3 passed (3.2s)
Commit: 695bc23d40e234439fa37f819d03867fc159b96a
```

The critical test "ABS-464: forward moves are primary; a backward move is gated behind 'more…'" at line 128 is green. `card` is no longer `undefined`.

### AC2 — No regression: board + home + budget remain green
**Status: ✅ PASS**

```
Command: DATABASE_URL=postgres://postgres:postgres@localhost:5432/agentic \
         E2E_DB_NAME=agentic_e2e_abs483_qa CI=1 \
         pnpm --filter web test:e2e board.spec.ts home.spec.ts budget.spec.ts
Result: Running 27 tests using 1 worker — 27 passed (25.2s)
Commit: 695bc23d40e234439fa37f819d03867fc159b96a
```

### AC3 — Contract consistent: endpoint / consumers / test
**Status: ✅ PASS**

- Endpoint (`POST /items`): emits bare key as `text/plain`
- Consumers (CLI/tracker/orchestrator): parse bare key — unaffected
- Test (`board.spec.ts:128`): now reads bare key via `.trim()` — consistent
- No divergent assumptions remain

### AC4 — typecheck + eslint + unit remain green
**Status: ✅ PASS (with pre-existing unit exception)**

**typecheck:**
```
pnpm -r typecheck
→ apps/web, packages/core, packages/forge, packages/webhooks, apps/server: all Done (no errors)
```

**eslint:**
```
pnpm lint → $ eslint . (no output = clean)
```

**unit:**
- 1 failure in `packages/core/test/migrate-prefix-guard.test.ts` — "two migrations share a numeric prefix: 011"
- **Pre-existing on epic tip `cee670cc`**: both `011_command_reason_length.sql` (ABS-447, `a6f27767`) and `011_seat_spawn_id_text.sql` (ABS-445, `c0b92b31`) pre-date this commit
- **Confirmed via `git diff cee670cc HEAD -- packages/core/src/migrations/`**: returns empty — this diff touches ZERO migration files
- The migration runner (`applyMigrations`) does NOT enforce the prefix guard; e2e boot and all ACs are unaffected
- Resolution (renumber vs grandfather) has operator-DB blast radius and is an Epic-Sync/migration-numbering call (ABS-428/ABS-449), not an ABS-483 one
- **AC4 is satisfied for ABS-483 scope**: "remain green" means no regression from this diff; the unit red pre-dates it

---

## Green-Run Proof (ABS-453 Obligation)

This ticket changes `board.spec.ts` (a `*.spec.ts` test file). ABS-453 mandates an attached green-run.

```
Command:  DATABASE_URL=postgres://postgres:postgres@localhost:5432/agentic \
          E2E_DB_NAME=agentic_e2e_abs483_qa CI=1 \
          pnpm --filter web test:e2e board.spec.ts
Counter:  3 passed, 0 failed
Commit:   695bc23d40e234439fa37f819d03867fc159b96a
```

✅ Green-run proof obligation met.

---

## Escalation — Pre-existing 011 migration prefix collision

The `migrate-prefix-guard` unit test failure is a **carry-forward escalation** (out of ABS-483 scope):
- Both `011_command_reason_length.sql` and `011_seat_spawn_id_text.sql` were independently introduced on the epic branch (ABS-447 + ABS-445)
- Renumbering an already-applied migration trips the ABS-288 content-integrity guard — exactly why `004` was grandfathered
- Needs its own ticket routed to Epic-Sync/architecture (ABS-428/ABS-449 lane)

---

## Verdict

**APPROVED** — all four ACs met. Pattern compliance verified, contract consistent end-to-end, no RLS/security surface, no over-engineering. The one unit red is pre-existing and orthogonal to this diff.

**Next:** Transition to Story Acceptance (no `design` flag on this ticket).
