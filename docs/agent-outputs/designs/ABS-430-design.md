# ABS-430 Design — EventFeed Filter UI + Run Timeline View

**Ticket**: ABS-410 S9b — EventFeed filter UI + Run Timeline view
**Design artifact**: `docs/agent-outputs/designs/ABS-430-design.md`
**Design system**: `docs/design/DESIGN_SYSTEM.md` (starter template — see *Deviations*)
**De-facto token source**: `backend/apps/web/src/styles.css` `:root` custom properties
  (light theme + `prefers-color-scheme: dark` block)
**Author**: ui-ux-design · 2026-07-18
**Depends on**: ABS-429 (S9a — cursor + server-side filter params), ABS-412 (stall-span events)

---

## 0. Design-System Deviations

`docs/design/DESIGN_SYSTEM.md` is still the boilerplate template (placeholder tokens
`{{COLOR_PRIMARY}}`, etc., not yet filled in for this project). The operative tokens are
the CSS custom properties declared in `backend/apps/web/src/styles.css` — these are the
project's actual design contract. **Deviation reported to System Architect** (deviation D1).

All token references in this document use the CSS-var names from `styles.css`:

| CSS var | Light value | Dark value | Semantic role |
|---|---|---|---|
| `--bg` | `#f4f5f7` | `#0e1116` | page background |
| `--panel` | `#ffffff` | `#171b22` | surface (cards, panels) |
| `--panel-2` | `#eceef1` | `#1f242c` | recessed surface |
| `--text` | `#1b1f24` | `#e6e8eb` | body text |
| `--muted` | `#6b7280` | `#9aa4b2` | secondary/ambient text |
| `--border` | `#d6dae0` | `#2b313a` | dividers, track backgrounds |
| `--accent` | `#2563eb` | `#60a5fa` | primary / spawn state |
| `--live` | `#16a34a` | `#4ade80` | live / completion-ok state |
| `--stale` | `#b91c1c` | `#f87171` | error / stall / completion-err state |
| `--emphasis` | `#fef3c7` | `#3b2f0b` | attention background |
| `--emphasis-border` | `#f59e0b` | `#b7791f` | attention border / command marker |

**Typography**: 14px/1.4 `system-ui, -apple-system, Segoe UI, Roboto, sans-serif`
(from `body { font: 14px/1.4 … }` in `styles.css`).

**Breakpoints** (inferred from `styles.css` `@media` rules already in codebase):

| Breakpoint | Width | Rule |
|---|---|---|
| `mobile` | `< 600px` | Single column; filter controls stack vertically |
| `tablet` | `600–1023px` | Feed sidebar collapses; timeline scrolls horizontally |
| `desktop` | `≥ 1024px` | Full side-by-side layout; timeline visible by default |

---

## 1. Context & Constraints

- **Existing component**: `backend/apps/web/src/components/EventFeed.tsx` — a `<aside
  className="feed">` with a single free-text filter input and an SSE-fed `LiveEvent[]` prop.
  This design **extends** (not rewrites) that component (ADR-A-0010 minimal-change default).
- **Consumed endpoints** (from ABS-429): `GET /api/v1/events?ticket=…&seat=…&kind=…&run=…&cursor=…&limit=…`
  returns `{ events: LiveEvent[], next_cursor: string | null }`.
- **SSE subscription**: existing SSE pattern from `App.tsx` — feed the new filter params as query
  string so the server returns a filtered stream (Follow mode). Browse mode suspends the SSE
  subscription and switches to paginated REST.
- **5-state color language** (from ABS-416 rollup-util, referenced by ABS-410 epic principles 2/4/5):
  spawn=`--accent`, completion-ok=`--live`, completion-err=`--stale`, stall-span=`--stale`
  (hatched, see §3.2), command=`--emphasis-border`, budget=`--stale`. Lane tracks stay `--border`
  (neutral — not any of the 5 state colors).
