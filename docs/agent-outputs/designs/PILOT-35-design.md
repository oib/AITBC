# Design: PILOT-35 — Mission Control Event-Feed: Relative Time + Tooltip

**Ticket**: PILOT-35 — Mission Control: Event-Feed-Einträge zeigen relative Zeit (0m/4m/1h) + volles Datum on hover
**Design by**: ui-ux-design
**Date**: 2026-07-25
**Design system**: `docs/design/DESIGN_SYSTEM.md`
**Token source**: `backend/apps/web/src/theme.css` + `backend/apps/web/src/styles.css`
(design-system file is a starter template with `{{PLACEHOLDER}}` tokens; real resolved
values live in the CSS files — pre-existing deviation, reported to System Architect in
ABS-352, ABS-419, ABS-473, ABS-430, PILOT-33 — see §10)
**ABS-470 time utility**: `backend/apps/web/src/lib/formatTime.ts` — verbatim reuse, no second implementation
**a11y pattern**: ABS-467 `title` + `aria-label` tooltip pattern (same as Attention Queue in `Inbox.tsx`)

---

## 1. Design Goal

Every entry in the Event-Feed and the Home Live Ticker currently shows WHAT happened
(ticket, status, kind) but not WHEN. The operator cannot instantly judge whether an event
is fresh (seconds ago) or stale (hours ago) without cross-referencing other surfaces.
This is the "halbe Information" gap identified in the v3-Pilot #3 operator finding.

This design adds:

1. **Relative age** per event entry (e.g. `0s`, `4m`, `3h`, `2d`) in both surfaces —
   **verbatim reuse of `formatAge()` from `lib/formatTime.ts` (ABS-470); zero new
   time-formatting code**.
2. **Full absolute timestamp as a native tooltip** on hover (title attribute) — same pattern
   as the Attention Queue (`Inbox.tsx` line 240): `title={formatAbsolute(iso)}`.
3. **Live ticking** at 30 s interval via a single `setInterval` per component —
   no per-second re-render of the feed.
4. **a11y**: both the `title` attribute (tooltip) and `aria-label` (screenreader) carry the
   full absolute timestamp, consistent with ABS-467 non-color conveyor principle.

**Surfaces in scope**:
- `EventFeed.tsx` — Follow-mode and Browse-mode `EventRow` items (ABS-430)
- `HomeView.tsx` — Home Ticker `<li>` items (ABS-416)

---

## 2. Design Token Mapping

De-facto token source: `backend/apps/web/src/styles.css` `:root` block.
**Deviation from DESIGN_SYSTEM.md template** — see §10.

| Design token | CSS var | Light | Dark | Usage in this design |
|---|---|---|---|---|
| `color.text` (muted) | `var(--muted)` | `#6b7280` | `#9aa4b2` | Age stamp text and ticker-age text |
| `color.border` | `var(--border)` | `#d6dae0` | `#2b313a` | Feed-item border (unchanged) |
| `font.size.sm` | 11px | — | — | Age stamp font-size (same as badges, ticker text) |
| `spacing.xs` | 4px / `gap: 3px` | — | — | Gap between label and age stamp |

**Components used** (design system § Components):
- No new components introduced.
- The age stamp is a plain `<span>` with `title` / `aria-label` attributes — consistent with
  the Attention Queue age pattern and ABS-467 tooltip pattern.

**ABS-470 utility reuse** (non-negotiable constraint from the ticket):

```typescript
// from backend/apps/web/src/lib/formatTime.ts (ABS-470)
formatAge(seconds: number): string   // "45s" | "4m" | "3h" | "2d"
formatAbsolute(input): string        // "2026-07-19 14:02:40"
```

Both functions are imported directly from `../lib/formatTime` in the changed files.
`util.ts` re-exports `formatAge` for backward compat but direct import is preferred
for clarity.

---

## 3. Component Anatomy — EventFeed (`EventFeed.tsx`)

### 3.1 Current `EventRow` (no timestamp)

