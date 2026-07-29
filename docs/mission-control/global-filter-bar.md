# Global Filter Bar and URL-Addressable Drawers

Feature shipped in ABS-420 (epic ABS-410). Applies to the Mission Control SPA
(`backend/apps/web`).

---

## Overview

The global filter bar sits in the app shell and persists across all views: Board,
Live Spawns, Event Feed, and Inbox. Setting a filter on the Board and switching to
the Event Feed keeps that filter applied. Reloading the page restores all active
filters from the URL query string.

Deep links let you share or bookmark any ticket drawer or seat drawer. Pasting
`#/ticket/ABS-123` into a retro note opens that ticket directly.

---

## Filter Dimensions

Five dimensions are available:

- **epic** (`?epic=`) — ticket key, e.g. `ABS-410`
- **run** (`?run=`) — run identifier string
- **role** (`?role=`) — agent role slug, e.g. `fe-developer`
- **timeRange** (`?timeRange=`) — one of `""` (all), `1h`, `4h`, `24h`, `7d`
- **project** — handled by the separate project selector in the shell

A dimension selector that does not apply to the current view appears greyed out
with a tooltip. Its value is preserved in the URL so it reactivates when you
switch to a view that uses it.

**Board view**: all four dimensions are interactive.
**Report, ADRs, Policies**: all four appear greyed (values preserved).

---

## Using the Filter Bar

### Set a filter

Select a value from any dropdown in the filter bar. The URL query string updates
immediately (`?epic=ABS-410&role=fe-developer`). Switching views keeps the query
string intact.

### Active filter chips

When any filter is set, chips appear directly below the selectors with no click
required. Each chip shows the dimension and value (e.g. `epic=ABS-410`) with an
`×` to remove it. A `Clear all (N)` button removes all filters at once.

### Empty state

When filters produce no results, the view names the active filters
(`epic=ABS-410, role=fe-developer`) and offers a one-click **Clear all** button.

---

## Saved Filter Presets

Save frequently used filter combinations under a name.

1. Set the filters you want.
2. Type a name in the **Save as** input in the filter bar.
3. Click **Save**. The preset is stored in `localStorage` under the key
   `agentic_saved_filters`.
4. To apply a saved preset: click its name. All dimensions are set at once.
5. To delete a preset: click the `×` next to its name.

Presets survive page reloads and new sessions on the same browser. They are
browser-local and not shared across machines.

---

## URL-Addressable Drawers (Deep Links)

Every ticket drawer and seat drawer is addressable by URL hash.

### Open a ticket drawer

```
https://your-host/#/ticket/ABS-123
```

The drawer opens over whatever view is active. If you arrive with this URL in a
fresh session, the session probe runs first; once authentication resolves, the
drawer opens automatically.

### Open a seat drawer

```
https://your-host/#/seat/fe-developer-1752938c
```

### Close a drawer

Press **Esc** or click outside the drawer. The hash is removed from the URL;
the underlying view URL (including any active query-string filters) is preserved.

### KPI navigation

KPI clicks in the Report view (e.g. a failing-ticket count) set filter state
through the same `useFilterState` hook that the filter bar uses. The resulting
URL is identical to setting those filters manually. Copy the URL after a KPI
click to share the exact filtered view.

---

## Implementation Reference

All paths are relative to `backend/apps/web/src/`.

**`useFilterState.ts`** — URL-persisted filter state hook. Reads query params on
init, writes on every change, syncs on browser `popstate`. Exports `FilterState`,
`EMPTY_FILTERS`, `activeCount`, and `activeDesc`.

**`useDrawerURL.ts`** — URL hash-persisted drawer hook. Parses `#/ticket/<key>`
and `#/seat/<id>` on init; writes hash on open/close; syncs on `popstate`.

**`components/GlobalFilterBar.tsx`** — The single filter bar mounted once in
`App.tsx`. Renders active-filter chips, per-dimension selectors (greyed when not
applicable), and saved-preset controls.

**`App.tsx`** — Shell. Instantiates `useFilterState` and `useDrawerURL`; renders
`GlobalFilterBar`; passes `filters` and `setFilters` as props to each list view.

Each list view receives `filters` and applies only the dimensions it supports.
Views do not hold their own state for the five global dimensions.

---

## Troubleshooting

### Filters are lost after switching accounts

Saved presets are stored in `localStorage` under the browser profile. Switching
to a different browser or private/incognito window starts with empty presets.
Active query-string filters survive because they are in the URL, not in storage.

### A greyed selector shows a value I cannot change

A greyed dimension holds a value set in a view that does support it (e.g. `run`
set while on the Board). Switch back to the Board to edit or clear that dimension,
or use **Clear all** to wipe it.

### Cold navigation opens no drawer

Check that the hash uses the exact patterns `#/ticket/<key>` or `#/seat/<id>`.
A malformed hash (missing leading `/`, unknown kind) is silently ignored.
