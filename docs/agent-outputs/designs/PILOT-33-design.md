# Design: PILOT-33 — Mission Control Attention-Inbox: Dismiss / Ack

**Ticket**: PILOT-33 — Mission Control: Attention-Inbox-Einträge ausblenden/dismissen (acknowledge ohne Statuswechsel)
**Design by**: ui-ux-design
**Date**: 2026-07-25
**Design system**: `docs/design/DESIGN_SYSTEM.md`
**Token source**: `backend/apps/web/src/theme.css` + `backend/apps/web/src/styles.css`
(design-system file is a starter template with `{{PLACEHOLDER}}` tokens; real resolved
values live in the CSS files, same deviation as ABS-352/ABS-419/ABS-473 — see §13)
**Parent context**: ABS-417 (Attention Inbox v2, Done), ABS-419 (Budget action, Done)

---

## 1. Design Goal

The operator currently cannot remove a known/acknowledged item from the Attention
Inbox without resolving its underlying cause. Acknowledged or consciously-ignored
entries accumulate and dilute the signal value of the queue — the inbox ceases to
mean "what needs me NOW".

This design adds:

1. **Dismiss/Ack action** on every attention item — non-destructive, auditable.
   Removes the entry from the active queue without touching the underlying issue.
2. **Dismissed-items toggle** in the inbox header — view dismissed entries; no silent
   data hole. A count keeps the operator aware of the dismissed set size.
3. **Restore action** on dismissed items — one click to return an item to the active queue.
4. **Clear re-trigger semantics**: dismiss is keyed to the specific occurrence
   `(source_ref, type, created_at)`, NOT to the rule. The same condition firing again
   creates a fresh attention item that is NOT dismissed.

**ABS-417 principles respected (unchanged):**
- Age is always visible without hover.
- One-click actions are max one dialog deep (dismiss is zero dialogs — immediate).
- All actions reuse existing audited endpoints; the dismiss endpoint is additive.
- Destructive actions require non-empty reason; dismiss is NOT destructive (no reason required).
- Agent/orchestrator sessions cannot trigger write actions (server enforces 403; UI
  renders read-only notice — same gate as existing resolve actions).

---

## 2. Design Token Mapping

De-facto token source: `backend/apps/web/src/theme.css` (same established mapping
as ABS-352/ABS-419). **Deviation reported** — see §13.

| Design token (DESIGN_SYSTEM.md) | CSS var | Light | Dark | Usage in this design |
|---|---|---|---|---|
| `color.background` | `var(--bg)` | `#f4f5f7` | `#0e1116` | Page background |
| `color.surface` | `var(--panel)` | `#ffffff` | `#171b22` | Active item card background |
| `color.surface-2` | `var(--panel-2)` | `#eceef1` | `#1f242c` | **Dismissed item card background** |
| `color.text` | `var(--text)` | `#1b1f24` | `#e6e8eb` | Active item text |
| `color.muted` | `var(--muted)` | `#5c636e` | `#9aa4b2` | Dismissed item text, dismiss button default |
| `color.primary` | `var(--accent)` | `#1d4ed8` | `#60a5fa` | Links, type-gate left border |
| `color.error` | `var(--stale)` | `#b91c1c` | `#f87171` | Dismiss button hover, type-blocker, needs-human dismiss border |
| `color.warning-bg` | `var(--emphasis)` | `#fef3c7` | `#3b2f0b` | needs-human item background |
| `color.warning` | `var(--emphasis-border)` | `#f59e0b` | `#b7791f` | type-escalation/budget left border |
| `color.border` | `var(--border)` | `#d6dae0` | `#2b313a` | Item border, **dismissed item left border (override)** |

**Components used** (design system § Components):
- **Button/secondary** → `.linkbtn` class (existing base) — dismiss, restore, and ▼ Resolve toggles
- **Card/default** → `.attention-item` (existing) — item rows; dismissed variant uses `var(--panel-2)` bg
- **Input/checkbox** → dismissed-toggle checkbox in inbox header

---

## 3. Dismiss/Ack Semantics

### 3.1 What dismiss means

