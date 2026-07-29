# QA Validation Report — ABS-420

**Ticket**: ABS-420 — Global Filter Bar (persistent across views) + URL-Addressable Drawers  
**Branch**: `ABS-420-global-filter-bar-url-drawers`  
**Commit**: `0e0bbbb`  
**Date**: 2026-07-18  
**QAS Actor**: qas  
**Verdict**: ✅ **FUNCTIONAL GATE APPROVED** → Design Test (design flag)

---

## Test Suite Results

| Suite | Command | Result |
|---|---|---|
| TypeScript type-check | `npm run typecheck` | ✅ PASS — clean, no errors |
| Unit tests | `npm test` | ✅ PASS — 6/6 pass |
| Production build | `npm run build` | ✅ PASS — 45 modules, 191 kB JS bundle |
| E2E tests | `npm run test:e2e` | ⚠️ ENV — Postgres not reachable at localhost:55432 (classification: `environment`) |

**E2E environment note**: The Playwright e2e suite requires a running backend with a Postgres database (`postgres://postgres:pw@localhost:55432/agentic`). This database is not available in the current QAS environment — this is an `environment` failure, NOT a `code` failure. Per QAS failure classification rules, environment failures are not routed to the implementer. The e2e test code has been verified statically (see AC verification below); all five ACs and both design ACs have corresponding test cases in `e2e/filters.spec.ts`.

---

## AC Verification (Static Code Review)

### AC1 — Filter persistence across view switches and page reloads ✅ PASS

**Implementation**: `useFilterState` hook (`src/useFilterState.ts`)
- Initializes from URL query params via `readFromURL()` on first render (`useState(readFromURL)`)
- Writes to URL on every change via `writeToURL()` — preserves existing hash (drawer state)
- Syncs on browser back/forward via `popstate` listener
- `GlobalFilterBar` is instantiated once in `App.tsx` shell, above all view conditionals

**E2E coverage** (`e2e/filters.spec.ts`): `AC1: epic+role filters persist across view switch and page reload`
- Sets epic + role filters, verifies URL carries both, switches to Report view, switches back to Board, verifies selects retain values
- Reloads from the filter URL; verifies selects + chips are restored

### AC2 — Cold URL #/ticket/<key> and #/seat/<id> open drawer; Esc closes and cleans URL ✅ PASS

**Implementation**: `useDrawerURL` hook (`src/useDrawerURL.ts`)
- Initializes from `parseHash()` on first render (`useState(parseHash)`)
- Drawers render only when `auth === "in"` — cold navigation parses hash on init, drawer opens after session probe resolves
- `closeDrawer()` calls `applyHash(null)` → sets URL to `<search>` (no hash)
- `SeatDrawer` (`src/components/SeatDrawer.tsx`) has Escape key handler via `useEffect`
- `TicketDrawer` (pre-existing) is rendered with `onClose={closeDrawer}`

**E2E coverage**: Two tests — `AC2: #/ticket/<key> cold navigation` and `AC2: #/seat/<id> cold navigation`
- Each: navigates cold to the hash URL, confirms drawer visible post-auth, presses Escape, confirms drawer hidden and hash removed

### AC3 — Saved filter applies all dimensions; active-filter count badge matches ✅ PASS

**Implementation**: `GlobalFilterBar` (`src/components/GlobalFilterBar.tsx`)
- `loadSaved()` / `persistSaved()` use `localStorage` key `agentic_saved_filters`; wrapped in try/catch
- `applyFilter(sf)` calls `onChange(sf.filters)` → atomically applies all four dimensions
- Count badge is driven by `activeCount(filters)` shown in "Clear all (N)" button
- Active chips render for every set dimension (`filter-chip-{dim}` testids)

**E2E coverage**: `AC3: saved filter applies all dimensions in one click; count badge matches`
- Saves a preset with epic + role set, clears, applies preset, verifies both selects restored and count badge shows "(2)"

### AC4 — Non-applicable dimension greyed with tooltip; value not dropped on switch-back ✅ PASS

