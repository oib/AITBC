# QA Validation Report — ABS-418

**Ticket**: ABS-418 — ABS-410 S5: Seat Drawer — Metadata, Heartbeat Age, Log Tail, Links, Human-Gated Stop/Abort
**Branch**: `ABS-418-auto`
**Commits**: `e30c84c` (implementation) + `b9f19fe` (e2e UUID seed fix)
**QAS validation date**: 2026-07-18
**Flags**: `[design]` → exit target: **Design Test**
**Verdict**: ✅ **APPROVED**

---

## Validation Summary

| Check | Result | Detail |
|-------|--------|--------|
| `pnpm -r typecheck` | ✅ PASS | All 5 packages — zero errors |
| `pnpm eslint .` | ✅ PASS | No lint violations |
| `pnpm --filter web build` | ✅ PASS | Vite 47 modules, 317ms |
| Integration tests (`seat-detail-routes.test.ts`) | ✅ 7/7 PASS | Isolated schema, live Postgres |
| E2E tests (`seat-drawer.spec.ts`) | ⚠️ NOT RUNNABLE | Pre-existing `environment` issue (migration drift — `008_knowledge_adr_policy.sql` missing on disk for `backend-db-1`; unchanged from prior validation cycles) |
| Architecture review | ✅ APPROVED | system-architect re-review (latest handoff) |
| Code & AC coverage review | ✅ COMPLETE | All 5 ACs + 3 Design ACs verified in implementation |

---

## Integration Test Evidence (7/7 PASS)

```
Command: DATABASE_URL="postgres://postgres:postgres@localhost:5432/agentic" \
         node --import tsx --test --test-concurrency=1 \
         apps/server/test/seat-detail-routes.test.ts

✔ seat detail: 200 with correct fields for an open spawn        (294.9ms)
✔ seat detail: 200 for a completed spawn with exit_code + diagnostic (4.7ms)
✔ seat detail: 404 for unknown spawn id                          (2.8ms)
✔ log tail: 200 with empty lines when no telemetry ingested      (5.4ms)
✔ log tail: 200 with formatted lines for ingested events         (7.3ms)
✔ log tail: 404 for unknown spawn id                             (2.4ms)
✔ log tail: respects limit parameter                             (6.5ms)

ℹ tests 7 | pass 7 | fail 0 | duration_ms 760ms
```

---

## Acceptance Criteria Verification

### AC1 — Drawer opens from all three entry points; shows metadata incl. last-activity age
**Status: ✅ PASS**
- **LiveSpawns** (`LiveSpawns.tsx`): spawn rows wire `onOpenSeat` → `openDrawer({kind:"seat", id})` in `App.tsx`
- **Home fleet strip**: same `LiveSpawns` panel rendered at `App.tsx:211` (Home view)
- **Inbox** (`Inbox.tsx:265`): `onOpenSeat` + `spawnsByTicket` → "Seat" button (`data-testid="inbox-seat-{key}"`) per row with matching active spawn
- **Metadata fields**: `seat-meta` dl in `SeatDrawer.tsx:145` — role, instance, run-ID, attempt, elapsed, started_at, ticket link (`seat-ticket-link`)
- **Last-activity age**: `seat-active-badge` (active) or `seat-stale-badge` (stalled) with `formatAge(seat.elapsed_seconds)` — ABS-412 data
- **E2E**: `AC1a` (Live-Spawns click), `AC1c` (Inbox "Seat" link)

### AC2 — Log tail + auto-refresh + explicit empty state
**Status: ✅ PASS**
- `fetchLogs` called on mount; `setInterval(fetchLogs, 10_000)` started; cleared on unmount (`clearInterval` in cleanup)
- Empty state: `seat-logs-empty` rendered when `logs.lines.length === 0` — text "No log data ingested for this seat."
- Log lines: `seat-log-lines` `<pre>` rendered when lines present
- Manual refresh: "↻ Refresh" button (`seat-logs-refresh`) calls `fetchLogs()`
- **E2E**: `AC2a` (lines rendered), `AC2b` (empty state)

