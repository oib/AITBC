# Design: ABS-419 — S7 Usage & Budget Meter UI

**Ticket**: ABS-419 — KPI Budget Bar, Per-Run/Epic Breakdown, Burn Rate
**Design system**: `docs/design/DESIGN_SYSTEM.md`
**Design system note**: The file at `docs/design/DESIGN_SYSTEM.md` contains placeholder tokens.
Real design tokens live in `backend/apps/web/src/styles.css` as CSS custom properties.
This design maps all token names to those CSS variables. **Deviation reported to System Architect
(same finding as ABS-352): `DESIGN_SYSTEM.md` must be populated from `styles.css` values to serve
as the authoritative single source of truth (ADR-A-0017).**
**Date**: 2026-07-18
**Author**: ui-ux-design
**Parent epic**: ABS-410 (design principles 1, 2, 4 binding)
**Depends on (implemented)**: ABS-414 (S6 API, Done), ABS-416 (S2 Home KPI strip, Done)

---

## 1. Design Goal

The operator sees spend without leaving the dashboard:

- **Home KPI strip**: the S2 placeholder `home-kpi-budget` chip becomes a real budget bar
  showing current run/epic spend vs. budget plus burn rate ($/h). Three threshold states,
  colored by the existing 5-state palette. Tooltip shows token detail.
- **Usage view**: a new `UsageView` panel reachable via the budget chip (drill-down) and a
  nav tab; shows per-run/epic/seat/day breakdown tables from the S6 aggregation API.
- **Incomplete-cost badge**: when any row has `incomplete: true`, the total is flagged — never
  silently wrong.
- **Budget config UI**: inline in the Usage view header; human-gated write to S6 `PUT /budget`;
  403 error path rendered for non-human sessions.
- **Budget attention items**: `budget`-type items (already recognized by Inbox.tsx with icon 💸
  and CSS class `type-budget`) get a "→ Usage" link action that navigates to the Usage view.

**Design principles respected (ABS-410 §Design Principles):**

| Principle | How this design satisfies it |
|---|---|
| 1 — Overview first | Budget chip on Home is glanceable (one number + bar); no scroll required |
| 2 — Status rollup | Uses only the existing 5-color palette; no new colors |
| 4 — Details on demand | Usage view is a drill-down; KPI chip stays minimal |

---

## 2. Design Token Mapping

De-facto token source: `backend/apps/web/src/styles.css` (same mapping as ABS-352/ABS-348).

| Design token | CSS var | Light | Dark | Usage in this design |
|---|---|---|---|---|
| `color.background` | `var(--bg)` | `#f4f5f7` | `#0e1116` | Page bg |
| `color.surface` | `var(--panel)` | `#ffffff` | `#171b22` | Card/panel bg |
| `color.surface-2` | `var(--panel-2)` | `#eceef1` | `#1f242c` | KPI chip bg, table row alt |
| `color.text` | `var(--text)` | `#1b1f24` | `#e6e8eb` | Body text, chip labels |
| `color.muted` | `var(--muted)` | `#6b7280` | `#9aa4b2` | Burn rate label, sublabels |
| `color.primary` | `var(--accent)` | `#2563eb` | `#60a5fa` | Budget bar fill (normal state), links |
| `color.success` | `var(--live)` | `#16a34a` | `#4ade80` | (not used for budget, avoids confusion) |
| `color.warning` | `var(--emphasis-border)` | `#f59e0b` | `#b7791f` | Budget bar + chip accent (warning state) |
| `color.warning-bg` | `var(--emphasis)` | `#fef3c7` | `#3b2f0b` | Warning chip background tint |
| `color.error` | `var(--stale)` | `#b91c1c` | `#f87171` | Budget bar + chip accent (exceeded state) |
| `color.border` | `var(--border)` | `#d6dae0` | `#2b313a` | Dividers, chip borders |
| `font.size.sm` | `11px` | — | — | Burn rate label, token tooltip |
| `font.size.md` | `14px` | — | — | Table body |
| `font.size.lg` | `18px` | — | — | KPI chip spend value |
| `spacing.xs` | `4px` | — | — | Inline chip gaps |
| `spacing.sm` | `8px` | — | — | Chip padding, row padding |
| `spacing.md` | `12px` | — | — | Panel padding |
| `spacing.lg` | `16px` | — | — | View padding |