```
li.feed-item[.feed-item-follow]
  span.feed-kind-badge     ← kind
  button.linkbtn.feed-ticket-link (or span.key)  ← ticket
  span.muted               ← seat
  span.feed-to[.feed-to-follow]  ← label/status
```

### 3.2 New `EventRow` (with age stamp)

```
li.feed-item[.feed-item-follow]
  span.feed-kind-badge     ← kind (unchanged)
  button.linkbtn.feed-ticket-link (or span.key)  ← ticket (unchanged)
  span.muted               ← seat (unchanged)
  span.feed-to[.feed-to-follow]  ← label/status (unchanged)
  span.feed-event-age      ← NEW: relative age + absolute tooltip
    [title={formatAbsolute(event.occurred_at)}]
    [aria-label="{formatAge(ageS)} ago — {formatAbsolute(event.occurred_at)}"]
    [data-testid="feed-event-age"]
    "{formatAge(ageS)}"    ← e.g. "4m", "3h", "2d"
```

**Notes**:
- The age span is rendered only when `event.occurred_at` is truthy. Follow-mode events
  go through `liveToRun()` which already maps `LiveEvent.at → RunEvent.occurred_at`
  (confirmed in `EventFeed.tsx` `liveToRun` function). No data-model change required.
- `margin-left: auto` in the flex row pushes the age to the right edge of the feed item
  on desktop. On narrow widths (`flex-wrap: wrap` already active on `.feed-item`), the
  age wraps gracefully to a new line below the label — no clipping.
- In Follow mode, the age stamp inherits the ambient opacity of `.feed-item-follow`
  (`opacity: 0.9`). No additional opacity override is needed.

### 3.3 Re-render mechanism (30 s tick)

A single `now` state in `EventFeed` drives all age computations. The interval fires once
per 30 s (not per second), so a feed with 50 rows triggers 1 state update per 30 s:

```typescript
// Inside EventFeed component (before return):
const [now, setNow] = useState(() => Date.now());
useEffect(() => {
  const t = setInterval(() => setNow(Date.now()), 30_000);
  return () => clearInterval(t);   // cleanup on unmount
}, []);
```

`now` is passed as a prop to `EventRow`:

```typescript
// EventRow signature extension:
function EventRow({
  event,
  follow,
  onOpenTicket,
  now,                    // NEW
}: {
  event: RunEvent;
  follow: boolean;
  onOpenTicket?: (key: string) => void;
  now: number;            // NEW: ms timestamp from Date.now()
}) {
  const ageS = Math.max(0, Math.floor((now - new Date(event.occurred_at).getTime()) / 1000));
  // ...
}
```

`Math.max(0, ...)` guards against clock skew returning a negative age.

**Usage at render site**:
```tsx
{shown.map((e) => (
  <EventRow key={e.seq} event={e} follow={follow} onOpenTicket={onOpenTicket} now={now} />
))}
```

---

## 4. Component Anatomy — Home Ticker (`HomeView.tsx`)

### 4.1 Current ticker `<li>` (no timestamp)

```
li.home-ticker-item[data-testid="ticker-item"]
  span.home-ticker-key  "{e.ticket_id}"
  " → "
  span.home-ticker-to[title={e.to}]  "{ROLLUP_LABEL[rollupState(e.to)]}"
```

### 4.2 New ticker `<li>` (with age stamp)

```
li.home-ticker-item[data-testid="ticker-item"]
  span.home-ticker-key  "{e.ticket_id}"
  " → "
  span.home-ticker-to[title={e.to}]  "{ROLLUP_LABEL[rollupState(e.to)]}"
  " "
  span.home-ticker-age     ← NEW: relative age + absolute tooltip
    [title={formatAbsolute(e.at)}]
    [aria-label="{formatAge(ageS)} ago — {formatAbsolute(e.at)}"]
    [data-testid="ticker-event-age"]
    "{formatAge(ageS)}"
```

**Notes**:
- `e.at` is `LiveEvent.at` (ISO 8601 string). No data-model change.
- A leading space character (`{" "}`) before the age span separates it visually from
  the label in the inline flow. No flex change required for the ticker item.