| Property | Value |
|---|---|
| Visibility | Item is removed from the active queue view |
| Underlying data | **Unchanged** — the attention item record, its events, and the ticket/seat/command state are NOT deleted |
| Audit trail | Backend stores `(project, source_ref, type, created_at, dismissed_at, dismissed_by_session)` in a `attention_dismissals` table |
| Restorability | One-click Restore returns the item to the active queue (deletes the dismissal record) |
| Scope | Dismiss is per-entry — keyed by `(source_ref, type, created_at)` |

### 3.2 Re-trigger semantics

Dismiss binds to a **specific occurrence** (identified by `created_at`), not to the
underlying condition (rule/source). When the same source+type condition fires again,
the backend creates a new attention item with a new `created_at`. The new item is NOT
dismissed and appears in the active queue. The previously dismissed entry (different
`created_at`) remains in the dismissed set.

```
Example:
  09:00 — stalled-seat item for spawn-abc123 emitted (created_at: T1)
  09:05 — operator dismisses item (dismissal record: source_ref=spawn-abc123, type=stalled-seat, created_at=T1)
  09:10 — spawn stalls again, new item emitted (created_at: T2)
  → Active queue shows the T2 item (NOT dismissed)
  → Dismissed toggle shows the T1 item (dismissed)
```

### 3.3 Who can dismiss

Dismiss is a write action (it mutates backend state). It is gated on `isWriter`
(role `admin` or `maintainer`), consistent with ABS-417 AC5. Agent/orchestrator
sessions see the same read-only notice as for other write actions; the server
enforces 403 on the dismiss endpoint.

**Rationale**: Unlike the budget "→ View Usage" action (read-only navigation, ABS-419),
dismiss mutates the attention queue on the server — it must respect the same write
boundary.

---

## 4. Component Anatomy

### 4.1 AttentionRow — active item (modified)

Existing row with dismiss button added. The "▼ Resolve" toggle and the new
"✕ Dismiss" button are siblings inside a new `.attention-actions` row:

```
li.attention-item.{type-css-class}[.needs-human]
  [data-testid="attention-{source_ref}"]

  .attention-top                        ← UNCHANGED
    span.attention-icon
    span.badge.attention-type
    {source link or span}
    span.attention-age[.attention-age-urgent]

  div.attention-hint                    ← UNCHANGED

  .attention-actions                    ← NEW wrapper (replaces bare ▼ Resolve button)
    button.linkbtn.attention-action-toggle
      [aria-expanded={expanded}]
      [data-testid="attention-action-btn-{source_ref}"]
      "▼ Resolve" / "▲ Close"

    [if isWriter]
    button.linkbtn.attention-dismiss-btn
      [data-testid="attention-dismiss-{source_ref}"]
      [aria-label="Dismiss this {type} item for {source_ref}"]
      [disabled={dismissBusy}]
      "✕ Dismiss"                       ← immediate, no confirm dialog

    [if dismissErr]
    span.err[role="alert"]
      [data-testid="attention-dismiss-err-{source_ref}"]
      "Dismiss failed ({status})"

  [if expanded]
  ActionPanel                           ← UNCHANGED
```

**Dismiss behaviour**: clicking "✕ Dismiss" calls `POST /attention/dismiss` with
`{ source_ref, type, created_at }`. On success, `onChanged()` is called and the
item disappears from the active list. On 403, the standard error message is shown.
No confirmation dialog — dismiss is reversible (Restore is available in the
dismissed view).

### 4.2 AttentionRow — dismissed item (new variant)

Dismissed items appear in a separate section below the active queue (only when
`showDismissed` is true). They have reduced visual weight and a Restore action:

```
li.attention-item.dismissed.{type-css-class}
  [data-testid="attention-dismissed-{source_ref}"]
  [aria-label="Dismissed: {type} for {source_ref}"]

  .attention-top
    span.attention-icon  [aria-hidden="true"]
    span.badge.attention-type  (muted)
    {source label — same as active, but non-interactive if ticket}
    span.attention-age  (muted)
    span.badge.dismissed-badge  "✓ ack"    ← new: signals dismissed status non-color

  div.attention-hint  (muted)

  div.attention-dismissed-meta
    "Dismissed {relative time}"            ← e.g. "Dismissed 5m ago"
    [data-testid="attention-dismissed-at-{source_ref}"]

  [if isWriter]
  button.linkbtn.attention-restore-btn
    [data-testid="attention-restore-{source_ref}"]
    [aria-label="Restore {type} item for {source_ref} to active queue"]
    [disabled={restoreBusy}]
    "↩ Restore"
```