**Components used** (design system § Components):
- **Card/default** → `.home-kpi-chip` pattern (existing, extended for budget)
- **Button/primary** → `<button>` for budget edit submit (existing `button` base style)
- **Input/text** → budget config form fields (existing `input` base style)
- **Table/default** → Usage breakdown table (existing `.fm` / structured layout)
- **Badge** → `.badge` for incomplete-cost indicator (existing pattern)

---

## 3. Budget States

The three states map to existing 5-state palette colors only — no new color introduced.

| State | Trigger | Bar fill color | Chip border/accent | Chip background |
|---|---|---|---|---|
| Normal | spend < warning_pct % of budget | `var(--accent)` | `var(--border)` default | `var(--panel-2)` |
| Warning | spend ≥ warning_pct %, < 100 % | `var(--emphasis-border)` | `var(--emphasis-border)` | `var(--emphasis)` |
| Exceeded | spend ≥ 100 % | `var(--stale)` | `var(--stale)` | light: `#fff0f0` / dark: `#2c1010` |

When no budget is configured (`budget_usd: null`): chip shows spend only (`$2.64`) with
"no limit" in `var(--muted)` — no bar rendered, chip is non-interactive placeholder.

---

## 4. Component Anatomy

### 4.1 Home KPI Budget Chip (replaces placeholder)

The existing placeholder chip:
```html
<span class="home-kpi-chip home-kpi-budget" data-testid="kpi-budget">
  <span class="home-kpi-value home-kpi-budget-ph">—</span>
  <span class="home-kpi-label">budget</span>
</span>
```

Replaced by a `<button>` that navigates to the Usage view (`onNavigate("usage")`):

```
button.home-kpi-chip.home-kpi-budget[.budget-warning|.budget-exceeded]
  [aria-label="$2.64 of $10.00 budget (26%); burn rate $0.22/h — go to usage"]
  [data-testid="kpi-budget"]
  [title="576k tokens in · 96k tokens out"]     ← tooltip

  .home-kpi-budget-top
    span.home-kpi-value "$2.64"                 ← color: var(--text) in ALL states (normal/warning/exceeded)
                                               ← only the bar fill and chip border use the state accent
    span.home-kpi-budget-limit " / $10"         ← color: var(--muted)

  .home-kpi-budget-bar                          ← thin progress bar, 4px tall
    .home-kpi-budget-bar-fill                   ← width: 26%; background: state accent

  span.home-kpi-label "0.22 $/h · budget"      ← dual label: burn rate + "budget"
```

**No-budget state** (budget_usd = null):
```
span.home-kpi-chip.home-kpi-budget[non-interactive]
  span.home-kpi-value "$2.64"
  span.home-kpi-label "spend · no limit"
```

**No-data state** (never fetched / loading):
```
span.home-kpi-chip.home-kpi-budget
  span.home-kpi-value.home-kpi-budget-ph "—"
  span.home-kpi-label "budget"
```

**Data source**: `GET /usage?group=run` (most-recent run row) + `GET /usage/burn-rate` +
`GET /budget` (project-scope default, run override preferred). Fetched by a new `useBudget(project)`
hook; polled every 60s or on SSE `budget-*` events.

---

### 4.2 Usage View (`<UsageView>`)

Reachable via:
- Budget chip click → `onNavigate("usage")`
- Nav tab "Usage" added to App.tsx view switcher

```
.usage-view
  .usage-header
    h2 "Usage"
    .usage-group-switcher
      button[aria-pressed] "Run"
      button[aria-pressed] "Epic"
      button[aria-pressed] "Seat"
      button[aria-pressed] "Day"
    [if role >= maintainer]
      button.usage-budget-edit-toggle "⚙ Budget"  ← toggles budget config panel

  [if budgetEditOpen && role >= maintainer]
  .usage-budget-config                             ← collapsible inline panel
    [see §4.3]

  [if anyRowIncomplete]
  .usage-incomplete-notice[role="status"]
    span.badge.badge-incomplete "⚠ incomplete cost"
    " — one or more rows contain unknown models; $ totals are a floor, not exact."

  .usage-table
    table[aria-label="Usage by {group}"]
      thead
        tr
          th "Key"                 ← run_id / epic / seat / YYYY-MM-DD
          th "Spawns"
          th "Tokens in"
          th "Tokens out"
          th "Cost"                ← $ with ⚠ if row.incomplete
          [if group=run] th "Budget"
      tbody
        tr × N   [see §4.2.1]
      tfoot
        tr.usage-total
          td "Total"
          td {sum spawns}
          td {sum tokens_in}
          td {sum tokens_out}
          td {sum cost_usd}
            [if anyRowIncomplete] span.badge.badge-incomplete "⚠"
          [if group=run] td "—"
```