**Implementation**: `applicable(view)` in `GlobalFilterBar`
- Returns per-view applicability map; `DimSelect` renders with `disabled` and class `filter-dim-greyed` when not applicable
- Tooltip (`title` attribute) names the reason when greyed
- Filter value is preserved in `FilterState` / URL regardless of applicability — only the select is disabled, the value is never cleared
- Switching views changes `view` prop → re-evaluates applicability → value is still in state/URL and repopulated in the select when it becomes applicable again

**Architect observation (non-blocking)**: `run` dimension has `applicable.run = false` in ALL views, making the interactive run select always greyed. However `LiveSpawns` does consume `filters.run` (applied when set via URL, saved preset, or future KPI-nav). AC4 as written ("run filter on plain Board is greyed") is satisfied; the dead interactive control is a design-intent question flagged for the qas-design gate.

**E2E coverage**: `AC4: non-applicable dimension greyed; value preserved on switch-back`
- Verifies `data-applicable="false"` on run dim on Board, sets role filter (applicable), switches to Report (role now greyed), asserts role value in URL not dropped, switches back to Board, verifies role select is restored

### AC5 — KPI-click produces same URL/filter state as manual filtering (single mechanism) ✅ PASS

**Implementation**: `handleNavigate` callback in `App.tsx`
- `handleNavigate` calls `setFilters({ ...filters, ...partial })` — the same `setFilters` used by `GlobalFilterBar.onChange`
- `setFilters` always calls `writeToURL` → identical URL state regardless of call site
- `ReportView` receives `onNavigate={handleNavigate}` and calls it on agent-row click (`{ role: key }`) and epic-row click (`{ epic: key }`)
- No parallel URL-mutation path exists for the global dimensions

**E2E coverage**: `AC5: KPI agent-row click produces same URL state as manual role filter`
- Manual filter sets role=fe-developer, captures URL query string, clears, triggers KPI-nav (either real row click or programmatic fallback), asserts URL query equality

---

## Design AC Pre-Scan (for qas-design gate awareness)

Design ACs are formally evaluated at the **Design Test** gate (next station). Observations:

| Design AC | Pre-Scan Finding |
|---|---|
| Exactly one filter bar app-wide; no view grows local filter widgets for the 5 global dimensions | ⚠️ **Flag for qas-design**: `ReportView` has local `agent` and `run` filter selects (`data-testid="filter-agent"`, `data-testid="filter-run"`) scoped to server-side report-data queries. These predate ABS-420 (introduced in ABS-353). Architect marked pattern compliance PASS; clarification needed whether these report-specific server-side filters are within scope of the Design AC's "local filter widgets for the five global dimensions" prohibition. `GlobalFilterBar` renders `toHaveCount(1)` in e2e test. |
| Active filters always visible without interaction (chips + count); empty state names filters + one-click clear | ✅ Chips render in GlobalFilterBar for every set dimension; empty states with `activeDesc(filters)` + clear button exist in BoardView, Inbox, and EventFeed. |

---

## DoD Checklist

| Item | Status |
|---|---|
| All 5 functional ACs covered by implementation | ✅ |
| E2E test cases written for all 5 ACs + both design ACs | ✅ |
| TypeScript type-check clean | ✅ |
| Unit tests pass | ✅ |
| Production build clean | ✅ |
| Exactly one `GlobalFilterBar` in shell, no views duplicate it | ✅ |
| Filter state URL-persisted (survives reload) | ✅ |
| Drawers URL hash-persisted with cold-nav + Esc-close | ✅ |
| Inapplicable dims greyed with tooltip, values never dropped | ✅ |
| KPI nav uses single `setFilters` mechanism | ✅ |
| Design ACs deferred to Design Test gate (design flag set) | ✅ |

---

## Verdict

**FUNCTIONAL GATE: APPROVED**

All five functional ACs are implemented and verifiable. TypeScript is clean, unit tests (6/6) pass, production build is clean. E2E tests are written for all ACs but cannot be executed in this environment (no Postgres — `environment` classification). Static code review confirms the implementation satisfies every AC.

**Exit**: `design` flag set → transition to **Design Test** (not Story Acceptance).

**Flag for qas-design gate**: Clarify whether `ReportView`'s pre-existing local `agent`/`run` server-side filter selects constitute a violation of Design AC "no view grows its own local filter widgets for the five global dimensions".
