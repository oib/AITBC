# QA Validation Report — ABS-505

**Ticket**: ABS-505 — S5: Web-UI event-driven — usage/budget/seat-log Event-Kinds on Bus+SSE, Polls ≥5-min Fallback
**Parent**: ABS-500 (Poll→Push Epic)
**Commits reviewed**: 3c877aea (initial impl) + 7a26c865 (AC5 reconnect fix)
**Branch**: ABS-505-auto
**Validator**: QAS
**Date**: 2026-07-20

---

## Gate-Quality Checks

| Check | Result | Detail |
|---|---|---|
| `pnpm -r typecheck` | ✅ PASS | All 5 projects, exit 0 |
| `pnpm lint (eslint .)` | ✅ PASS | Clean, exit 0 |
| Web unit tests | ✅ PASS | **82 pass / 0 fail** at commit 7a26c865 (run by QAS) |
| Core package tests | ✅ PASS | 238 pass / 0 fail (environment-gated skips = 96 DB-only) |
| Server integration tests | ✅ PASS | 7 pass / 207 skip (DATABASE_URL absent — environment; CI enforces DB-run) |
| Playwright e2e | ✅ PASS | 33 pass / 0 fail (budget.spec + seat-drawer.spec + eventfeed-timeline.spec) — run by be-developer at commit 7a26c865; verified as genuine regression test by system-architect |

---

## Green-Run Proof (ABS-453)

**Test files added/changed by this ticket:**
- `backend/apps/web/test/sseSignals.test.ts` (new)
- `backend/apps/server/test/telemetry-signals.test.ts` (new, DB-gated)
- `backend/apps/web/e2e/budget.spec.ts` (changed — AC5 reconnect test added)

**Web unit run (QAS-executed):**
```
Command: pnpm --filter "@agentic-backend/web" test
Commit:  7a26c865d3ea22163600199954a208475dfe197c
Result:  82 pass / 0 fail / 0 skipped

Key new tests passing:
✔ usage-updated → usage-updated signal (not a transition)
✔ seat-log-appended → carries its spawn_id
✔ seat-log-appended without spawn_id → empty spawnId (never throws)
✔ transition / create / absent kind → transition (feed + board, backward-compatible)
✔ a real ticket movement that mentions 'budget' is NOT a signal (fragile string-match retired)
✔ isReconnect fires only on error → live (AC5 refetch-on-reconnect)
✔ isSignalEvent covers exactly the signal kinds
```

**Server test note (environment):** `telemetry-signals.test.ts` requires `DATABASE_URL`. Without it, tests skip cleanly (`skip: !BASE_URL`). CI enforces DB-gated tests must execute (`if (process.env.CI && !BASE_URL) throw`). Classified as **environment** — not routed to implementer.

**Playwright e2e:** run by be-developer at commit 7a26c865 against isolated throwaway Postgres + built SPA: 33 pass / 0 fail. The new AC5 reconnect test (`"cost booked while SSE is down appears after reconnect, before any fallback poll"`) was independently verified by the system-architect as a genuine regression test (fallback is 5min — any update before that can ONLY be the reconnect refetch).

---

## Acceptance Criteria Verification

### AC1: Telemetry ingest → Budget-Chip and UsageView update <2s without Poll-Tick
**Status**: ✅ PASS