### 4.3 Home Ticker re-render mechanism (30 s tick)

Same pattern as EventFeed — one `now` state in `HomeView`:

```typescript
// Inside HomeView component (alongside existing useMemo/useState):
const [now, setNow] = useState(() => Date.now());
useEffect(() => {
  const t = setInterval(() => setNow(Date.now()), 30_000);
  return () => clearInterval(t);
}, []);
```

Age computation inline at the render site:
```tsx
{ticker.map((e) => {
  const ageS = Math.max(0, Math.floor((now - new Date(e.at).getTime()) / 1000));
  return (
    <li key={e.seq} className="home-ticker-item" data-testid="ticker-item">
      <span className="home-ticker-key">{e.ticket_id}</span>
      {" → "}
      <span className="home-ticker-to" title={e.to}>
        {ROLLUP_LABEL[rollupState(e.to)]}
      </span>
      {" "}
      <span
        className="home-ticker-age"
        title={formatAbsolute(e.at)}
        aria-label={`${formatAge(ageS)} ago — ${formatAbsolute(e.at)}`}
        data-testid="ticker-event-age"
      >
        {formatAge(ageS)}
      </span>
    </li>
  );
})}
```

---

## 5. CSS Additions (`backend/apps/web/src/styles.css`)

Append this block to the PILOT-35 CSS section:

```css
/* ---- PILOT-35: per-entry event age stamp ---- */

/* EventFeed: age stamp pushed to right edge of the flex row */
.feed-event-age {
  font-size: 11px;
  color: var(--muted);
  white-space: nowrap;
  margin-left: auto;     /* pushes right within .feed-item flex row */
  flex-shrink: 0;
  cursor: default;       /* title tooltip activates on hover — no pointer needed */
}

/* Home Ticker: age stamp inline (ticker item is not flex; trailing inline span) */
.home-ticker-age {
  font-size: 11px;
  color: var(--muted);
  white-space: nowrap;
  cursor: default;
}
```

**Token audit**:
- `var(--muted)` `#6b7280` on `var(--panel)` `#ffffff` → ~4.62:1 ✓ AA body text
- `var(--muted)` `#9aa4b2` on `var(--panel)` dark `#171b22` → ~4.47:1 ✓ AA (dark theme;
  confirmed via ABS-475 muted-on-panel table)
- 11px is non-body text size — 3:1 threshold applies for large text; at 11px it is
  caption/label text, not "large text". The ~4.62:1 ratio exceeds AA small text (≥4.5:1) ✓

---

## 6. Imports Required

### `EventFeed.tsx` additions

```typescript
// Add to existing imports at top of EventFeed.tsx:
import { formatAge, formatAbsolute } from "../lib/formatTime";
```

(Currently neither is imported in EventFeed.tsx. Both are in `lib/formatTime.ts` as
named exports per ABS-470.)

### `HomeView.tsx` additions

`formatAbsolute` is already imported; `formatAge` needs to be added:

```typescript
// Current (line 5): import { formatAbsolute, formatDate } from "../lib/formatTime";
// Updated:
import { formatAge, formatAbsolute, formatDate } from "../lib/formatTime";
```

(HomeView currently imports `formatAge` from `"../util"` at line 4. The implementer
should consolidate to `lib/formatTime` or keep the util import — both resolve to the
same function. No new implementation either way.)

---

## 7. Responsive Behaviour

Breakpoints from `styles.css` `@media` rules (established in ABS-430):

| Breakpoint | Width | Event-Feed age | Ticker age |
|---|---|---|---|
| `desktop` (≥1024px) | `.feed` at fixed width | Age flush-right in row (margin-left: auto) | Inline trailing span |
| `tablet` (768–1023px) | `.feed` may scroll | Age wraps to new line when row is narrow (flex-wrap existing) | Inline trailing span |
| `mobile` (<600px) | `.feed` full-width | Age wraps below label | Inline trailing span |