- **Read-only surface** (ADR-A-0004): this story renders events; write actions (e.g. drawer actions)
  are governed by ABS-418 and must not be added here.
- **Render from typed event fields** (ADR-A-0026): never parse comment body strings; all
  marker placement uses typed `LiveEvent` fields (`kind`, `seq`, `ticket_id`, `seat_role`,
  `run_id`, `spawned_at`, `completed_at`, `exit_code`, `stall_start`, `stall_end`, etc.).

---

## 2. EventFeed — Filter Controls + Follow/Browse Modes

### 2.1 Component Anatomy (extends `.feed` aside)

```
┌ .feed ────────────────────────────────────────────────────────────┐
│ .feed-head                                                        │
│  Live feed                                                        │
│  [ticket ▾]  [seat ▾]  [kind ▾]  [run ▾]  [Follow] [Browse]     │
└───────────────────────────────────────────────────────────────────┘
│ .feed ol  (event list — follows existing markup)                  │
│  · ABS-430  ∅ → Design          (ambient in Follow mode)         │
│  · ABS-412  In Progress → Done                                    │
└───────────────────────────────────────────────────────────────────┘
```

**Filter row elements** (all within `.feed-head`, extending the existing `<input aria-label="filter events">`):

| Element | Type | Wired to | Feed-local |
|---|---|---|---|
| Ticket | `<select>` | S8 global bar (ABS-420) `ticket` dimension | No |
| Seat | `<select>` | S8 global bar (ABS-420) `seat` dimension (if exposed) | No |
| Run | `<select>` | S8 global bar (ABS-420) `run` dimension | No |
| Kind | `<select>` | — | **Yes** (feed-local; not in global bar) |
| Follow / Browse | toggle buttons | mode state (local) | Yes |

**Token assignments — filter row**:
- `<select>` elements: `background: var(--bg)`, `color: var(--text)`, `border: 1px solid var(--border)`,
  `border-radius: 6px`, `padding: 6px 8px` — same pattern as `.report-filters select` in `styles.css`.
- Each `<select>` must have a paired `<label>` (visible or `sr-only`) per accessibility standard.
- `.feed-kind-badge` (per-event kind chip in each list item): `background: var(--panel-2)`,
  `color: var(--muted)` — no rollup state color applied to the badge regardless of event kind.

### 2.2 Follow Mode (default)

- SSE subscription active, filtering by current filter dimensions as query params.
- New events prepend to list (newest first, consistent with current component).
- Event rows are **ambient**: `.feed-to` computed color = `var(--muted)`, NOT `var(--accent)` or
  `var(--text)`. The feed in follow mode mirrors the Home ticker — no accent colors for
  routine transition events. Only errors (`completion exit ≠ 0`, `stall_detected`) may carry
  `var(--stale)` on the relevant field; ordinary status transitions stay `var(--muted)`.
- Mode toggle: `[Follow]` button with `aria-pressed="true"`, `[Browse]` with `aria-pressed="false"`.

### 2.3 Browse Mode (paused + paginated)

- SSE subscription suspended on mode switch.
- Pagination uses ABS-429 cursor: `GET /api/v1/events?…&cursor=<next_cursor>&limit=50`.
- No gaps or duplicates across page boundary: the cursor is opaque (server-side
  sequence pointer) — the client passes it verbatim; it does not render or parse the cursor value.
- Event rows use full-contrast `.feed-to` = `var(--text)` (browse is not ambient; the
  ambient restriction applies only to Follow mode).
- Pagination controls below the list:
  ```
  [← Newer]  page N  [Older →]
  ```
  Buttons: `.btn-secondary` pattern (`background: var(--panel-2)`, `color: var(--text)`,
  `border: 1px solid var(--border)`). Disabled when no cursor in that direction.

### 2.4 Responsive Behaviour

- **Desktop (≥ 1024px)**: `.feed` stays at 260px fixed width (existing); filter row wraps onto
  two lines if needed (`.feed-head` already `flex-wrap: wrap` feasible).
