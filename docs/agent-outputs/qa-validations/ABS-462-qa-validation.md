# QA Validation Report — ABS-462
**Single source of truth for orchestrator/seat status displays**

| Field | Value |
|---|---|
| Ticket | ABS-462 |
| Parent | ABS-460 |
| Branch | `ABS-462-auto` |
| Commit | `3e0eeaed5d4ec8c32b864709933485e66ea63418` |
| QAS run date | 2026-07-19 |
| Verdict | **APPROVED** |

---

## Acceptance Criteria Verification

| # | Criterion | Test Coverage | Result |
|---|---|---|---|
| AC1 | No screen can simultaneously render 'no orchestrators' and a listed orchestrator host (e2e) | `home.spec.ts` "ABS-462 AC1: a listed spawn host never coexists with 'no orchestrators'" | ✅ PASS |
| AC2 | Attention count byte-identical on Home, nav badge, and Board; intentional scope diff renders exactly 'N items + M seats' (unit + e2e) | `attention.test.ts` AC4 formatScopedCount; `attentionSummary.test.ts` scopedCount; `inbox.spec.ts` "AC2: attention count is byte-identical..." | ✅ PASS |
| AC3 | Home shows health one-liner; green system states positively | `attentionSummary.test.ts` AC3 green/populated/plural; `home.spec.ts` AC1 checks `home-health` contains "stale"+"blocked" | ✅ PASS |
| AC4 | Unit test pins aggregation contract in `core attention.ts` | `packages/core/test/attention.test.ts` (6 tests) | ✅ PASS |
| Scope | Badge semantics: stale seats rendered as 'N active · M stale', not counted active | Covered in `home.spec.ts` fixture (1 active + 1 stale spawn) | ✅ PASS |

---

## Green-Run Proof (ABS-453)

### Unit Tests — Files added/changed by commit `3e0eeaed`

**`packages/core/test/attention.test.ts`**
```
Command: node --import tsx --test packages/core/test/attention.test.ts
Commit:  3e0eeaed5d4ec8c32b864709933485e66ea63418

✔ AC4: total equals items.length — the one canonical count (0.703667ms)
✔ AC4: item_count + seat_count partitions total (N items + M seats) (0.072375ms)
✔ AC4: by_type counts every discriminated type (0.645541ms)
✔ AC4: oldest_seat_age_seconds is the max stalled-seat age (0 when none) (0.053208ms)
✔ AC4: formatScopedCount renders the exact 'N items + M seats' form (0.057292ms)
✔ AC4: empty feed summarizes to all-zero (0.045583ms)
tests 6 | pass 6 | fail 0
```

**`apps/web/test/attentionSummary.test.ts`**
```
Command: node --import tsx --test apps/web/test/attentionSummary.test.ts
Commit:  3e0eeaed5d4ec8c32b864709933485e66ea63418

✔ AC2: total equals items.length regardless of type mix (0.708917ms)
✔ AC2: scopedCount renders the exact 'N items + M seats' form (0.065208ms)
✔ AC3: green system states health positively (0.079458ms)
✔ AC3: health line names seats (with oldest age), blockers and gates (0.072833ms)
✔ AC3: singular vs plural wording (0.054875ms)
tests 5 | pass 5 | fail 0
```

### E2E Tests — Playwright (Postgres-backed server, port 5432)

**`apps/web/e2e/home.spec.ts` + `apps/web/e2e/inbox.spec.ts`**
```
Command: DATABASE_URL="postgres://postgres:postgres@localhost:5432/agentic" \
         pnpm --filter @agentic-backend/web exec playwright test home.spec.ts inbox.spec.ts --reporter=list
Commit:  3e0eeaed5d4ec8c32b864709933485e66ea63418

Running 17 tests using 1 worker

  ✓  1  e2e/home.spec.ts:135:1 › AC1: all 4 zones render (KPI, attention, epics, ticker) (958ms)
  ✓  2  e2e/home.spec.ts:173:1 › ABS-462 AC1: a listed spawn host never coexists with 'no orchestrators' (747ms)
  ✓  3  e2e/home.spec.ts:185:1 › AC2: no vertical scroll on main container at 1440×900 (742ms)
  ✓  4  e2e/home.spec.ts:196:1 › AC2: no vertical scroll on main container at 1280×800 (757ms)
  ✓  5  e2e/home.spec.ts:211:1 › AC3: 'needs-human' KPI opens the Attention Inbox with no narrowing filter (787ms)
  ✓  6  e2e/home.spec.ts:224:1 › AC3: 'active-seats' KPI opens the board filtered to the active run (825ms)
  ✓  7  e2e/home.spec.ts:240:1 › AC5: SSE events update ticker without reload (753ms)
  ✓  8  e2e/home.spec.ts:278:1 › AC5: SSE disconnect shows the reconnect banner with last-data timestamp (755ms)
  ✓  9  e2e/inbox.spec.ts:153:1 › AC1: attention items render oldest-first with age badges and source links (234ms)
  ✓ 10  e2e/inbox.spec.ts:201:1 › AC1: source link on a ticket item opens the ticket drawer (301ms)
  ✓ 11  e2e/inbox.spec.ts:226:1 › AC2: escalation resolve — posting a decision comment reclassifies item (387ms)
  ✓ 12  e2e/inbox.spec.ts:268:1 › AC2: blocker resolve — transition removes the item on next attention fetch (410ms)
  ✓ 13  e2e/inbox.spec.ts:316:1 › AC2: gate release-lever toggle is visible and interactive (379ms)
  ✓ 14  e2e/inbox.spec.ts:353:1 › AC3: stop-run requires confirm dialog with non-empty reason (421ms)
  ✓ 15  e2e/inbox.spec.ts:422:1 › AC2: attention count is byte-identical on nav badge, Board header, and Home (313ms)
  ✓ 16  e2e/inbox.spec.ts:469:1 › AC5: agent/orchestrator sessions cannot trigger actions (280ms)
  ✓ 17  e2e/inbox.spec.ts:524:1 › empty state: 'Nothing needs you' shown when no attention items (241ms)

  17 passed (12.5s)
```

---

## Pre-existing Failure Note

`core/test/migrate-prefix-guard.test.ts` fails due to a duplicate `011_*` migration prefix (`011_command_reason_length.sql` + `011_seat_spawn_id_text.sql`). This failure was introduced by the ABS-447 merge (`e5fce3cf`) and is **confirmed pre-existing** — commit `3e0eeaed` touches **no migration files**. This is an ABS-449-class numbering collision that the migration owner must renumber; it does not block this story.

---

## DoD Checklist

- [x] All 4 ACs met and verified by test evidence
- [x] Unit tests green: core `6/6`, web `5/5`
- [x] E2E tests green: `17/17 passed` (home.spec + inbox.spec)
- [x] `pnpm -r typecheck` clean (verified by system-architect)
- [x] `pnpm lint` clean (verified by system-architect)
- [x] `pnpm --filter @agentic-backend/web build` clean (verified by system-architect)
- [x] No design flag → no Design Test gate
- [x] Pre-existing failure (`migrate-prefix-guard`) confirmed out of scope

---

## Final Verdict

**APPROVED** — All ACs verified, all changed test files ran green against commit `3e0eeaed`. Releasing to Story Acceptance.