#### 4.2.1 Table Row Anatomy

```
tr[data-incomplete="true|false"]
  td.usage-key        "run-2026-07-18"  [link to drawer if group=run/epic]
  td.usage-spawns     "12"
  td.usage-tokens-in  "480k"           ← formatted: k / M suffix
  td.usage-tokens-out "96k"
  td.usage-cost
    "$2.64"
    [if row.incomplete]
      span.badge.badge-incomplete title="Unknown model(s) — cost is a floor" "⚠"
  [if group=run]
  td.usage-budget
    [if budget set]   "$10.00 · 26% · normal|⚠ warning|🔴 exceeded"
    [else]            span.muted "—"
```

Token formatting helper: `< 1000 → exact; ≥ 1000 → "{n}k"; ≥ 1 000 000 → "{n}M"`.

---

### 4.3 Budget Config Panel (inline, human-gated)

Visible only when `role ∈ {admin, maintainer}` AND user toggles "⚙ Budget".

```
.usage-budget-config[aria-label="Budget configuration"]
  form.budget-form
    fieldset
      legend "Budget (project default)"

      label[for="budget-usd"] "Budget USD"
      input#budget-usd[type="number" min="0" step="0.01" placeholder="e.g. 50"]

      label[for="warning-pct"] "Warning threshold %"
      input#warning-pct[type="number" min="1" max="100" placeholder="80"]

      button[type="submit" disabled={busy}] "Save"

      [if saveError]
      span.err[role="alert"] "Failed to save: {error message}"

      [if saveOk]
      span[role="status"] "Saved ✓"

  [if role NOT in {admin, maintainer}]
  p.muted[role="status"] "Budget editing requires maintainer or admin role."
```

**403 path** (agent token / non-human session): the form is not rendered at all.
Instead, a single `p.err[role="alert"]` reads: "Budget config is not available for
this session (human login required)."

**API**: `PUT /api/v1/projects/:project/budget` with body
`{ scope: "project", budget_usd, warning_pct }`. On 200 `{ ok: true }`: close panel,
re-fetch budget + refresh chip. On 403: display the 403 error message inline.

---

### 4.4 Budget Attention Items in Inbox

**Important — post-ABS-417 Inbox architecture (updated 2026-07-19):**
ABS-417 replaced the legacy escalation-only `Inbox.tsx` with a unified attention-queue
component built on `AttentionItem` objects. The new Inbox already registers `budget`
items (`TYPE_ICON.budget = "💸"`, `TYPE_CSS.budget = "type-budget"`), but its
`ActionPanel` dispatcher returns `null` for the `budget` type. This design specifies how
ABS-419 fills that gap — **not** via the old flat-list `onNavigate` prop pattern.

**Prop addition to the ABS-417 Inbox component:**

Add one optional prop alongside the existing `onOpen`, `payload`, `orchestrators`, etc.:

```typescript
onNavigate?: (view: string) => void;
```

Thread it through: `Inbox` → `AttentionRow` → `ActionPanel` → new `BudgetAction`.

**New `BudgetAction` component** (add to `Inbox.tsx`):

```typescript
function BudgetAction({
  item,
  onNavigate,
}: {
  item: AttentionItem;
  onNavigate?: (view: string) => void;
}) {
  return (
    <div className="action-panel" data-testid={`action-panel-${item.source_ref}`}>
      <div className="action-form">
        <p className="muted">{item.resolve_hint}</p>
        {onNavigate && (
          <button
            className="linkbtn"
            data-testid={`budget-view-usage-${item.source_ref}`}
            onClick={() => onNavigate("usage")}
          >
            → View Usage
          </button>
        )}
      </div>
    </div>
  );
}
```

**`ActionPanel` dispatcher addition** (no `isWriter` guard — viewing usage is read-only):

```typescript
if (item.type === "budget") {
  return <BudgetAction item={item} onNavigate={onNavigate} />;
}
```