At mobile, `.feed-item` already has `flex-wrap: wrap` (from `styles.css` line 517).
The `margin-left: auto` on `.feed-event-age` means at full-width the age is right-aligned;
when the item is too narrow to fit in one line, the age wraps to a second line starting
from the right. This is acceptable and matches the behavior in `.attention-top` in Inbox.tsx.

---

## 8. Accessibility Specification

Per design system WCAG 2.1 AA standard (carried from ABS-416, ABS-417, ABS-467).

**Tooltip (title attribute)**:
- `title={formatAbsolute(event.occurred_at)}` → renders "2026-07-19 14:02:40" as the
  native browser tooltip on hover over the age stamp. This is the same pattern used in:
  - `Inbox.tsx` line 240: `title={formatAbsolute(item.created_at)}`
  - `HomeView.tsx` line 212: `title={o.last_seen ? formatAbsolute(o.last_seen) : ""}`
  - ABS-467 established this pattern as the project tooltip convention.

**Screenreader access (aria-label)**:
- `aria-label={"{ageS} ago — {formatAbsolute(iso)}"}` on the age `<span>` provides
  the full timestamp to screenreaders. The `title` attribute alone is not reliably
  announced; `aria-label` overrides the visible text for screenreaders and delivers
  the full date+time string directly.
- Example: `aria-label="4m ago — 2026-07-25 09:15:32"`.
- This supersedes the visible text ("4m") with a richer description that does not
  require the screenreader user to hover.

**Non-color conveyor**: the age is purely textual (e.g. "4m"). No color is used to
convey temporal urgency — the text value itself carries the information.

**Focus**: the `<span>` is not focusable (`tabindex` not set). This is correct — it is
a passive label, not an interactive element. The tooltip (full date) is accessible via
`aria-label` without requiring Tab focus.

**Keyboard tooltip**: native `title` shows only on hover, not on keyboard focus on
non-interactive elements. The `aria-label` compensates: screenreader users get the full
value without requiring the pointer.

**Focus order**: unchanged — no new interactive elements are introduced.

**Contrast**:
- `.feed-event-age` / `.home-ticker-age` use `var(--muted)` — contrast ratio ≥4.62:1
  on both light (`#6b7280` on `#ffffff`) and dark (`#9aa4b2` on `#171b22`) themes.
  Passes WCAG AA for text ≥11px (caption size; treated as small text → ≥4.5:1 threshold).

---

## 9. Modified Files Summary

| File | Change type | Description |
|---|---|---|
| `backend/apps/web/src/components/EventFeed.tsx` | Modify | (1) Import `formatAge`, `formatAbsolute` from `../lib/formatTime`. (2) Add `now: number` prop to `EventRow`. (3) Render `.feed-event-age` span after `.feed-to` in `EventRow`. (4) Add `now` state + 30 s `setInterval` useEffect in `EventFeed`. (5) Pass `now` to each `<EventRow>`. |
| `backend/apps/web/src/components/HomeView.tsx` | Modify | (1) Add `formatAge` to import from `../lib/formatTime` (or confirm existing `util` import). (2) Add `now` state + 30 s `setInterval` useEffect. (3) Render `.home-ticker-age` span per ticker item. |
| `backend/apps/web/src/styles.css` | Modify | Append PILOT-35 CSS block (`.feed-event-age`, `.home-ticker-age`). |
| `backend/apps/web/src/lib/formatTime.ts` | **No change** | ABS-470 utility reused verbatim. Do not modify. |
| `backend/apps/web/src/types.ts` | **No change** | `RunEvent.occurred_at` and `LiveEvent.at` already exist. |

**No backend changes required** — all timestamps already flow from the server to the
frontend in existing fields.

---

## 10. Design System Deviation Report

**Deviation 1** (Critical — pre-existing, ongoing): `docs/design/DESIGN_SYSTEM.md`
contains only `{{PLACEHOLDER}}` tokens. Real tokens are in `backend/apps/web/src/theme.css`
and `backend/apps/web/src/styles.css`. Already escalated to System Architect in
ABS-352, ABS-419, ABS-473, ABS-430, PILOT-33; no new escalation required. Same finding;
same recommendation (populate DESIGN_SYSTEM.md from CSS values per ADR-A-0017).