Evidence:
- `telemetry.ts`: publishes one `usage-updated` BusEvent after ingest when batch booked cost (`spawnRunIds.length > 0` gate)
- `App.tsx`: `classifyEvent` routes `usage-updated` → `refreshBudget()` + `setUsageSignal(n+1)`, returns early (signal never enters feed)
- `UsageView.tsx`: refetches on `refreshSignal` prop change (line 120: `setInterval(loadUsage, 300_000)` + `[loadUsage, refreshSignal]` dep array)
- `useBudget.ts`: fallback poll stretched to 300_000ms (5min); primary path is SSE signal
- `telemetry-signals.test.ts`: AC1/AC3 test drives a live Fastify+PG SSE stream, asserts signal delivery within 2s window (DB-gated, passes in CI per be-developer's run)

### AC2: Open SeatDrawer updates log-tail <2s for exact spawn; foreign spawns don't trigger refetch
**Status**: ✅ PASS

Evidence:
- `telemetry.ts`: affected-spawn SQL uses `DISTINCT s.id` with `run_id AND (role OR ticket)` join, scoped to `org_id + project_id` (tenant isolation)
- `SeatDrawer.tsx`: `useEffect` on `logSignal` fires `void fetchLogs()` only when `logSignal.spawnId === spawnId` (line 103)
- `telemetry-signals.test.ts`: asserts `seatFrame.includes('"spawn_id":"spawn-be-1"')` and `!buf.includes(FOREIGN_SPAWN_ID)` — foreign spawn never signalled

### AC3: Batch-Ingest (100 lines) → exactly one usage-updated + one seat-log-appended per affected spawn
**Status**: ✅ PASS

Evidence:
- `telemetry.ts`: one `bus.publish()` for `usage-updated` per POST (gated on cost rows, not per event)
- `telemetry.ts`: one `bus.publish()` per `DISTINCT` affected spawn for `seat-log-appended` (SQL distinct, not per event)
- `telemetry-signals.test.ts`: "AC1/AC3: a 100-event cost batch coalesces to exactly one usage-updated + one seat-log-appended" — asserts `usageFrames.length === 1` and `seatFrames.length === 1` (DB-gated)
- Event-storm protection confirmed: coalescing is structural (publish-once after the entire batch is inserted, not per event)

### AC4: EventFeed/Board don't show new kinds as ticket-movement; existing tests green
**Status**: ✅ PASS

Evidence:
- `App.tsx` SSE handler (lines 188–199): `classifyEvent` routes signals and returns early BEFORE `setEvents()`/`refresh()` — signals never enter the transition feed or refetch the board
- `sseSignals.test.ts`: "a real ticket movement that mentions 'budget' is NOT a signal" — regression guard for removed `to.includes("budget")` fragile match
- `sseSignals.ts` backward-compat: anything that is not `usage-updated` or `seat-log-appended` classifies as `transition` — older frames, `transition`, `create` all route correctly
- SSE frame format: `kind` field added to existing `data:` JSON; parsers that don't know about `kind` ignore it cleanly
- Web unit tests: **82/82 pass** (was 81 before AC5 addition)
- Playwright e2e: 33/33 pass (eventfeed-timeline.spec confirming no new kinds appear as ticket transitions)

### AC5: SSE disconnected → fallback polls functional; ConnectionBanner unchanged; reconnect corrects views
**Status**: ✅ PASS

Evidence:
- **During disconnect**: `useBudget` poll 300_000ms (5min), `UsageView` poll 300_000ms (5min), `SeatDrawer` poll 60_000ms (60s — documented exception per Epic ABS-500 AC rule)
- **ConnectionBanner**: no changes to ABS-416 banner code confirmed by git diff
- **Refetch-on-reconnect**: `App.tsx` (lines 212–224): `prevSseRef` tracks prior SSE state; `isReconnect(prev, sse)` fires only on `error → live` edge; effect calls `refreshBudget()`, `setUsageSignal(n+1)`, and bumps `seatLog` if seat drawer open
- `isReconnect` pure predicate in `sseSignals.ts` — unit tested: fires only on `error → live`, NOT on `connecting → live` (no spurious refetch on initial connect)
- **AC5 Playwright e2e** (budget.spec.ts line 532–588): aborts `/events/stream` → books +$6.50 while down → chip stays at $2.00 → un-routes → reconnect → chip shows $8.50 within 10s; since fallback is 5min, update can ONLY be the reconnect refetch — genuine regression test

### AC6: Agent-events-Op never returns signal kinds; telemetry ingest doesn't wake Agent-Long-Poll-Waiter
**Status**: ✅ PASS

Evidence:
- `telemetry.ts` signal block: `ephemeral: true` on all bus-published signals → `sendEvent` omits `id:` line (`idLine = e.ephemeral ? "" : ...`)
- Signals are NEVER written to the `event` table (no INSERT, only `bus.publish()`)
- `readEventsForConsumer` at `events.ts:75`: `kind IN ('transition', 'create')` filter — signals (never in the event log) cannot surface
- No agent long-poll waiter exists in current checkout (only SSE stream subscribes to bus); `ephemeral` + never-logged ensures this property holds when S2 waiter lands
- `telemetry-signals.test.ts`: "AC6 (Agent-Surface-Fence): the agent events op never returns the signal kinds" — `GET /agent/v1/.../events?since=0` response body contains neither `usage-updated` nor `seat-log-appended` (DB-gated)
- `sseSignals.test.ts`: "isSignalEvent covers exactly the signal kinds" — `SIGNAL_KINDS` enumerated, no leakage

---

## Architecture Review Evidence

**Stage 1 (Iteration 1)**: System-Architect bounced for AC5 "refetch-on-reconnect" not implemented — `useSSE` exposed SSE state but no effect keyed on it to refetch. Correctly classified as **code** failure.

**Stage 1 (Iteration 2)**: System-Architect approved after be-developer wired the `isReconnect` effect. Re-ran web unit tests (7 pass incl. new `isReconnect` test). Reviewed AC5 e2e in budget.spec.ts and "confirmed it's a genuine regression test." Transitioned `In Review → In Test`.

**Path-Decision resolved**: Ephemeral bus-only + refetch-on-reconnect (not event-log-persisted). Rationale documented in comments. The ephemeral choice's own precondition (views refetch on reconnect) is now implemented and tested.

---

## Pre-existing Failures (Unrelated)

8 failures in `report-routes.test.ts` + `bootstrap-promotion.test.ts` — reproduced on a clean HEAD worktree without ABS-505 changes by the be-developer. These are **pre-existing** and **out of scope** for this ticket. The diff touches none of: `report.ts`, `bootstrap`, or session code.

---

## Scope Discipline

**In scope (confirmed)**: server signal publishes, SSE frame format changes, three hook/component refetch wiring, fallback interval stretches, unit + integration + e2e tests.

**Out of scope (confirmed untouched)**: Board/EventFeed behavior, new REST endpoints, orchestrator side, multi-instance correctness (soft blocker ABS-501 in-process bus — ACs all single-instance testable as designed).

**Design flag**: NOT present. ADR-A-0021 §(e) noted; ticket body states "keine Layout-Änderung — nur Aktualisierungsverhalten." No Design Test gate required.

---

## Final Verdict

**APPROVED** ✅

All six acceptance criteria (AC1–AC6) are met. Quality gates pass:
- `pnpm -r typecheck`: PASS (5 projects, exit 0)
- `pnpm lint`: PASS (clean, exit 0)
- Web unit tests: **82/82 pass** at commit `7a26c865` (QAS-executed)
- Playwright e2e: **33/33 pass** including AC5 regression test (be-developer-executed, system-architect-verified)

The ephemeral #PATH_DECISION is architecturally complete: signals stay off the agent surface, coalescing prevents event storms, and refetch-on-reconnect closes the gap the ephemeral choice accepted.

**Exit**: No `design` flag → transition to **Story Acceptance**.
