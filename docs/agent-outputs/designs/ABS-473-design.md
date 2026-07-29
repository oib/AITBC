# Design: Deep Links — Routable Views and Filter State

**Ticket**: ABS-473  
**Design by**: ui-ux-design  
**Date**: 2026-07-20  
**Design system**: `docs/design/DESIGN_SYSTEM.md` (version: template — token values are `{{PLACEHOLDER}}`; see Deviation Note below)  
**Status**: DESIGN-FIX (Iteration 2) — §2.1 corrected per ADR-A-0027 + QAS-Design DAC-1 FAIL; DAC-6 impl-fix flagged for be-developer

---

## Design System Deviation Note

`docs/design/DESIGN_SYSTEM.md` contains `{{PLACEHOLDER}}` tokens without resolved values
(`{{COLOR_PRIMARY}}`, `{{FONT_FAMILY}}`, `{{SPACING_MD}}`, etc.). This design is primarily a
**URL grammar and interaction-state design**, not a visual styling design, so unresolved color
and spacing tokens do not block it. All structural rules ARE used:
- Accessibility standards (WCAG `{{WCAG_LEVEL}}` contrast ratios, focus, keyboard)
- Component names (Button/primary, Input/select) for nav and filter controls
- Responsive breakpoint structure (mobile/tablet/desktop) for link behaviour