**Note**: The dismissed item's source link does NOT open the ticket drawer (it is a
passive view — dismiss view is read-only for orientation, not action).

### 4.3 Inbox header — dismissed toggle (new)

```
.inbox-head                           ← existing flex row
  h2.column-head "Attention {activeCount}"
  [if items.length > 0]
  button.linkbtn.inbox-jump
    [data-testid="inbox-jump-oldest"]
    "↓ oldest"

  label.inbox-dismissed-toggle        ← NEW
    input[type="checkbox"]
      [data-testid="inbox-dismissed-toggle"]
      [checked={showDismissed}]
      [aria-label="Show dismissed items ({dismissedCount})"]
    " Dismissed ({dismissedCount})"
```

**Toggle behaviour**:
- When unchecked (default): only active items shown; `getAttention(project)` normal call.
- When checked: active queue + dismissed section below; switches to
  `getAttentionWithDismissed(project)` which returns all items (active + dismissed
  with `dismissed: true` flag). Dismissed section is rendered with a divider heading.
- The `dismissedCount` shown in the label comes from the last `getAttentionWithDismissed`
  result (or is hidden/0 when never fetched in the session). On first toggle-on, count
  resolves once the extended query returns.

### 4.4 Inbox — dismissed section heading

Between the active queue and the dismissed section (only when `showDismissed` is true
and `dismissedCount > 0`):

```
h3.inbox-dismissed-head "Dismissed ({dismissedCount})"
  [data-testid="inbox-dismissed-section"]
```

If `dismissedCount === 0` and `showDismissed` is true:
```
div.inbox-dismissed-empty [data-testid="inbox-dismissed-empty"]
  p.muted "No dismissed items."
```

---

## 5. Data Flow

### 5.1 API additions

**New endpoint — dismiss:**
```
POST /api/v1/projects/:project/attention/dismiss
Body: {
  source_ref: string,
  type: string,        // AttentionItemType value
  created_at: string   // ISO 8601 — exact value from the AttentionItem
}
Response 200: { ok: true }
Response 403: { error: "forbidden" }   ← agent/orchestrator sessions
```

**New endpoint — restore (un-dismiss):**
```
DELETE /api/v1/projects/:project/attention/dismiss
Body: {
  source_ref: string,
  type: string,
  created_at: string
}
Response 200: { ok: true }
Response 403: { error: "forbidden" }
Response 404: { error: "not dismissed" }   ← no dismissal record found
```

**Extended GET /attention:**
```
GET /api/v1/projects/:project/attention?include_dismissed=true
→ AttentionPayload where items includes dismissed entries (dismissed: true).
  Dismissed items carry dismissed_at: string (ISO 8601).
  Without the query param: existing behaviour unchanged (ADDITIVE-ONLY, AC4 ABS-411).
```

### 5.2 Type additions (types.ts — ADDITIVE)

```typescript
// ---- PILOT-33: Dismiss/Ack additions ----

/** Extended AttentionItem with optional dismiss fields.
 * Older backends that do not support PILOT-33 will omit these fields;
 * clients treat absent fields as dismissed: false (ADDITIVE-ONLY, AC4 ABS-411). */
export interface AttentionItem {
  // ... all existing fields unchanged ...

  /**
   * True when the operator has acknowledged and dismissed this item.
   * Only present when GET /attention?include_dismissed=true is used.
   * Absent (undefined) is equivalent to false.
   */
  dismissed?: boolean;

  /**
   * ISO 8601 UTC timestamp when this item was dismissed.
   * Only present when dismissed === true.
   */
  dismissed_at?: string;
}
```

### 5.3 api.ts additions

```typescript
// ---- PILOT-33: Dismiss/Ack ----

/** Dismiss an attention item (acknowledge without resolving). Human-session gated (403 for agents). */
export function dismissAttention(
  project: string,
  item: { source_ref: string; type: string; created_at: string }
): Promise<WriteResult> {
  return postJSON(
    `/api/v1/projects/${encodeURIComponent(project)}/attention/dismiss`,
    item
  );
}

/** Restore a dismissed attention item back to the active queue. Human-session gated (403 for agents). */
export function restoreAttention(
  project: string,
  item: { source_ref: string; type: string; created_at: string }
): Promise<WriteResult> {
  return deleteJSON(
    `/api/v1/projects/${encodeURIComponent(project)}/attention/dismiss`,
    item
  );
}

/** Fetch attention items including dismissed ones (PILOT-33 toggle view). */
export async function getAttentionWithDismissed(project: string): Promise<AttentionPayload> {
  return getJSON(
    `/api/v1/projects/${encodeURIComponent(project)}/attention?include_dismissed=true`
  );
}
```