- **Tablet (600–1023px)**: feed sidebar may collapse to an icon tab; filter controls visible
  in the feed drawer when expanded.
- **Mobile (< 600px)**: filter selects stack vertically; Follow/Browse toggle spans full width.

---

## 3. Run Timeline View

### 3.1 High-Level Layout

The Run Timeline is a **new view** (not embedded in the existing board column layout). It occupies
the main `.main` content area when the "Timeline" nav tab is selected (via `.view-nav`).

```
┌ .timeline-view ─────────────────────────────────────────────────────┐
│ .timeline-head                                                       │
│   Run: [run-picker ▾]  (default: latest)                             │
│   Density: [Lifecycle ●] [All ○]                                     │
│                                                                       │
│ .timeline-axis                                                        │
│   00:00  01:30  03:00  04:30  06:00  …  (relative to run start)      │
│                                                                       │
│ .timeline-lanes                                                       │
│  fe-developer · ABS-430  ●━━━━━━━━━━░░░░░━━━━━━━━●                   │
│  po-agent · ABS-430      ●━━━━━●                                      │
│  tdm · ABS-430           ●━━━━━━━━━━━━━━━●                           │
│  … (one lane per seat in the run)                                     │
└──────────────────────────────────────────────────────────────────────┘
```

- **`.timeline-view`**: `flex: 1`, `display: flex`, `flex-direction: column`, `overflow: hidden`,
  `background: var(--panel)`, `border: 1px solid var(--border)`, `border-radius: 10px`,
  `padding: 16px` — mirrors `.report` surface pattern.
- **`.timeline-head`**: `display: flex`, `flex-wrap: wrap`, `align-items: center`, `gap: 12px`,
  `margin-bottom: 12px`.
- **`.timeline-axis`**: horizontal row, `font-size: 11px`, `color: var(--muted)`, tick marks at
  equal intervals.
- **`.timeline-lanes`**: `overflow-x: auto` (scrolls horizontally for long runs); `display: flex`,
  `flex-direction: column`, `gap: 4px`.

### 3.2 Lane Anatomy

```
.lane-row
  .lane-label  "fe-developer · ABS-430"   (role · ticket_id)
  .lane-track  ─────────────────────────────────────
               ●  [━━━━━━░░░░░░░░░━━━━━━━]  ●  ▲
               │   active   stall   active   │  command
               spawn                      completion
```

**Lane elements and tokens**:

| Element | CSS class | Token(s) | Notes |
|---|---|---|---|
| Lane label | `.lane-label` | `color: var(--muted)`, `font-size: 12px`, `white-space: nowrap`, `min-width: 180px` | `role · ticket_id` |
| Lane track | `.lane-track` | `background: var(--border)`, `height: 8px`, `border-radius: 4px`, `position: relative` | **neutral — NOT a state color** |
| Active span | `.lane-active-span` | `background: var(--border)` (same as track; filled bar implied by markers) | drawn between spawn and completion |
| Stall span | `.lane-stall-span` | `background: repeating-linear-gradient(45deg, var(--emphasis), var(--emphasis) 4px, var(--stale) 4px, var(--stale) 8px)`, `height: 8px` | hatched; not solid red |
| Spawn marker | `.marker-spawn` | `background: var(--accent)`, circle `8px × 8px`, `border-radius: 50%` | |
| Completion (exit 0) | `.marker-completion-ok` | `background: var(--live)`, circle | |
| Completion (exit ≠ 0) | `.marker-completion-err` | `background: var(--stale)`, circle | |
| Command marker | `.marker-command` | `color: var(--emphasis-border)`, triangle icon `▲`, `font-size: 10px` | rendered as text node / SVG path |
| Budget marker | `.marker-budget` | `background: var(--stale)`, diamond `◆` | |
| Transition marker (All density) | `.marker-transition` | `color: var(--muted)`, dot `·` | Lifecycle density: not rendered |
| Heartbeat marker (All density) | `.marker-heartbeat` | `color: var(--muted)`, dot `·` | Lifecycle density: not rendered |