Add this branch before the final `return null;` in `ActionPanel`. Pass `onNavigate`
down through `AttentionRow` props to reach `ActionPanel`.

**Resulting anatomy** (the "▼ Resolve" expand button is already provided by `AttentionRow`):

```
li.attention-item.type-budget[.needs-human]
  .attention-top
    span.attention-icon "💸"
    span.badge.attention-type "budget"
    span.attention-source muted         ← item.source_ref (run_id / epic key)
    span.attention-age "{N}m"
  .attention-hint                       ← item.resolve_hint from server
  button.linkbtn.attention-action-toggle "▼ Resolve"  ← provided by AttentionRow
  [expanded]:
    .action-panel[data-testid="action-panel-{source_ref}"]
      .action-form
        p.muted  {resolve_hint}
        button.linkbtn[data-testid="budget-view-usage-{source_ref}"] "→ View Usage"
```

The "→ View Usage" button calls `onNavigate("usage")`, switching the active view.
No direct resolve action is provided — budget items are informational; the human
opens the Usage view and decides (raise budget, inspect spend, initiate a stop-run
via ABS-348 controls).

**CSS for `type-budget`** (addition to `styles.css`):
```css
.type-budget { border-left: 3px solid var(--emphasis-border); }
.type-budget.needs-human { border-left-color: var(--stale); }
```
`warning` events use `var(--emphasis-border)` (needs-human orange);
`exceeded` events escalate to `var(--stale)` (blocked red) by propagating the
`needs-human` class (age threshold already applied by `AttentionRow`).

---

## 5. New TypeScript Types

```typescript
// --- ABS-419 Budget/Usage types ---

/** Single aggregation row from GET /usage */
export interface UsageRow {
  key: string;           // run_id | epic key | seat role | "YYYY-MM-DD"
  spawns: number;
  tokens_in: number;
  tokens_out: number;
  cost_usd: number;
  incomplete: boolean;   // true = unknown model(s); $ total is a floor
}

export interface UsageResponse {
  project: string;
  group: "run" | "epic" | "seat" | "day";
  rows: UsageRow[];
}

export interface BurnRateResponse {
  run_id: string | null;
  idle: boolean;
  tokens_per_hour: number;
  cost_per_hour: number;
  window_minutes: number;
}

export interface BudgetConfig {
  scope: "project" | "run" | "epic";
  scope_id: string | null;
  budget_usd: number | null;
  warning_pct: number;          // default 80
  last_alert: "none" | "warning" | "exceeded";
  updated_at: string;
}

export interface BudgetResponse {
  configs: BudgetConfig[];
}

/** Derived state for the KPI chip and Usage view */
export type BudgetState = "normal" | "warning" | "exceeded" | "no-budget" | "loading";

export interface BudgetDerived {
  state: BudgetState;
  spendUsd: number;
  budgetUsd: number | null;
  pct: number | null;             // null when no budget
  burnRateUsdPerHour: number;
  tokensIn: number;
  tokensOut: number;
  configs: BudgetConfig[];
}
```

---

## 6. Data Refresh Strategy

| Data | Trigger | Endpoint |
|---|---|---|
| Usage rows | Group switcher change + 60s poll | `GET /usage?group={group}` |
| Burn rate | 30s poll + SSE `budget-*` events | `GET /usage/burn-rate` |
| Budget config | On load, after PUT, after SSE `budget-*` | `GET /budget` |
| KPI chip | Derived from above; no separate fetch | — |

**SSE events**: When a `BUDGET-WARNING` or `BUDGET-EXCEEDED` event arrives on the SSE
stream, re-fetch both `/usage/burn-rate` and `/budget` immediately. The existing `useSSE`
hook dispatches events by type; add a listener for `budget-*` event types.

---

## 7. States Reference

| State | KPI Chip | Usage View | Inbox |
|---|---|---|---|
| No budget configured | Spend only, "no limit" muted | Budget column shows "—" | No budget items |
| Normal (< warning_pct%) | Blue bar, `$X / $Y` | Budget col: `$Y · N% · normal` | No budget items |
| Warning (≥ warning_pct%, < 100%) | Orange border + bg, orange bar | Budget col: `$Y · N% · ⚠ warning` | 💸 budget-warning item appears |
| Exceeded (≥ 100%) | Red border + bg, red bar | Budget col: `$Y · N% · 🔴 exceeded` | 💸 budget-exceeded item appears |
| Incomplete cost | — (chip unaffected) | `⚠ incomplete cost` notice + ⚠ badge on row | — |
| Loading | Placeholder `—` | Spinner/skeleton | — |
| 403 (agent session) | Not interactive | Budget config panel hidden, error message | — |