**Reported to System Architect** (design-system token values are unresolved;
architectural sign-off on the hash grammar is required per this ticket's #PATH_DECISION).

---

## 1. Context and Problem

### Current State (ABS-420 contract)

`useDrawerURL.ts` implements the only URL-persisted UI state today:

| URL dimension | Current usage | Mechanism |
|---|---|---|
| **Search params** (`?...`) | Filter state: `epic`, `run`, `role`, `timeRange` | `replaceState` via `useFilterState.ts` |
| **Hash** (`#...`) | Drawer target only: `#/ticket/<key>` or `#/seat/<id>` | `replaceState` — back does NOT close drawer |
| **View** | In-memory React state only — NOT in URL | n/a |

Problems:
1. `#/board` does not route anywhere — `parseHash` ignores slash-less or non-`ticket`/`seat` fragments
2. Browser back never closes a drawer (replaceState pushes no history entry)
3. A pasted deep link cannot restore a specific view
4. Global filter state already serialises into search params; no gaps there

### Proposed New State (this design)

The ABS-420 hash grammar is **explicitly superseded**. The new grammar is:

```
<pathname>?<filter-params>#/<view-token>[?item=<item-target>]
```

Where:
- `?<filter-params>` — search params unchanged: `epic`, `run`, `role`, `timeRange`  
  (existing `useFilterState.ts` continues to own this layer)
- `#/<view-token>` — active view path in the hash (NEW)
- `?item=<item-target>` — drawer target as a hash-internal query param (NEW, replaces `#/ticket/...` / `#/seat/...`)

---

## 2. Hash Grammar Specification (resolved per ADR-A-0027)

> **ADR-A-0027** (2026-07-20, proposed; operator-signed; human ratification at epic merge
> per ADR-A-0004) is the binding PATH_DECISION for this grammar. Section 2 reflects the
> ADR-confirmed contract.

### 2.1 Routable View Tokens

Six routable view tokens (per ADR-A-0027 §1, Decision point 1):

| View token | Maps to `View` type in `App.tsx` | Nav button |
|---|---|---|
| `home` | `"home"` | Home |
| `board` | `"board"` | Board |
| `adrs` | `"adrs"` | ADR Register |
| `policies` | `"policies"` | Policies |
| `timeline` | `"timeline"` | Timeline |
| `usage` | `"usage"` | Usage |

> **`report` is NOT a routable view.** `#/report` is parseable by the router but is a
> **redirect alias** that immediately redirects to `#/usage` (per ADR-A-0027 §1 and ABS-469).
> The `Report` nav button navigates directly to `#/usage`; `#/report` in a pasted URL
> normalises to `#/usage` on the first navigation. There is no `"report"` `View` type in
> the 6-token grammar the ADR defines.

Default view on load with no hash: `home` (existing behaviour preserved).

### 2.2 Item Target Format

```
item-target := kind ":" identifier
kind        := "ticket" | "seat"
identifier  := percent-encoded key or ID string
```

Examples:
```
#/board?item=ticket:ABS-473         ← Board view, ticket drawer open
#/timeline?item=seat:spawn-abc-123  ← Timeline view, seat drawer open
#/adrs                              ← ADR Register, no drawer
```

Superseded ABS-420 formats:
| Old hash | New hash (same view) |
|---|---|
| `#/ticket/ABS-473` | `#/board?item=ticket:ABS-473` |
| `#/seat/spawn-123` | `#/board?item=seat:spawn-123` |

### 2.3 Full URL Examples

```
/#/home
/?epic=ABS-410#/board
/?epic=ABS-410&run=run-001#/board?item=ticket:ABS-473
/?run=run-001#/timeline
/#/usage
```

---

## 3. History API Semantics

| User action | History API call | Stack result |
|---|---|---|
| App bootstrap / auth resolves | `replaceState` with `#/<currentview>` | Replaces current entry |
| Click nav button (view change) | `pushState` with `#/<newview>` | Adds entry → back returns to previous view |
| Open drawer | `pushState` with `#/<view>?item=<target>` | Adds entry → back closes drawer |
| Close drawer (×) | `replaceState` with `#/<view>` (strips item param) | No new entry → back goes to before-open |
| Filter change | `replaceState` updating `?<filter-params>` only | No new entry (existing behaviour) |
| `popstate` event | Parse hash for view token + item target; update both `view` state and `drawer` state | Handles back/forward for both |

**Back-button scenario** (satisfying AC `"back closes drawer, second back returns to previous view"`):
```
History stack (chronological):
  [1] /#/home           ← user was on Home
  [2] /#/board          ← clicked Board (pushState)
  [3] /#/board?item=ticket:ABS-473  ← opened drawer (pushState)

Browser back from [3] → [2]: drawer closes ✓
Browser back from [2] → [1]: returns to Home ✓
```

---

## 4. Seam: useDrawerURL.ts Redesign

`backend/apps/web/src/useDrawerURL.ts` is the ONLY seam to extend — do not fork.

### 4.1 Proposed `useRoutingURL` Hook (rename/extend)

The hook must manage BOTH view state and drawer state from the hash. Suggested
signature (non-normative; implementer may adjust names, not the contract):

```typescript
/** Union of the hash-item target formats */
export type DrawerTarget =
  | { kind: "ticket"; key: string }
  | { kind: "seat"; id: string }
  | null;

/** The full parsed hash state */
export interface HashState {
  view: View;             // parsed view token, defaults to "home"
  drawer: DrawerTarget;   // null when no ?item= param
}

export function useRoutingURL(): {
  view: View;
  drawer: DrawerTarget;
  navigateTo: (view: View) => void;          // pushState: view change
  openDrawer: (target: DrawerTarget) => void; // pushState: drawer open
  closeDrawer: () => void;                    // replaceState: strip item param
}
```

### 4.2 parseHash (updated contract)

```
parseHash(hash: string) → HashState

Input:  "#/board?item=ticket:ABS-473"
Output: { view: "board", drawer: { kind: "ticket", key: "ABS-473" } }

Input:  "#/adrs"
Output: { view: "adrs", drawer: null }

Input:  "" (empty)
Output: { view: "home", drawer: null }

Input:  "#/ticket/ABS-473"   ← ABS-420 legacy format
Output: { view: "home", drawer: { kind: "ticket", key: "ABS-473" } }
         ↑ graceful fallback: restores drawer but cannot know the intended view

Input:  "#/report"            ← redirect alias (not a routable view; per ADR-A-0027 §1)
Output: redirects to { view: "usage", drawer: null }
         ↑ the router replaceStates to "#/usage" immediately; ABS-469 canonicalises this
```

Legacy format handling: on first parse of a legacy `#/ticket/<key>` or `#/seat/<id>`,
the hook restores the drawer and replaces the hash with `#/home?item=<target>` so
subsequent navigation uses the new grammar.

### 4.3 Test Contract (ABS-420 useDrawerURL tests SUPERSEDED)

The existing `useDrawerURL` tests are **NOT preserved** — they test the old contract.
New tests cover:
- `parseHash` unit tests for all format cases above (including legacy)
- Hook round-trips: `navigateTo` → `openDrawer` → back → back
- Cold navigation (pasted URL) restores view + drawer + filters

---

## 5. Filter Applicability Matrix (GlobalFilterBar)

Extends the existing `applicable()` function in `GlobalFilterBar.tsx`.

Current: only `board` is fully applicable (all four dims); all others are fully greyed.
Proposed refinement based on current data flows:

| View | `epic` | `run` | `role` | `timeRange` |
|---|---|---|---|---|
| `home` | ✗ inert | ✗ inert | ✗ inert | ✗ inert |
| `board` | ✓ active | ✓ active | ✓ active | ✓ active |
| `adrs` | ✗ inert | ✗ inert | ✗ inert | ✗ inert |
| `policies` | ✗ inert | ✗ inert | ✗ inert | ✗ inert |
| `timeline` | ✗ inert | ✓ active | ✗ inert | ✓ active |
| `usage` | ✗ inert | ✗ inert | ✗ inert | ✗ inert |

> **`report` removed**: it is a redirect alias (→ `#/usage`), not a routable view. The
> prior `report` row (run: active) is dropped. Filter applicability for the Usage view
> remains all-inert (UsageView has no global-filter wiring).

Rationale:
- `timeline`: `runOptions` + `events` flow in; time-range is meaningful for event density
- All others: no current data flow from global filters into view components

**Behaviour for inert dimensions**:
- Dimension control remains **visible** (preserves `run` in URL when switching views)
- Control is **disabled** (`disabled` attribute) with `title="<Dim> filter does not apply to this view"`
- `filter-dim-greyed` CSS class applied (already implemented in `DimSelect`)
- Active chips for inert-view dims still shown in the chip strip (value preserved)

---

## 6. Deep-Link URL Composition

A fully-qualified deep link composes all three layers:
```
<pathname>?<filter-params>#/<view>[?item=<kind>:<id>]
```

For consumers (ABS-469 /report redirect, ABS-479 notifications):
- ABS-469 `/report` redirect: the server-side `/report` URL redirects the browser to
  `/#/usage` — not `/#/report`. The router recognises `#/report` as a legacy/compat alias
  and immediately redirects to `#/usage` if ever pasted; the canonical deep link is `/#/usage`
  (or `/?run=<run-id>#/usage`).
- ABS-479 notification deep-link: `/#/board?item=ticket:<key>` (or `/#/home?item=ticket:<key>`)

---

## 7. Responsive Behaviour

Per design system breakpoints (mobile / tablet / desktop — specific values `{{BREAKPOINT_*}}`):

- **All breakpoints**: URL grammar is identical; hash routing is client-side only
- **Mobile**: Nav collapses to a compact representation (Button/secondary, design system `Button`)
  — deep links still resolve to the correct view; filter bar may wrap to additional rows
- **Tablet / Desktop**: Full horizontal nav bar; filter bar inline

No layout changes are introduced by this story beyond what views already implement.

---

## 8. Accessibility Notes

Per design system WCAG `{{WCAG_LEVEL}}` standard:
- **`aria-current="page"`**: already applied to nav buttons in `App.tsx` for the active view;
  must remain applied after the view state moves to the URL (it must read from parsed hash state,
  not from in-memory `view` state, to avoid flicker)
- **Focus management**: on view change, focus should move to the main landmark (`<main>`)
  or the view's h1; this prevents screen readers from announcing stale content
- **Drawer focus**: drawer open/close focus trap is already implemented in `TicketDrawer` /
  `SeatDrawer`; the seam change does not affect their internal focus management
- **Keyboard**: all flows completable without a pointer — nav buttons, drawer open/close,
  filter controls — unchanged requirement; the routing change must not break tab order
- **`prefers-reduced-motion`**: no animated route transitions introduced by this design;
  honour the existing `prefers-reduced-motion` declarations in `styles.css`

---

## 9. Out of Scope

- Server-side rendering (explicitly excluded in ticket)
- Saved-filter sharing backend (local names stay in `localStorage`, as today)
- Changes to `useFilterState.ts` internals — it already correctly persists filters in search params
- ABS-469 `/report` redirect implementation (composes here; implemented in ABS-469)
- ABS-479 notification deep-link wiring (composes here; implemented in ABS-479)

---

## 10. Design Acceptance Criteria

See the [DAC block posted to ticket ABS-473](#design-acceptance-criteria-block-abs-473).