**Stall span**: `aria-label="Stalled {N}s"` where N is `stall_end − stall_start` in seconds.
Label text is visible as tooltip/title; when the segment width > 50px, the label is also inline
inside the segment (font-size: 10px, color: var(--text), truncated with ellipsis). Never
color-only communication: the hatch pattern + aria-label + inline text triple-conveys stall state.

**Lane `role="img"` accessibility**: each `.lane-track` element carries
`role="img"` and `aria-label` encoding role, ticket_id, spawned_at, and either
`completed_at` or "still active".

### 3.3 Event Markers — Density Modes

**Lifecycle mode** (default — `.density-lifecycle`):
- Rendered: `spawn` ●, `completion` ●, `stall_span` ░░, `budget` ◆
- NOT rendered in DOM: `command` ▲, `transition` ·, `heartbeat` ·

**All mode** (`.density-all`):
- Rendered: everything above PLUS `command` ▲ (`--emphasis-border`) and `transition` · (`--muted`)
  and `heartbeat` · (`--muted`)

**Density toggle**:
```html
<div role="group" aria-label="Timeline density">
  <button aria-pressed="true"  class="density-btn density-lifecycle">Lifecycle</button>
  <button aria-pressed="false" class="density-btn density-all">All</button>
</div>
```
- Active button: `border-color: var(--accent)`, `color: var(--accent)` (or `background: var(--panel-2)` tint)
- Inactive button: `.btn-secondary` style

### 3.4 Time Axis

- Horizontal axis above the lanes; ticks at regular intervals (e.g. every 30 s or auto-scaled).
- `.axis-label`: `font-size: 11px`, `color: var(--muted)`, relative time from run start
  (e.g. "01:30" for 90 s into the run).
- Axis spans the full scroll width of the lanes.

### 3.5 Run Picker

- `<select>` or searchable combobox listing known run IDs (from ABS-347 run-ID field).
- Default: latest run (most recent `run_id`).
- Label: `<label for="run-picker">Run</label>` (or `aria-label`).
- Token: same `.report-filters select` pattern.

### 3.6 Click Interactions

| Click target | Action |
|---|---|
| `.lane-row` / `.marker-spawn` / `.lane-track` | Opens **Seat Drawer** (ABS-418), passing `spawn_id` / `seat_role` + `ticket_id` |
| `.lane-label` ticket ID portion | Opens **TicketDrawer**, passing `ticket_id` |
| `.marker-completion-*` | Opens **Seat Drawer** (same seat) |
| `.marker-command` | Opens command detail (within Seat Drawer or inline tooltip) |

All interactive elements: `cursor: pointer`, keyboard-focusable (`tabindex="0"`), respond to
Enter/Space with same action as click.

### 3.7 Live Update (SSE — active runs)

- If the selected run is still active (`completed_at = null`), the timeline subscribes to
  the SSE feed filtered by `run_id`.
- New events (`spawn`, `completion`, `stall_detected`, `command_queued`, `budget_warning`)
  update the lanes in-place without a full reload.
- Lane tracks extend rightward as time progresses; new markers appear at the live edge.
- When the run completes, SSE subscription ends and the timeline freezes.

### 3.8 Responsive Behaviour

- **Desktop (≥ 1024px)**: Full timeline visible; `.lane-label` at 180px, track scrolls.
- **Tablet (600–1023px)**: `.lane-label` truncates to 120px; horizontal scroll continues.
- **Mobile (< 600px)**: Timeline is horizontally scrollable; `.lane-label` shows role only
  (ticket truncated); consider "Timeline unavailable — use desktop" fallback if too narrow.

### 3.9 Duration Rendering

- **Seat active time**: rendered as the filled portion of `.lane-active-span` from spawn marker
  to completion marker (or live edge for active seats). No numeric display by default; duration
  appears in the Seat Drawer on click.