---

## 8. Accessibility Specification

- **Budget KPI chip button**: `aria-label` includes spend, budget, percent, burn rate and
  destination: e.g. `"$2.64 of $10.00 budget (26%); burn rate $0.22/h — go to usage"`.
  Tooltip via `title` attribute for token detail (not sole a11y mechanism).
- **Progress bar**: `role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}
  aria-label="Budget {pct}% used"`. Visual bar supplemented by text values.
- **Budget state (color only → not)**: State communicated by text AND color. Warning chip reads
  "⚠" prefix on the spend value + `aria-label` includes state. Exceeded reads "🔴" prefix.
  Never color-only.
- **Incomplete-cost badge**: `role="status"` on `.usage-incomplete-notice`; badge text is
  "⚠ incomplete cost" — never icon-only.
- **Group switcher buttons**: `aria-pressed="true|false"` on each; grouped with
  `role="group" aria-label="Group usage by"`.
- **Budget form**: all inputs have `<label>` with `for` attribute; save error uses
  `role="alert"`; success uses `role="status"`.
- **→ View Usage link**: Implemented as `<button>` with clear text "→ View Usage"; not icon-only.
- **Contrast compliance** (WCAG 2.1 AA):
  - `var(--text)` `#1b1f24` on `var(--panel)` `#ffffff` → ~15.9:1 ✓ (table body)
  - `var(--text)` `#1b1f24` on `var(--panel-2)` `#eceef1` → ~11.9:1 ✓ (KPI chip bg)
  - `var(--accent)` `#2563eb` on `var(--panel-2)` `#eceef1` → ~5.1:1 ✓ (normal chip value)
  - `var(--text)` `#1b1f24` on `var(--emphasis)` `#fef3c7` → ~14.1:1 ✓ (warning chip value)
  - `var(--stale)` `#b91c1c` on `var(--panel)` `#ffffff` → ~5.9:1 ✓ (exceeded chip value)
  - Exceeded chip bg: `#fff0f0` (light) — `var(--text)` `#1b1f24` on `#fff0f0` → ~14.8:1 ✓
  - Incomplete badge: `var(--emphasis-border)` `#f59e0b` text on `var(--bg)` `#f4f5f7`:
    **DEVIATION** — fails 4.5:1. **Resolution**: use `var(--text)` `#1b1f24` on `var(--emphasis)`
    `#fef3c7` → ~14.1:1 ✓ for the badge (same fix as ABS-352 stale badge).
- **Focus order**: Home KPI → ... → budget chip → [Usage view if navigated:] group switcher →
  budget-edit toggle → budget form → table (keyboard-navigable via `Tab` into rows).
- **Keyboard**: group switcher is Tab-navigable; active group button is `aria-pressed="true"`.
  Budget form completable without pointer. `Escape` closes budget config panel.
- **Motion**: 60s polling updates numbers in-place; no animation — `prefers-reduced-motion` unaffected.

---

## 9. Responsive Behavior

Design-system breakpoints are placeholders; this design uses the same breakpoints as ABS-352:

| Breakpoint | Width | Behavior |
|---|---|---|
| `desktop` | ≥1024px | KPI chip in strip (same row); Usage view full table, all columns visible |
| `tablet` | 768–1023px | KPI chip wraps to next line in KPI strip flex; Usage table scrolls horizontally; budget config panel stacks vertically |
| `mobile` | <768px | Budget chip renders as compact 2-line chip; Usage table shows key + cost only (other columns behind horizontal scroll); group switcher wraps |

---

## 10. CSS Additions (scope for FE developer)