### 5.4 Inbox component state additions

New local state in the `Inbox` component:
```typescript
const [showDismissed, setShowDismissed] = useState(false);
```

When `showDismissed` is false: existing `getAttention` call unchanged.
When `showDismissed` switches to true: one-time fetch via `getAttentionWithDismissed`
(or the parent re-fetches via the extended endpoint and passes the full payload).

**Simplest implementation**: add an `onToggleDismissed` callback prop or move the
fetch call inside `Inbox` using a secondary fetch. Either approach is acceptable;
implementer chooses the cleanest seam.

The active items remain `items.filter(i => !i.dismissed)` (reversed newest-first as today).
The dismissed items are `items.filter(i => i.dismissed)` (rendered oldest-dismissed-first
for the dismissed section, i.e. NOT reversed — the last dismissed is most recent context).

---

## 6. Inbox States Reference

| Condition | Active queue | Dismissed section | Toggle label |
|---|---|---|---|
| 0 active, 0 dismissed | "Nothing needs you." | hidden | "Dismissed (0)" hidden |
| N active, 0 dismissed | N items | hidden when toggled on: "No dismissed items." | "Dismissed (0)" |
| N active, M dismissed | N items | hidden by default; M items when toggled | "Dismissed (M)" |
| 0 active, M dismissed | "Nothing needs you." | M items when toggled | "Dismissed (M)" |
| dismiss in progress | item visible, dismiss btn disabled + spinner | — | — |
| 403 on dismiss | error span `role="alert"` on item | — | dismiss btn hidden (read-only notice) |
| restore in progress | — | item visible, restore btn disabled | — |

---

## 7. Responsive Behaviour

Breakpoints (from styles.css authoritative comment: sm=600px, md=768px, lg=1024px):

| Breakpoint | Inbox width | Dismiss / Restore buttons |
|---|---|---|
| `desktop` (≥1024px) | 300px (fixed, existing) | `.attention-actions` flex row: Resolve + Dismiss side by side |
| `tablet` (768–1023px) | Full width (existing mobile stack from ABS-465) | `.attention-actions` wraps: Resolve and Dismiss stack vertically |
| `mobile` (<768px) | Full width | Same as tablet — buttons stack vertically, full readable width |

The `.attention-actions` wrapper uses `flex-wrap: wrap` so the buttons wrap naturally
at narrow widths without explicit breakpoint rules.

---

## 8. Accessibility Specification

Per design system WCAG 2.1 AA (existing standard, carried from ABS-417/ABS-419).

**Dismiss button:**
- `aria-label="Dismiss this {type} item for {source_ref}"` — descriptive, not "Dismiss" alone.
- `disabled` when dismiss is in progress (`dismissBusy`).
- Error: `role="alert"` on the error span so the screen reader announces the failure.
- Color: `var(--muted)` default → `var(--stale)` on hover. Both pass contrast ≥3:1 for
  interactive element borders; the button text "✕ Dismiss" is not color-only (text label present).

**Dismissed item card:**
- `aria-label="Dismissed: {type} for {source_ref}"` on the `<li>` element.
- `.dismissed-badge` badge text "✓ ack" is a non-color, non-emoji signifier.
- All text on `var(--panel-2)` background: `var(--muted)` `#5c636e` on `#eceef1` → confirmed AA-compliant (ABS-475 established `--muted` meets ≥4.5:1 on `--panel-2`).
- Dismissed items do NOT open the ticket drawer on source-ref click — a passive view.
  Source label is a `<span>`, not a `<button>`, to prevent accidental navigation.

**Restore button:**
- `aria-label="Restore {type} item for {source_ref} to active queue"` — descriptive.
- `disabled` when restore is in progress.

**Dismissed toggle:**
- `<label>` wraps the `<input type="checkbox">` — native label association.
- `aria-label` on the checkbox: `"Show dismissed items ({N})"` — the count in the label
  keeps the operator informed without opening the view.