**No new token deviations**: all tokens used (`.feed-event-age`, `.home-ticker-age`) map to
existing `var(--muted)`, `font-size: 11px`, `white-space: nowrap` — no new design token
is introduced. No addition to DESIGN_SYSTEM.md is needed for this story.

---

## 11. Out of Scope

- Adding timestamps to Seat Drawer events (separate surface; not in PILOT-35 ACs).
- Adding timestamps to ADR/Policy list entries.
- Per-user timezone preference (ABS-470 explicitly out of scope: format is fixed, timezone
  follows the browser default).
- Per-second re-render (operator finding says 30–60 s is sufficient).
- Command-receipts (ABS-508 domain — the ACs say "sobald ABS-508 liefert"; no ABS-508
  field yet. Once ABS-508 ships with a timestamp field, the same `.feed-event-age` span
  pattern applies automatically since `EventRow` renders by `occurred_at`).

---

## 12. Design Acceptance Criteria [PILOT-35]

See §12 — the full DAC block is also posted as a `handoff` comment on PILOT-35 via the
tracker adapter.

```markdown
## Design Acceptance Criteria [PILOT-35]

**Design artifact**: docs/agent-outputs/designs/PILOT-35-design.md
**Design system**: docs/design/DESIGN_SYSTEM.md → de-facto tokens: backend/apps/web/src/theme.css + styles.css
**ABS-470 utility**: backend/apps/web/src/lib/formatTime.ts (formatAge + formatAbsolute)

### Schema Conformance
- [ ] DAC-1: Every `EventRow` in the EventFeed (Follow mode and Browse mode) renders a
  `<span data-testid="feed-event-age">` as the last child of the `<li>`. The span's
  computed `color` equals `var(--muted)` and `font-size` equals `11px`.
  Verified by inspecting a feed-item in DevTools.

- [ ] DAC-2: Every `<li data-testid="ticker-item">` in the Home Ticker renders a
  `<span data-testid="ticker-event-age">`. The span's computed `color` equals
  `var(--muted)` and `font-size` equals `11px`.

- [ ] DAC-3: The text content of `[data-testid="feed-event-age"]` and
  `[data-testid="ticker-event-age"]` matches the `formatAge()` output from
  `lib/formatTime.ts` — specifically, the format is `{N}s`, `{N}m`, `{N}h`, or `{N}d`
  with no other characters (no "ago", no colon). Examples: "4m", "3h", "2d".

- [ ] DAC-4: The `title` attribute of each age span contains the full absolute timestamp
  in the ABS-470 format: "YYYY-MM-DD HH:MM:SS" (24h, ISO date part). Example:
  `title="2026-07-25 09:15:32"`. Verified by reading the DOM attribute.

- [ ] DAC-5: The `aria-label` attribute of each age span includes BOTH the relative age
  AND the absolute timestamp, separated by " — ". Example:
  `aria-label="4m ago — 2026-07-25 09:15:32"`. Verified via accessibility inspector.

- [ ] DAC-6: The age text in `[data-testid="feed-event-age"]` updates without a page
  reload. With an event that has `occurred_at` set to ~29 minutes ago: at T=0 the
  span shows "29m"; after 60 s (one tick interval) it shows "30m". The update happens
  without a full DOM remount (the `key` of the list item is unchanged).
  Verified by waiting 31–60 s or by directly advancing `Date.now()` in a test.

- [ ] DAC-7: In Follow mode, `.feed-event-age` is a sibling of `.feed-to-follow` (both
  inside the same `.feed-item` `<li>`). The age span has `margin-left: auto` so it
  aligns to the right edge of the row at desktop widths. Verified by inspecting
  computed styles.

### Accessibility
- [ ] DAC-8: Contrast — `.feed-event-age` and `.home-ticker-age` computed color is
  `var(--muted)` against the feed background. In light theme: `#6b7280` on `#ffffff`
  → measured ≥4.5:1 via browser contrast tool. In dark theme: `#9aa4b2` on `#171b22`
  → measured ≥4.4:1 (AA for non-large text at 11px; accepted as equivalent given
  ABS-475 precedent; QAS-Design may flag if measured contrast falls below 4.5:1 and
  request a token adjustment).