```css
/* ---- S7 Budget KPI chip (ABS-419) ---- */

/* Budget chip state modifiers */
.home-kpi-chip.home-kpi-budget { min-width: 90px; }

.home-kpi-chip.home-kpi-budget.budget-warning {
  border-color: var(--emphasis-border);
  background: var(--emphasis);
}
.home-kpi-chip.home-kpi-budget.budget-exceeded {
  border-color: var(--stale);
  background: #fff0f0;   /* light: ~14.8:1 with var(--text) */
}
@media (prefers-color-scheme: dark) {
  .home-kpi-chip.home-kpi-budget.budget-exceeded { background: #2c1010; }
}

.home-kpi-budget-top {
  display: flex; align-items: baseline; gap: 2px;
}
.home-kpi-budget-limit { font-size: 12px; color: var(--muted); }
.home-kpi-budget-bar {
  width: 100%; height: 4px; border-radius: 2px;
  background: var(--border); overflow: hidden; margin: 3px 0;
}
.home-kpi-budget-bar-fill {
  height: 100%; border-radius: 2px; transition: width .3s ease;
  background: var(--accent); /* overridden by state classes */
}
.budget-warning .home-kpi-budget-bar-fill { background: var(--emphasis-border); }
.budget-exceeded .home-kpi-budget-bar-fill { background: var(--stale); }

/* Exceeded KPI value accent (WARNING state has NO text color override — see DAC-7) */
/* IMPORTANT: .budget-warning .home-kpi-value must NOT be set to var(--emphasis-border).
   That color (#f59e0b) on the warning bg (var(--emphasis) = #fef3c7) yields only 1.87:1
   contrast, failing WCAG 1.4.3. The warning value text INHERITS var(--text) from the base
   chip style — do not add a color override for the warning state. If styles.css contains
   `.budget-warning .home-kpi-value { color: var(--emphasis-border); }` — REMOVE that line. */
.budget-exceeded .home-kpi-value { color: var(--stale); }

/* ---- S7 Usage View (ABS-419) ---- */

.usage-view {
  flex: 1; display: flex; flex-direction: column;
  padding: 16px; overflow-y: auto; gap: 12px;
}
.usage-header {
  display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
}
.usage-header h2 { margin: 0; font-size: 16px; }

.usage-group-switcher {
  display: flex; gap: 4px;
}
.usage-group-switcher button {
  padding: 4px 10px; font-size: 12px;
  background: var(--panel-2); color: var(--text);
  border: 1px solid var(--border); border-radius: 6px;
}
.usage-group-switcher button[aria-pressed="true"] {
  background: var(--accent); color: #fff; border-color: var(--accent);
}

.usage-budget-config {
  background: var(--panel); border: 1px solid var(--border);
  border-radius: 8px; padding: 12px; display: flex; flex-direction: column; gap: 8px;
}
.budget-form { display: grid; gap: 6px; }
.budget-form label { font-size: 12px; color: var(--muted); }
.budget-form input { width: 120px; }

.usage-incomplete-notice {
  background: var(--emphasis); border: 1px solid var(--emphasis-border);
  border-radius: 6px; padding: 8px 12px; font-size: 13px;
  display: flex; align-items: center; gap: 8px;
}

.badge.badge-incomplete {
  background: var(--emphasis);
  border-color: var(--emphasis-border);
  color: var(--text);   /* #1b1f24 on #fef3c7 → 14.1:1 ✓ */
}

.usage-table { overflow-x: auto; }
.usage-table table {
  width: 100%; border-collapse: collapse; font-size: 13px;
}
.usage-table th {
  text-align: left; font-size: 11px; text-transform: uppercase;
  letter-spacing: .04em; color: var(--muted);
  padding: 6px 8px; border-bottom: 1px solid var(--border);
}
.usage-table td {
  padding: 6px 8px; border-bottom: 1px solid var(--border);
}
.usage-table tr:last-child td { border-bottom: none; }
.usage-table tr:hover td { background: var(--panel-2); }

.usage-total td { font-weight: 700; color: var(--text); border-top: 2px solid var(--border); }

.usage-key a, .usage-key button.linkbtn {
  color: var(--accent); font-weight: 700;
}

/* Inbox budget type (ABS-419 addition to ABS-417 base) */
.type-budget { border-left: 3px solid var(--emphasis-border); }
.type-budget.needs-human { border-left-color: var(--stale); }

@media (max-width: 1023px) {
  .usage-table table { min-width: 500px; }
}
@media (max-width: 767px) {
  .home-kpi-chip.home-kpi-budget { min-width: 70px; }
  .home-kpi-budget-limit { display: none; }  /* show in aria-label, hide visually on mobile */
}
```

---

## 11. New API Calls (additions to `api.ts`)