- Toggle state change triggers re-fetch; any loading state can be indicated via
  `aria-busy="true"` on the dismissed section heading.

**Focus order addition** (extends ABS-417 order):
```
Active items newest → oldest:
  [for each item] type-icon (sr-only label) → source ref → age → ▼ Resolve → ✕ Dismiss

Inbox header:
  h2 "Attention N" → [if items] ↓ oldest → Dismissed ({N}) checkbox

Dismissed section (when shown):
  h3 "Dismissed ({M})" → [for each dismissed item] source-span → age → dismissed-meta → ↩ Restore
```

**Keyboard**:
- "✕ Dismiss" reachable by Tab and activatable by Space/Enter.
- "↩ Restore" reachable by Tab and activatable by Space/Enter.
- Dismissed-toggle checkbox operable by Space.
- No new dialog — dismiss is immediate. This is intentional (the Restore path provides undo;
  no confirmation dialog is less interaction overhead for a non-destructive action).

**Contrast calculations** (light mode; dark mode symmetric via ABS-475 darkened tokens):
- `var(--muted)` `#5c636e` on `var(--panel-2)` `#eceef1` → ≥4.5:1 ✓ (ABS-475)
- `var(--muted)` `#5c636e` on `var(--panel)` `#ffffff` → ~8.6:1 ✓ (dismiss btn default)
- `var(--stale)` `#b91c1c` on `var(--panel)` `#ffffff` → ~5.9:1 ✓ (dismiss btn hover)
- `var(--text)` `#1b1f24` on `var(--panel-2)` `#eceef1` → ≥11:1 ✓ (dismissed item main text if needed)

---

## 9. CSS Additions (scope for FE developer)

```css
/* ---- PILOT-33: Dismiss/Ack ---- */

/* Action row — wraps "▼ Resolve" and "✕ Dismiss" side by side */
.attention-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

/* Dismiss button — low-weight, non-destructive affordance */
.attention-dismiss-btn {
  color: var(--muted);
  font-size: 11px;
  margin: 0;
  transition: color .15s;
}
.attention-dismiss-btn:hover:not(:disabled) {
  color: var(--stale);
}
.attention-dismiss-btn:disabled {
  opacity: .6;
  cursor: default;
}

/* Dismissed item card — reduced visual weight; left border deemphasized */
.attention-item.dismissed {
  background: var(--panel-2);
  border-left-color: var(--border);   /* override type-specific accent */
  opacity: 1;                          /* NOT opacity-reduced: text must stay AA-compliant */
}

/* All text on dismissed cards uses muted for de-emphasis */
.attention-item.dismissed .attention-type,
.attention-item.dismissed .attention-source,
.attention-item.dismissed .attention-age,
.attention-item.dismissed .attention-hint {
  color: var(--muted);
}

/* Dismissed badge — "✓ ack" indicator; non-color signifier */
.dismissed-badge {
  font-size: 10px;
  padding: 1px 5px;
  background: var(--panel-2);
  border: 1px solid var(--border);
  border-radius: 10px;
  color: var(--muted);
  white-space: nowrap;
}

/* Dismissed timestamp meta line */
.attention-dismissed-meta {
  font-size: 11px;
  color: var(--muted);
}

/* Restore button */
.attention-restore-btn {
  color: var(--accent);
  font-size: 11px;
  margin: 0;
}
.attention-restore-btn:hover:not(:disabled) {
  text-decoration: underline;
}

/* Dismissed toggle — compact checkbox in inbox header */
.inbox-dismissed-toggle {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  color: var(--muted);
  cursor: pointer;
  margin-left: 4px;
  white-space: nowrap;
}
.inbox-dismissed-toggle input[type="checkbox"] {
  cursor: pointer;
  accent-color: var(--accent);
}

/* Dismissed section heading */
.inbox-dismissed-head {
  font-size: 11px;
  font-weight: 600;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: .04em;
  margin: 8px 0 4px;
  padding-top: 8px;
  border-top: 1px solid var(--border);
}

.inbox-dismissed-empty {
  font-size: 12px;
  color: var(--muted);
  padding: 4px 0;
}
```

---

## 10. New Files / Modifications for Implementer