- [ ] DAC-9: The age `<span>` is NOT keyboard-focusable (no `tabindex` attribute).
  The `aria-label` provides the full timestamp to screenreaders without requiring
  focus. Verified by Tab-navigating through a feed-item — the age span is skipped.

- [ ] DAC-10: A screenreader (VoiceOver or NVDA) reading a feed-item announces the
  `aria-label` value (e.g. "4m ago — 2026-07-25 09:15:32") rather than just the
  visible text ("4m"). Verified using a screenreader or accessibility inspector showing
  the computed accessible name.

- [ ] DAC-11: The relative age conveys no information by color alone — the age string
  is always the primary carrier. No color-only differentiation between fresh (0m) and
  stale (3h) events. Verified: both "0m" and "3h" entries use the same `var(--muted)`
  color; no conditional color logic is applied to the age span.

### Responsive Breakpoints
- [ ] DAC-12: At **desktop (≥1024px)**: `[data-testid="feed-event-age"]` is visible
  and right-aligned within its row. The feed item does not overflow horizontally.
  Verified at 1280px viewport width.

- [ ] DAC-13: At **mobile (<600px)**: the age span wraps below the event label (second
  line within the flex container) and is NOT cropped or clipped. The text is fully
  readable. Verified at 375px viewport width.

- [ ] DAC-14: At **all breakpoints**: `[data-testid="ticker-event-age"]` is visible
  in the Home Ticker and does not push other ticker content off-screen. Verified at
  375px (mobile) and 1280px (desktop).

### User Flows
- [ ] DAC-15: **EventFeed Follow-mode age flow**:
  1. Navigate to Mission Control (board or home view with EventFeed visible).
  2. Ensure at least one event appears in the feed list.
  3. Assert `[data-testid="feed-event-age"]` is present on each `[data-testid="feed-item"]`.
  4. Hover (or inspect `title` attribute) over the age span → full timestamp appears
     in the format "YYYY-MM-DD HH:MM:SS".
  5. Assert the age text matches `formatAge(elapsed_seconds)` for the event's
     `occurred_at` timestamp.

- [ ] DAC-16: **EventFeed Browse-mode age flow**:
  1. Switch EventFeed to Browse mode.
  2. Assert fetched events render with `[data-testid="feed-event-age"]` per item.
  3. Hover over an age span → full absolute timestamp in `title` attribute visible.
  4. Navigate to page 2 (Older →) → age stamps also present on the second page.

- [ ] DAC-17: **Home Ticker age flow**:
  1. Navigate to Home view.
  2. Assert at least one `[data-testid="ticker-item"]` is present.
  3. Assert each ticker item contains `[data-testid="ticker-event-age"]` with non-empty
     text matching the `{N}s|{N}m|{N}h|{N}d` pattern.
  4. Hover over the age span → full absolute timestamp in `title` attribute visible.

- [ ] DAC-18: **Format identical between EventFeed and Ticket display**:
  Both the Attention Queue age (`[data-testid^="attention-age-"]`) and the new
  `[data-testid="feed-event-age"]` produce the same string format for the same number
  of elapsed seconds — both call `formatAge()` from `lib/formatTime.ts`. Verified by
  inspecting an event that is approximately the same age as an attention item: the
  text format ("Nm" / "Nh" / "Nd") is identical.

- [ ] DAC-19: **No second formatAge/formatAbsolute implementation**:
  A `git grep` for "function formatAge\|function formatAbsolute" in
  `backend/apps/web/src/` returns exactly ONE definition location:
  `backend/apps/web/src/lib/formatTime.ts`. No inline equivalent appears in
  `EventFeed.tsx` or `HomeView.tsx`.
```