- **Stall span duration**: `aria-label="Stalled {N}s"` + inline text when width > 50px.
  Always computed as `stall_end − stall_start` from typed event fields (ADR-A-0026).

---

## 4. Design Acceptance Criteria [ABS-430]

**Design artifact**: `docs/agent-outputs/designs/ABS-430-design.md`
**Design system**: `docs/design/DESIGN_SYSTEM.md` + operative tokens in `backend/apps/web/src/styles.css`
**Date**: 2026-07-18

### Schema Conformance (Design System § Tokens + Components)

- [ ] **DAC-1**: `.lane-track` computed `background` equals `var(--border)` (neutral); NO state
  color (`--accent`, `--live`, `--stale`, `--emphasis`, `--emphasis-border`) appears as a lane
  background — verified by inspecting the element in DevTools.
- [ ] **DAC-2**: Each event marker uses exactly the mapped `--var` from §3.2 token table:
  spawn `--accent`, completion-ok `--live`, completion-err `--stale`, command `--emphasis-border`
  (foreground/icon fill only), budget `--stale`. No other color used for marker fills.
- [ ] **DAC-3**: `.lane-stall-span` renders as `repeating-linear-gradient(45deg, var(--emphasis),
  var(--emphasis) 4px, var(--stale) 4px, var(--stale) 8px)` — **hatched**, not a solid `--stale`
  fill; verified by inspecting the `background` computed value.
- [ ] **DAC-4**: EventFeed Follow-mode: `.feed-to` computed `color` equals `var(--muted)` for
  routine transition events — NOT `var(--accent)` or `var(--text)`. Verified by switching to
  Follow mode and inspecting a routine transition event row.
- [ ] **DAC-5**: EventFeed Browse-mode: `.feed-to` computed `color` equals `var(--text)` (full
  contrast) — the ambient restriction does NOT apply in Browse mode. Verified by switching to
  Browse mode.
- [ ] **DAC-6**: In Lifecycle density mode (default), `command` (▲) and `transition` (·) and
  `heartbeat` (·) marker elements are **absent from the DOM** — verified by DOM inspection (no
  `.marker-command`, `.marker-transition`, `.marker-heartbeat` nodes in `.timeline-lanes`).
- [ ] **DAC-7**: In All density mode, `.marker-command` elements are present and carry
  `color: var(--emphasis-border)` (amber); `.marker-transition` / `.marker-heartbeat` carry
  `color: var(--muted)` — verified by enabling All mode and inspecting marker computed styles.
- [ ] **DAC-8**: `.feed-kind-badge` (per-row kind chip) has `background: var(--panel-2)` and
  `color: var(--muted)` regardless of event kind — verified by inspecting a `spawn` and a
  `completion` row in Follow mode; no state color applied to the badge.

### Accessibility

- [ ] **DAC-9**: Every `<select>` in the EventFeed filter row has a programmatic label
  (`<label>` associated by `for` + `id`, or `aria-label`); verified with axe / screen reader.
- [ ] **DAC-10**: Follow/Browse mode toggle buttons carry `aria-pressed="true"` on the active
  mode and `aria-pressed="false"` on the inactive mode; toggling updates `aria-pressed`
  synchronously — verified via accessibility inspector.
- [ ] **DAC-11**: Each `.lane-track` element carries `role="img"` and `aria-label` encoding
  role, ticket_id, spawned_at, and either completed_at (ISO string) or "still active" — verified
  with accessibility inspector.
- [ ] **DAC-12**: All timeline marker elements (`.marker-spawn`, `.marker-completion-ok`,
  `.marker-completion-err`, `.marker-command`, `.marker-budget`) are keyboard-focusable
  (`tabindex="0"`) and respond to Enter/Space with the same Seat Drawer / TicketDrawer open
  action as a pointer click — verified by Tab-navigation + keyboard activation.