| File | Change |
|---|---|
| `backend/apps/web/src/types.ts` | Add optional `dismissed?: boolean` and `dismissed_at?: string` to `AttentionItem` (ADDITIVE) |
| `backend/apps/web/src/api.ts` | Add `dismissAttention`, `restoreAttention`, `getAttentionWithDismissed` functions; add `deleteJSON` helper if not present |
| `backend/apps/web/src/components/Inbox.tsx` | (1) Wrap `attention-action-toggle` and new `attention-dismiss-btn` in `.attention-actions` div in `AttentionRow`; (2) Add dismiss logic and `dismissBusy/dismissErr` state to `AttentionRow`; (3) Add dismissed-item rendering (`DismissedRow` sub-component); (4) Add `showDismissed` state + toggle checkbox to `Inbox` header; (5) Add dismissed section below the active list |
| `backend/apps/web/src/styles.css` | Append PILOT-33 Dismiss/Ack CSS block (§9) |
| `backend/` (server side) | New `attention_dismissals` table + `POST /attention/dismiss` + `DELETE /attention/dismiss` endpoints + `?include_dismissed=true` support on `GET /attention` — required backend for the FE to function; implementer should confirm backend scope or file a separate backend story if out of scope |

**Backend scope note**: the FE implementer should confirm with the system architect
whether the backend endpoints (dismiss table + API) are in scope for PILOT-33 or
require a separate ticket. The design contracts both. If backend is a separate story,
the FE can be implemented with a local `dismissedRefs` Set in React state (client-side
only, non-persistent) as an interim stub, and the e2e DACs that require server
persistence would be deferred.

---

## 11. Design System Deviation Report

**Deviation 1** (Critical — pre-existing, ongoing): `docs/design/DESIGN_SYSTEM.md`
contains only `{{PLACEHOLDER}}` tokens. Real tokens are in `backend/apps/web/src/theme.css`
and `backend/apps/web/src/styles.css`. Already escalated to System Architect in
ABS-352, ABS-419, ABS-473; no new escalation required. Same finding; same recommendation
(populate DESIGN_SYSTEM.md from CSS values per ADR-A-0017).

**Deviation 2** (Minor, new): No dedicated `color.dismissed` or `color.ack` token
exists in the design system for the "dismissed" state. This design uses
`var(--panel-2)` background + `var(--muted)` text + `var(--border)` left border as
the dismissed item palette — all existing tokens used conservatively. **No new token
proposed** (the existing panel-2/muted/border trio is sufficient). If the team wants
a formal `color.dismissed-bg` token, it maps to `var(--panel-2)` and should be
added to DESIGN_SYSTEM.md and theme.css.

---

## 12. Out of Scope

