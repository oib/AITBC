# QA Validation Report — ABS-461
**Abort-spawn command from the UI (kill the resolve dead-end)**

- **Verdict**: APPROVED
- **Commit under review**: `55657aec2ce5637bd57eb75d857ca963cd3fb72a`
- **Date**: 2026-07-19
- **QAS actor**: qas

---

## Acceptance Criteria Verification

| AC | Criterion | Result | Evidence |
|----|-----------|--------|----------|
| AC1 | Clicking Resolve on a stalled seat offers 'Abort spawn' with required reason; submit enqueues an orch_command keyed by ledger_id | **PASS** | `inbox.spec.ts` — test `ABS-461: stalled-seat offers abort-spawn keyed by ledger_id with mandatory reason` asserts `body.kind==="abort-spawn"`, `body.ledger_id===stalledSpawnId`, `body.reason` truthy; 9/9 green (QAS run) |
| AC2 | Route rejects a missing reason with 400 per the existing convention | **PASS** | `command-routes.test.ts` — `ABS-444: enqueue of a destructive kind is rejected 400 when the reason is missing/empty` covers abort-spawn; 26/26 PASS (QAS run) |
| AC3 | No orchestrator connected → honest queue/undeliverable copy; no 'Orchestrators panel' dead-end | **PASS** | `git grep "Orchestrators panel"` over `backend/apps/web/` returns nothing; offline copy added: "The abort will be queued and delivered when the orchestrator next polls." |
| AC4 | No schema change to the wire format beyond the added reason field | **PASS** | Zero migration files touched in commit 55657aec (3 files changed: `types.ts`, `Inbox.tsx`, `inbox.spec.ts`); `reason` field pre-existed via ABS-444 |

---

## Gate Results (QAS Independent Run)

| Gate | Command | Result |
|------|---------|--------|
| TypeScript (5 ws) | `pnpm -r typecheck` | **PASS** — 5 workspaces clean |
| Lint | `pnpm lint` | **PASS** — no errors |
| Web unit tests | `pnpm --filter @agentic-backend/web test` | **13/13 PASS** |
| Command-routes integration | `node --import tsx --test command-routes.test.ts` | **26/26 PASS** |
| Inbox e2e (ABS-453 green-run proof) | `playwright test inbox.spec.ts` | **9/9 PASS** |

### Green-Run Proof (ABS-453)
```
Command:  DATABASE_URL=postgres://postgres:pw@localhost:55411/agentic \
          node_modules/.bin/playwright test inbox.spec.ts --reporter=list
Commit:   55657aec2ce5637bd57eb75d857ca963cd3fb72a
Results:  9 passed (4.8s)

  ✓ 1 inbox.spec.ts:153 › AC1: attention items render oldest-first with age badges and source links
  ✓ 2 inbox.spec.ts:201 › AC1: source link on a ticket item opens the ticket drawer
  ✓ 3 inbox.spec.ts:226 › AC2: escalation resolve — posting a decision comment reclassifies item
  ✓ 4 inbox.spec.ts:268 › AC2: blocker resolve — transition removes the item on next attention fetch
  ✓ 5 inbox.spec.ts:316 › AC2: gate release-lever toggle is visible and interactive
  ✓ 6 inbox.spec.ts:354 › ABS-461: stalled-seat offers abort-spawn keyed by ledger_id with mandatory reason
  ✓ 7 inbox.spec.ts:422 › AC4: unread badge appears when attention items arrive
  ✓ 8 inbox.spec.ts:474 › AC5: agent/orchestrator sessions cannot trigger actions
  ✓ 9 inbox.spec.ts:529 › empty state: 'Nothing needs you' shown when no attention items
```

---

## Pre-existing Failures (Not introduced by ABS-461)

The following test failures were confirmed to pre-exist in parent commit `c3b8caee` (before ABS-461):

| Test | Failure | Classification | Notes |
|------|---------|----------------|-------|
| `migrate-prefix-guard` | `011` collision: `011_command_reason_length.sql` & `011_seat_spawn_id_text.sql` | `code` — pre-existing | Both files present in parent commit `c3b8caee`; ABS-461 touched zero migration files; introduced by epic merge `757d4977`. Needs separate renumbering ticket. |
| `bootstrap-promotion.test.ts` (3 tests) | 403 ≠ 200 (dev-token state) | `environment` — stale DB state | `abs410-demo-pg` has residual dev-token state from prior runs |
| `report-routes.test.ts` (5 tests) | 401 ≠ 200 (auth setup) | `environment` — stale DB state | Same container state issue |

**None of these failures are introduced by ABS-461.** The commit `55657aec` changed only 3 frontend files: `backend/apps/web/src/types.ts`, `backend/apps/web/src/components/Inbox.tsx`, `backend/apps/web/e2e/inbox.spec.ts`.

---

## Scope Discipline Verification

- ✅ Runner-side consume/terminate left to ABS-476 (out of scope)
- ✅ No bulk-abort, no auto-abort heuristics
- ✅ No shared-dialog refactor (pre-existing duplication, out of scope)
- ✅ `canControlOrchestrator` import correctly removed (no longer needed)

## Minor Non-blocking Finding

`Inbox.tsx:17` file-doc comment reads "Destructive actions (stop-run) require a non-empty reason (AC3)" — `abort-spawn` is now the stalled-seat destructive action. Stale parenthetical; behaviour is correct. Flagged as optional cleanup (also noted by system-architect; non-blocking).

---

## Design Flag

`labels: [orchestrator-ready, ux-review-2026-07]` — no `design` flag present.
Exit target: **Story Acceptance** (not Design Test).

---

## Final Verdict

**APPROVED** — All 4 ACs pass with independent evidence. Green-run proof for changed test file `inbox.spec.ts` confirmed: **9/9 at commit `55657aec`**. Pre-existing test failures are environment/pre-existing-code issues not in this ticket's scope. Implementation is frontend-only, scope-disciplined, and correctly wires the existing `abort-spawn` command kind with honest offline copy and zero dead-end references to the Orchestrators panel.