```typescript
export async function getUsage(project: string, group: "run"|"epic"|"seat"|"day"): Promise<UsageResponse> { … }
export async function getBurnRate(project: string, runId?: string): Promise<BurnRateResponse> { … }
export async function getBudget(project: string): Promise<BudgetResponse> { … }
export async function putBudget(project: string, body: {
  scope: "project"|"run"|"epic";
  scope_id?: string | null;
  budget_usd: number | null;
  warning_pct?: number;
}): Promise<{ ok: boolean }> { … }
```

---

## 12. New Files / Modifications for Implementer

| File | Change |
|---|---|
| `backend/apps/web/src/types.ts` | Add `UsageRow`, `UsageResponse`, `BurnRateResponse`, `BudgetConfig`, `BudgetResponse`, `BudgetState`, `BudgetDerived` |
| `backend/apps/web/src/api.ts` | Add `getUsage`, `getBurnRate`, `getBudget`, `putBudget` |
| `backend/apps/web/src/hooks/useBudget.ts` | New hook: fetches + derives `BudgetDerived`; polls + responds to SSE `budget-*` events |
| `backend/apps/web/src/components/BudgetChip.tsx` | New: replaces `home-kpi-budget` placeholder in `HomeView.tsx` |
| `backend/apps/web/src/components/UsageView.tsx` | New: group switcher, table, budget config panel |
| `backend/apps/web/src/components/HomeView.tsx` | Replace placeholder `<span>` with `<BudgetChip>` + wire `onNavigate("usage")` |
| `backend/apps/web/src/components/Inbox.tsx` | (1) Add `onNavigate?: (view: string) => void` prop to the ABS-417 Inbox component; thread through `AttentionRow` → `ActionPanel`; (2) Add new `BudgetAction` function component; (3) Add `budget` branch in `ActionPanel` dispatcher (before `return null`) — see §4.4 |
| `backend/apps/web/src/App.tsx` | Add `"usage"` to view union; add "Usage" nav tab; mount `<UsageView>` |
| `backend/apps/web/src/styles.css` | Append S7 Budget KPI + Usage View CSS block |

---

## 13. Design System Deviation Report

**Deviation 1** (Critical — pre-existing, ongoing): `docs/design/DESIGN_SYSTEM.md` contains
only placeholder tokens. Real tokens are in `backend/apps/web/src/styles.css`. This design
references the CSS vars directly. Already escalated to System Architect by ABS-352; no new
escalation needed here — the same finding applies. **Recommendation**: populate DESIGN_SYSTEM.md
from styles.css values (ADR-A-0017 compliance).

**Deviation 2** (Minor): `.badge.badge-incomplete` cannot use `var(--emphasis-border)` as
text color (amber on amber background fails WCAG 4.5:1 — same issue as ABS-352 stale badge).
**Resolution**: badge uses `var(--text)` on `var(--emphasis)` background → ~14.1:1. Specified
above in CSS block and accessibility section.

**Deviation 3** (Scope): `background: #fff0f0` (exceeded chip, light mode) and `#2c1010`
(dark mode) are one-off hex values for the exceeded state. The design system has no
`color.error-bg` token equivalent to `color.warning-bg`. **Recommendation**: add
`--stale-bg: #fff0f0` (light) / `#2c1010` (dark) to `styles.css` and reference as
`var(--stale-bg)`. **Reported to System Architect** as a design-system addition for the
exceeded state — consistent with the existing `--emphasis` / `--emphasis-border` warning pair.
Implementer may use the hex literals until the token is added.

---

## 14. Design Acceptance Criteria (DACs)