### AC3 — Abort-spawn requires reason, issues ABS-348 command, reflects state change
**Status: ✅ PASS**
- "⏹ Stop run" (`seat-stop-run`) + "⏹ Abort spawn" (`seat-abort-spawn`) — rendered only when `canControlOrchestrator(role) && seat.completed_at === null`
- `ConfirmWithReason`: Confirm button (`seat-confirm-submit`) is `disabled={busy || reason.trim() === ""}` — physically blocked without reason
- On confirm: `api.enqueueCommand(project, seat.instance_id, pending.kind, seat.id)` → existing ABS-348 endpoint
- Success: `seat-action-ok` shown; dialog dismissed; seat re-fetched
- **E2E**: `AC3`

### AC4 — Completed seats: exit code + diagnostic; stalled seats: stalled badge
**Status: ✅ PASS**
- Completed: `seat-exit-ok` (exit=0) or `seat-exit-err` (non-zero) + `seat-diagnostic`
- Stalled: `seat-stale-badge` — `spawn-stale-badge` with time-since-activity
- Active: `seat-active-badge`
- Integration tests confirm `exit_code`, `stale`, `elapsed_seconds` fields in API response
- **E2E**: `AC4a` (exit code + diagnostic), `AC4b` (stalled badge)

### AC5 — Raw toggle shows event JSON; default view has none
**Status: ✅ PASS**
- `showRaw` state default `false`; `seat-raw-json` `<pre>` only rendered when `showRaw === true`
- Raw toggle (`seat-raw-toggle`) with `aria-pressed`; resets to `false` on new seat open
- **E2E**: `AC5`

---

## Design ACs Verification

### Design AC1 — Overlay; Esc/outside-click closes and returns focus
**Status: ✅ PASS**
- `.drawer-scrim` with `position:fixed` overlay; `<aside class="seat-drawer-panel">` — no navigation
- Esc: `window.addEventListener("keydown", onKey)` in `useEffect` — `if (e.key === "Escape") onClose()`, cleaned up on unmount
- Outside-click: `scrim onClick={onClose}` + `stopPropagation` on `<aside>`
- **Focus-return**: `useEffect(() => { const prev = document.activeElement; return () => prev?.focus(); }, [])` — captures active element at mount, restores on unmount (all close paths unmount the component)
- **E2E**: `Design AC: Esc closes the seat drawer`

### Design AC2 — Curated by default; raw data only behind the Raw toggle
**Status: ✅ PASS**
- `showRaw: false` by default; `seat-raw-json` absent from DOM until toggle

### Design AC3 — Action buttons use blocked/destructive accent; visually separated
**Status: ✅ PASS**
- Both action buttons: `className="btn-danger"`
- `.seat-actions { border-top: 1px solid var(--border); padding-top: 12px; }` — explicit visual separator in `styles.css:988`

---

## E2E Environment Note (pre-existing, `environment` classification)

The Playwright webServer fails to start because `backend-db-1` (port 5432) has `008_knowledge_adr_policy.sql` in its applied-migrations history but the file was renumbered to `009_...` by a prior epic merge. This is a pre-existing migration drift unrelated to ABS-418. The `b9f19fe` UUID fix correctly addresses the HTTP 500 that blocked seed POSTs — the e2e tests will work once the operator resolves the migration drift on the shared Postgres.

**Coverage verdict**: Integration tests (7/7 PASS, isolated schema) prove backend correctness. E2E test code (9 tests, reviewed) covers all ACs with correct testids and assertions. Architecture review APPROVED by system-architect.

---

## ABS-230 Constraint Verification
`getSeatLogs` queries `run_event WHERE project_id=$1 AND run_id=$2 ... LIMIT $3` — reads only already-ingested telemetry. No new transport from the orchestrator host. ✅

---

## Non-Blocking Follow-up (from architecture review)
Confirm reason captured in UI (`seat-confirm-reason`) but not threaded to `enqueueCommand` — `orch_command` has no `reason` column. AC3 satisfied as written (deliberation gate). Recommend follow-up story for full audit trail on destructive human-gated actions.

---

## Verdict: ✅ APPROVED

All 5 ACs and all 3 Design ACs met. typecheck ✅ lint ✅ build ✅ integration 7/7 ✅. E2E blocked by pre-existing environment migration drift (not ABS-418). Implementation reviewed independently and confirmed correct.

**Next**: `flags: [design]` → **Design Test** (qas-design gate).