- Hard-delete of dismissed items from the backend (ticket: "kein Hard-Delete der
  zugrundeliegenden Events" — auditability requirement).
- Bulk dismiss ("dismiss all") — could be added later; out of scope for PILOT-33.
- Push notifications for re-triggered items (ABS-500 domain).
- The ABS-495 source-suppression work (machine wait-states not entering the inbox) —
  complementary, not a dependency; this design handles manual ack of any item type.

---

## 13. Design Acceptance Criteria (DACs)

See handoff comment for the full DAC block posted to PILOT-33.

```markdown
## Design Acceptance Criteria [PILOT-33]

**Design artifact**: docs/agent-outputs/designs/PILOT-33-design.md
**Design system**: docs/design/DESIGN_SYSTEM.md → de-facto tokens: backend/apps/web/src/theme.css + styles.css

### Schema Conformance
- [ ] DAC-1: The "✕ Dismiss" button uses `.linkbtn` + `.attention-dismiss-btn` classes.
  Default color is `var(--muted)`; hover color is `var(--stale)`. No new color token is
  introduced. The button renders ONLY when `isWriter` is true (role admin or maintainer).

- [ ] DAC-2: Dismissed item cards use `background: var(--panel-2)` and
  `border-left-color: var(--border)` (overriding the type-specific accent — confirmed by
  inspecting the DOM: dismissed `.attention-item.dismissed` does NOT retain a type-specific
  border-left color).

- [ ] DAC-3: The "✓ ack" badge in dismissed item rows uses the `.dismissed-badge` class
  with `background: var(--panel-2)`, `border: 1px solid var(--border)`, and
  `color: var(--muted)`. Text "✓ ack" is present (not icon-only).

- [ ] DAC-4: The `.attention-actions` wrapper renders both "▼ Resolve" and "✕ Dismiss"
  as sibling `<button>` elements in the same flex container. The existing
  `attention-action-toggle` class is retained on the Resolve button.

### Accessibility
- [ ] DAC-5: The dismiss button `aria-label` includes the item type and source_ref:
  e.g. `"Dismiss this stalled-seat item for spawn-abc123"`. Not bare "Dismiss".

- [ ] DAC-6: The restore button `aria-label` includes the item type and source_ref:
  e.g. `"Restore stalled-seat item for spawn-abc123 to active queue"`. Not bare "Restore".

- [ ] DAC-7: The dismissed-toggle `<input type="checkbox">` is wrapped in a `<label>`
  element (native association). The checkbox `aria-label` reads
  `"Show dismissed items ({N})"` where N is the current dismissed count.

- [ ] DAC-8: Contrast (light mode):
  - `var(--muted)` `#5c636e` on `var(--panel-2)` `#eceef1`: dismiss btn default,
    dismissed item text — measured ≥4.5:1 (AA body text).
  - `var(--stale)` `#b91c1c` on `var(--panel)` `#ffffff`: dismiss btn hover —
    measured ≥4.5:1.
  - `var(--accent)` on `var(--panel-2)`: restore btn — measured ≥4.5:1.
  All three verified in dark theme equivalents.

- [ ] DAC-9: Non-writer sessions (role not admin/maintainer): the "✕ Dismiss" button
  is NOT rendered. The read-only notice already present for other action types is
  sufficient (no additional read-only messaging needed for dismiss specifically —
  the button simply does not appear).

### Responsive
- [ ] DAC-10: At viewport ≥1024px (desktop), "▼ Resolve" and "✕ Dismiss" are on the
  same horizontal row inside `.attention-actions`.

- [ ] DAC-11: At viewport <768px (mobile), `.attention-actions` wraps so "▼ Resolve"
  and "✕ Dismiss" stack vertically. Neither button is cropped or horizontally clipped.

### User Flows
- [ ] DAC-12: **Active-dismiss e2e flow**: given an active attention item in the queue,
  a writer session clicks "✕ Dismiss" → the item is removed from the active list
  (no longer visible in the active queue without toggling "Dismissed") → the
  `POST /attention/dismiss` call returns `{ ok: true }`. Steps:
  1. Load Inbox; verify item present with `data-testid="attention-{source_ref}"`.
  2. Click `data-testid="attention-dismiss-{source_ref}"`.
  3. Assert item with `data-testid="attention-{source_ref}"` is no longer in the DOM.
  4. Assert active count in `data-testid="inbox-count"` decreased by 1.

- [ ] DAC-13: **Dismissed-toggle e2e flow**: after dismissing an item,
  toggle `data-testid="inbox-dismissed-toggle"` to ON →
  a dismissed section appears (`data-testid="inbox-dismissed-section"`) →
  the dismissed item appears with `data-testid="attention-dismissed-{source_ref}"` →
  the "✓ ack" badge is present on that item.

- [ ] DAC-14: **Restore e2e flow**: with the dismissed section visible,
  a writer session clicks `data-testid="attention-restore-{source_ref}"` on a
  dismissed item → the item returns to the active queue
  (appears again in the active list with `data-testid="attention-{source_ref}"`) →
  the dismissed section count decreases by 1.

- [ ] DAC-15: **Re-trigger semantics**: two attention items with the SAME `source_ref`
  and `type` but DIFFERENT `created_at` values are in the payload. The operator
  dismisses the older one (T1). The newer one (T2) remains in the active queue.
  Toggling "Show dismissed" shows only the T1 item in the dismissed section; T2
  is NOT shown there. (This verifies dismiss is keyed by `created_at`, not by
  source+type alone.)

- [ ] DAC-16: **Non-writer session**: load Inbox with a role that is NOT admin or
  maintainer. Verify: no "✕ Dismiss" button appears on any attention item
  (`data-testid="attention-dismiss-{source_ref}"` absent from DOM).

- [ ] DAC-17: **403 error path**: if `POST /attention/dismiss` returns 403, an
  error span with `role="alert"` and `data-testid="attention-dismiss-err-{source_ref}"`
  appears on the item. The item remains in the active queue (not removed).
```