- [ ] **DAC-13**: Stall-span segments carry `aria-label="Stalled {N}s"` (N = computed duration
  in seconds). When segment rendered width > 50px, the label text is also visible inline.
  Color is NEVER the sole conveyor of stall state — hatching + label + text triple-conveys it.
- [ ] **DAC-14**: Density toggle has `role="group"` and `aria-label="Timeline density"`;
  exactly one button has `aria-pressed="true"` at any given time — verified via DOM inspector.
- [ ] **DAC-15**: Text contrast ≥ 4.5:1 for all body text — `.feed-to` in Browse mode
  (`var(--text)` on `var(--panel)`), `.axis-label` (`var(--muted)` on `var(--panel)`), and
  `.lane-label` (`var(--muted)` on `var(--panel)`) — verified with browser contrast tool.
  Note: `var(--muted)` `#6b7280` on `var(--panel)` `#ffffff` = 4.62:1 (passes AA body text).
- [ ] **DAC-16**: Command marker ▲ tooltip/title text renders `var(--text)` on `var(--emphasis)`
  background — light: `#1b1f24` on `#fef3c7` ≥ 14:1 (pass). The marker icon fill uses
  `var(--emphasis-border)` `#f59e0b` on `var(--panel)` `#ffffff` = 2.83:1 which is
  non-text/decorative-only (the label carries the information) — verified that the text
  label/tooltip achieves ≥ 4.5:1 contrast.
- [ ] **DAC-17**: Focus ring is visible on all interactive elements (markers, toggle buttons,
  lane rows, filter selects, mode toggle, run picker) in both light and dark themes — verified
  by Tab-navigating the Timeline and EventFeed in both color schemes.
- [ ] **DAC-18**: `prefers-reduced-motion` media query suppresses any CSS transition/animation
  on the live-edge timeline extension — verified by enabling "Reduce motion" in OS settings
  and confirming no animated movement of lane tracks.

### Responsive Breakpoints

- [ ] **DAC-19**: At **desktop (≥ 1024px)**: `.feed` sidebar visible at 260px; timeline view
  shows all lanes with `.lane-label` at ≥ 180px; no horizontal body scroll.
- [ ] **DAC-20**: At **tablet (600–1023px)**: timeline scrolls horizontally within `.timeline-lanes`;
  `.lane-label` truncates gracefully; filter row wraps without overflow.
- [ ] **DAC-21**: At **mobile (< 600px)**: EventFeed filter selects stack vertically; Follow/Browse
  toggle spans full width; timeline degrades gracefully (horizontal scroll or fallback message).

### User Flows

- [ ] **DAC-22**: Operator opens EventFeed, selects ticket `ABS-430` from the ticket filter and
  `gate-results` from the kind filter, switches to Browse mode → list shows only `gate-results`
  events for ABS-430, paginated; Next/Previous buttons navigate pages with no gap or duplicate
  at the page boundary. E2e asserts: `ticket=ABS-430&kind=gate-results` query on both Browse
  REST calls + no seq-ID overlap between pages.
- [ ] **DAC-23**: Operator selects the latest run in the Run Timeline → one lane renders per
  seat; the ABS-412 fixture stall span is visible as a hatched segment on the correct seat lane;
  spawn, completion, and budget markers are present. E2e asserts marker element presence and
  `data-seat` / `data-kind` attributes match expected lane assignment.
- [ ] **DAC-24**: Operator clicks a seat lane → Seat Drawer (ABS-418) opens for that seat.
  Operator clicks a ticket ID in the lane label → TicketDrawer opens for that ticket.
  E2e asserts both drawer `data-testid` elements appear after the respective clicks.
- [ ] **DAC-25**: With a still-active run selected, a new `spawn` event arrives via SSE → a new
  lane appears in the timeline (or an existing lane extends) without a page reload. E2e asserts:
  after injecting a synthetic SSE event, the lane count increases / the lane track width changes
  within 500 ms, no full page navigation occurs.