```markdown
## Design Acceptance Criteria [ABS-419]

**Design artifact**: docs/agent-outputs/designs/ABS-419-design.md
**Design system**: docs/design/DESIGN_SYSTEM.md → de-facto tokens: backend/apps/web/src/styles.css

### Schema Conformance
- [ ] DAC-1: The budget KPI chip uses exactly the existing 5-state color palette:
  normal state bar fill = `var(--accent)` (#2563eb / #60a5fa); warning state chip
  border and bar fill = `var(--emphasis-border)` (#f59e0b / #b7791f) with chip bg
  `var(--emphasis)`; exceeded state = `var(--stale)` (#b91c1c / #f87171). No 6th color
  is introduced anywhere in the budget/usage surface.

- [ ] DAC-2: The Usage table's incomplete-cost badge uses `var(--text)` foreground on
  `var(--emphasis)` background (not amber-on-amber). Measured contrast ≥ 4.5:1 in both
  light and dark themes.

- [ ] DAC-3: Budget config form inputs have programmatic `<label>` elements (`for`
  attribute matching `id`). Save error uses `role="alert"`; save success uses `role="status"`.

### Accessibility
- [ ] DAC-4: The budget KPI chip `<button>` carries an `aria-label` that includes:
  current spend, total budget, percentage, burn rate, and destination (e.g.
  "$2.64 of $10.00 budget (26%); burn rate $0.22/h — go to usage"). State is NOT
  communicated by color alone: warning chip text carries "⚠" prefix in the spend
  value; exceeded chip text carries a visible indicator. Verified: no color-only state.

- [ ] DAC-5: The progress bar inside the budget chip has `role="progressbar"`,
  `aria-valuenow={pct}`, `aria-valuemin="0"`, `aria-valuemax="100"`, and
  `aria-label` including the percentage.

- [ ] DAC-6: The group switcher buttons have `aria-pressed="true"` on the active group
  and `aria-pressed="false"` on others; grouped with `role="group" aria-label="Group usage by"`.

- [ ] DAC-7: Contrast ratios (light mode, to be re-verified in dark):
  - `var(--text)` on `var(--panel)` ≥ 15:1 ✓ (table body)
  - `var(--accent)` #2563eb on `var(--panel-2)` #eceef1 ≥ 4.5:1 ✓ (normal chip value)
  - `var(--text)` on `var(--emphasis)` ≥ 14:1 ✓ (warning chip value and incomplete badge)
  - `var(--stale)` #b91c1c on `var(--panel)` #ffffff ≥ 4.5:1 ✓ (exceeded chip value)

### Responsive
- [ ] DAC-8: At viewport 1440×900, the budget chip renders in the KPI strip on the same
  row as the other chips without overflow or vertical scroll on the Home view.

- [ ] DAC-9: At viewport 768px width (tablet), the Usage table is horizontally scrollable
  (not cut off) and the budget config panel stacks vertically within the view.

- [ ] DAC-10: At viewport <768px (mobile), the budget chip renders as a compact 2-line
  chip; the `/ $budget` limit may be visually hidden (verified via aria-label that it
  remains accessible).

### User Flows
- [ ] DAC-11: Normal → Warning → Exceeded state transitions: with a seeded budget fixture,
  - At spend < warning_pct%: chip has `var(--accent)` bar and no warning border. (e2e)
  - At spend ≥ warning_pct% and < 100%: chip gains `budget-warning` class with
    `var(--emphasis-border)` border and bg `var(--emphasis)`. (e2e)
  - At spend ≥ 100%: chip gains `budget-exceeded` class with `var(--stale)` border
    and exceeded bg. (e2e)

- [ ] DAC-12: Clicking the budget chip navigates to the Usage view (view switcher
  activates "usage"); the Usage view renders with run group selected by default and
  the correct row data matching the S6 API fixture totals. (e2e)

- [ ] DAC-13: Group switcher toggles Usage table content: switching from "Run" to "Seat"
  calls `GET /usage?group=seat` and re-renders the table with seat-role rows. (e2e)

- [ ] DAC-14: Incomplete-cost fixture (a row with `incomplete: true`): the `⚠ incomplete cost`
  notice appears above the table; the affected row shows a `⚠` badge on its cost cell;
  the total row also shows the badge. The total is NOT silently zero. (e2e)

- [ ] DAC-15: Budget config round-trip (human role): a maintainer user can open the
  "⚙ Budget" panel, enter `budget_usd=20` and `warning_pct=75`, submit, and the chip
  re-fetches and reflects the new limit. The 403 path (agent token) renders
  "Budget config is not available for this session" — no form rendered. (e2e)

- [ ] DAC-16: Budget attention items in Inbox (post-ABS-417 Inbox structure): a
  `budget`-type `AttentionItem` renders with icon 💸 and CSS class `type-budget` in the
  attention queue. Clicking "▼ Resolve" expands the `ActionPanel`; the panel contains a
  button with `data-testid="budget-view-usage-{item.source_ref}"` labelled "→ View Usage"
  that, when clicked, switches the active view to "usage" (e2e: assert nav-usage tab becomes
  `aria-current="page"` after click). Works for both `budget-warning` and `budget-exceeded`
  source_ref values. (e2e)
```
