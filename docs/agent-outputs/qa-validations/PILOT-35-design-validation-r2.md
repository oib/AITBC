# Design Validation Report (r2) — PILOT-35

**Ticket**: PILOT-35 — Mission Control: Event-Feed-Einträge zeigen relative Zeit (0m/4m/1h) + volles Datum on hover
**Design artifact**: `docs/agent-outputs/designs/PILOT-35-design.md` (commit `329c7252`)
**Implementation commit**: `d6256253` (rebased onto `gitlab/main` `7438e790`, post-PILOT-37)
**Branch**: `PILOT-35-auto` (tip `1575425e` at QAS-Design r2 entry)
**QAS-Design run**: 2026-07-25 (r2 — post-rebase-conflict-resolution re-validation)
**Prior r1 verdict**: DESIGN APPROVED (commit `748957b8`, all 19 DACs passed against `7f3fd329`)
**Verdict**: ✅ **DESIGN APPROVED**

---

## Context: Why r2?

After the first QAS-Design pass (19/19 DACs PASS, `748957b8`) and PO acceptance, RTE
attempted to merge `PILOT-35-auto` to `main`. A conflict arose because PILOT-36
(merged first as MR !190) had introduced a reserved `.feed-event-time` placeholder span
at the exact trailing position where PILOT-35 inserts its `.feed-event-age` span in
`EventFeed.tsx`. The conflict also affected `styles.css`.

The FE Developer resolved the conflict (`d6256253`; pushed at `748957b8` then QAS r2
added `1575425e`). The System Architect independently approved the merge resolution
(gate-results `2026-07-25T14:45:21Z`). QAS r2 confirmed 22/22 e2e pass and `tsc`
exit 0 (`1575425e`).

This r2 pass re-validates the same 19 DACs against the rebased implementation
(`d6256253`), focusing on whether the conflict resolution introduced any design
regressions.

---

## Key Changes Introduced by the Rebase Conflict Resolution

| Change | Design impact |
|--------|---------------|
| `EventRow` gains `rowClass` (PILOT-36 seed dimming: `feed-item-seed`) alongside `ageS` (PILOT-35) | Age span rendering in `EventRow` is **independent** of `rowClass`; the span is still rendered unconditionally for any truthy `occurred_at` |
| Single `shown.map` → three separate maps: `followShown`, `seedShown`, `browseShown` | All three maps pass `now={now}` to `EventRow` ✓ |
| `.feed-event-time` placeholder (PILOT-36) replaced by `.feed-event-age` (PILOT-35) in CSS | PILOT-35's `.feed-event-age` rule is the authoritative rule; only an explanatory CSS comment remains of the placeholder |
| Duplicate `formatAbsolute` import deduped in `EventFeed.tsx` | Single import from `../lib/formatTime` — DAC-19 holds |
| `HomeView.tsx` auto-merged cleanly | No change to Home Ticker rendering |

---

## Pre-Check

| Item | Status | Evidence |
|------|--------|----------|
| Design artifact exists | ✅ | `docs/agent-outputs/designs/PILOT-35-design.md` at `329c7252` (unchanged) |
| DAC block present on ticket | ✅ | 19 DACs (DAC-1..19) in ui-ux-design handoff comment (`2026-07-25T09:45:03Z`) |
| All DACs testable without designer | ✅ | Concrete values throughout: `11px`, `var(--muted)`, regex `{N}[smhd]`, `YYYY-MM-DD HH:MM:SS`, aria pattern |
| Design system file exists | ✅ | `docs/design/DESIGN_SYSTEM.md` present; de-facto tokens in `theme.css` + `styles.css` (pre-existing placeholder deviation, ABS-352/419/473/430/PILOT-33) |
| Design-system-check gate | N/A | Neutral/backend profile → gate inert (no `config.design_system.enabled: true`) |
| DAC freeze integrity | ✅ | DAC block unchanged since r1; no DACs added, removed, or modified during the rebase-bounce iteration |

Pre-check: **PASSED**

---

## DAC Verification (all 19, against `d6256253`)

### Schema Conformance

**DAC-1** — Every `EventRow` in the EventFeed (Follow mode and Browse mode) renders
`<span data-testid="feed-event-age">` as the last child of the `<li>`; `color: var(--muted)`;
`font-size: 11px`.

- `EventRow` component still renders the age span as its final child (after `.feed-to-follow`
  in Follow mode, after `.feed-to` in Browse/seed):
  ```jsx
  {ageS !== null && (
    <span className="feed-event-age" data-testid="feed-event-age"
      title={...} aria-label={...}>{formatAge(ageS)}</span>
  )}
  ```
  This is the **last** element in the `<li>` regardless of whether `seed=true` or `follow=true` ✓
- `ageS` is `null` only when `event.occurred_at` is falsy. All three render sites feed events
  with non-null `occurred_at` (DB `RunEvent[]` for seed/browse; `liveToRun()` sets
  `occurred_at: e.at` for follow) ✓
- All three render paths pass `now={now}`:
  - `followShown.map(e => <EventRow ... now={now} />)` ✓
  - `seedShown.map(e => <EventRow ... now={now} />)` ✓
  - `browseShown.map(e => <EventRow ... now={now} />)` ✓
- CSS: `.feed-event-age { font-size: 11px; color: var(--muted); ... }` confirmed in `styles.css` ✓
- **→ PASS**

**DAC-2** — Every `<li data-testid="ticker-item">` in the Home Ticker renders
`<span data-testid="ticker-event-age">`; `color: var(--muted)`; `font-size: 11px`.

- `HomeView.tsx` auto-merged cleanly — no change to ticker rendering from r1.
  `<span className="home-ticker-age" data-testid="ticker-event-age" ...>` inside every
  `<li ... data-testid="ticker-item">` ✓
- CSS: `.home-ticker-age { font-size: 11px; color: var(--muted); ... }` ✓
- **→ PASS**

**DAC-3** — Age text matches `{N}s|{N}m|{N}h|{N}d`; no other characters.

- `formatAge()` from `lib/formatTime.ts` (unchanged) returns exactly this pattern ✓
- e2e: `expect(age).toHaveText(/^\d+[smhd]$/)` confirmed PASS in QAS r2 run (2/2 PILOT-35 tests, `d6256253`) ✓
- **→ PASS**

**DAC-4** — `title` attribute = "YYYY-MM-DD HH:MM:SS" (24h, ISO date).

- EventFeed: `title={formatAbsolute(event.occurred_at)}` ✓
- HomeView: `title={formatAbsolute(e.at)}` ✓
- `formatAbsolute` function unchanged (single definition in `lib/formatTime.ts`) ✓
- e2e: `expect(title).toMatch(/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/)` → PASS (QAS r2) ✓
- **→ PASS**

**DAC-5** — `aria-label` contains both relative age AND absolute timestamp, separated by " — ".

- EventFeed: `` aria-label={`${formatAge(ageS)} ago — ${formatAbsolute(event.occurred_at)}`} `` ✓
- HomeView: `` aria-label={`${formatAge(ageS)} ago — ${formatAbsolute(e.at)}`} `` ✓
- e2e: `expect(ariaLabel).toMatch(/^\d+[smhd] ago — \d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/)` → PASS ✓
- **→ PASS**

**DAC-6** — Age text updates without page reload; ≤60 s tick interval; `key` unchanged on tick.

- EventFeed: `const [now, setNow] = useState(() => Date.now()); useEffect(() => { const t = setInterval(() => setNow(Date.now()), 30_000); return () => clearInterval(t); }, []);` — 30 s interval, cleanup on unmount ✓
- HomeView: same pattern ✓
- List keys unchanged across ticks:
  - `followShown`: `key={e.seq}` ✓
  - `seedShown`: `key={\`seed-${e.seq}\`}` ✓
  - `browseShown`: `key={e.seq}` ✓
- **→ PASS**

**DAC-7** — Follow mode: `.feed-event-age` is last sibling of `.feed-to-follow` inside
`.feed-item`; `margin-left: auto`.

- In `EventRow` with `follow=true`:
  `<span className="feed-to feed-to-follow">{" "}{label}</span>` is immediately followed
  by the age span (when `ageS !== null`) — the age span is the last child ✓
- CSS: `.feed-event-age { margin-left: auto; flex-shrink: 0; }` within `.feed-item { display: flex; flex-wrap: wrap; }` ✓
- PILOT-36's `rowClass` adds `feed-item-seed` on seed rows but the flex layout is
  inherited; margin-left: auto still right-aligns the age span ✓
- **→ PASS**

---

### Accessibility

**DAC-8** — Contrast ≥4.5:1 (light), ≥4.4:1 (dark) for `var(--muted)` on feed/ticker background.

- No change to `theme.css` in the rebase. Values confirmed in r1:
  - Light: `--muted: #5c636e` on `#ffffff` → **5.56:1** ✓ (>4.5)
  - Dark: `--muted: #9aa4b2` on `#171b22` → **6.51:1** ✓ (>4.4)
- Both `.feed-event-age` and `.home-ticker-age` use `color: var(--muted)` unconditionally ✓
- **→ PASS**

**DAC-9** — Age span NOT keyboard-focusable; no `tabindex`.

- `EventFeed.tsx` and `HomeView.tsx` contain no `tabindex` attribute on any age span ✓
- `<span>` is not natively focusable ✓
- e2e: `expect(await age.getAttribute("tabindex")).toBeNull()` → PASS (QAS r2) ✓
- **→ PASS**

**DAC-10** — Screenreader announces `aria-label` value, not just visible text.

- `aria-label` on `<span>` overrides text content as accessible name (WAI-ARIA 1.2) ✓
- Pattern identical to `Inbox.tsx` ABS-467 precedent (already accepted) ✓
- **→ PASS**

**DAC-11** — No color-only differentiation between fresh (0s) and stale (3h) events.

- `.feed-event-age { color: var(--muted); }` — static, unconditional ✓
- `.home-ticker-age { color: var(--muted); }` — static, unconditional ✓
- Note: `rowClass` adds `feed-item-seed` (opacity 0.6) on seed rows — this affects the
  **row container** opacity, not the age span's color classification. No conditional color
  on the age `<span>` itself ✓
- **→ PASS**

---

### Responsive Breakpoints

**DAC-12** — Desktop (≥1024px): `[data-testid="feed-event-age"]` visible and right-aligned; no overflow.

- CSS unchanged from r1: `.feed-item { display: flex; flex-wrap: wrap; align-items: baseline; gap: 3px; }` ✓
- `.feed-event-age { margin-left: auto; flex-shrink: 0; white-space: nowrap; }` ✓
- PILOT-36's `.feed-item-seed` adds `opacity: 0.6` only — layout/alignment unaffected ✓
- **→ PASS**

**DAC-13** — Mobile (<600px): age span wraps below, not cropped.

- `flex-wrap: wrap` on `.feed-item` → wraps at narrow viewports ✓
- `.feed-event-age { flex-shrink: 0; }` — never clips ✓
- **→ PASS**

**DAC-14** — All breakpoints: `[data-testid="ticker-event-age"]` visible in Home Ticker; no overflow.

- HomeView ticker unchanged from r1; `.home-ticker-age { white-space: nowrap; }` ✓
- **→ PASS**

---

### User Flows

**DAC-15** — EventFeed Follow-mode age flow: load MC → assert `feed-event-age` per `feed-item` →
inspect `title` → assert `formatAge` text.

- Follow mode renders `followShown.map(e => <EventRow ... now={now} />)`. Each `EventRow`
  renders the age span when `occurred_at` is truthy. `liveToRun()` maps `LiveEvent.at →
  occurred_at`, which is always set ✓
- **→ PASS**

**DAC-16** — EventFeed Browse-mode age flow: switch to Browse → assert age stamps → page 2 → age stamps.

- Browse mode now uses its own dedicated `browseShown` map (PILOT-36 split). Critically,
  `now={now}` IS passed: `browseShown.map(e => <EventRow ... now={now} />)` ✓
- Browse events are DB `RunEvent[]` — `occurred_at` always populated ✓
- Page 2 is loaded via `loadPage()` into `browseEvents` → flows through the same
  `browseShown` map → age spans present ✓
- **→ PASS** *(This was the most critical change to verify for the rebase.)*

**DAC-17** — Home Ticker age flow: navigate Home → assert `ticker-item` → assert `ticker-event-age`
format → inspect `title`.

- `HomeView.tsx` auto-merged cleanly; ticker rendering unchanged from r1 ✓
- PILOT-35 e2e `home.spec.ts` test ("PILOT-35: ticker items show a relative age stamp…") is
  present in `d6256253` and confirmed PASS in QAS r2 run ✓
- **→ PASS**

**DAC-18** — Format identical between EventFeed age and Ticket (Attention Queue) display.

- Both use `formatAge` from `lib/formatTime.ts` (EventFeed: direct import; HomeView attention
  queue: via `util.ts` re-export) — same function, identical output for equal elapsed seconds ✓
- **→ PASS**

**DAC-19** — No second `formatAge`/`formatAbsolute` implementation.

- `EventFeed.tsx` after dedup: `import { formatAge, formatAbsolute } from "../lib/formatTime";`
  (single import, no local body) ✓
- QAS r2 confirmed: `git grep "function formatAge\|function formatAbsolute" backend/apps/web/src/`
  returns exactly one location: `src/lib/formatTime.ts` ✓
- **→ PASS**

---

## Design-System Deviation Check

`docs/design/DESIGN_SYSTEM.md` carries `{{PLACEHOLDER}}` tokens (pre-existing, reported to SA
via ABS-352/419/473/430/PILOT-33). De-facto tokens from `theme.css`/`styles.css` are the
effective contract. No new token introduced by PILOT-35 or by the rebase conflict resolution.
Design-system-check gate: **N/A** (neutral/backend profile).

---

## Green-Run Proof (ABS-453)

The story modifies `eventfeed-timeline.spec.ts` and `home.spec.ts`.

| Run | Result | Commit | Evidence |
|-----|--------|--------|----------|
| PILOT-35 isolated: `npx playwright test --grep "PILOT-35"` | **2 passed, 0 failed** | `d6256253` | QAS r2 gate-results comment (`2026-07-25T14:50:53Z`) |
| Full changed-spec suite: `eventfeed-timeline.spec.ts` + `home.spec.ts` | **22 passed, 0 failed** | `d6256253` | QAS r2 gate-results comment (improvement from r1's 20/21 — ABS-468 AC2 pre-existing resolved by PILOT-36 code now on main) |
| `tsc --noEmit` | **exit 0** | `d6256253` | QAS r2 gate-results comment |

The "0 executed" failure class (ABS-453 / ABS-416 / ABS-418 negative example) does NOT apply:
2 PILOT-35 tests ran and passed; 22 total suite tests ran and passed.

---

## Rebase-Specific Design Concern Assessment

The rebase introduced PILOT-36's split of the single `shown.map` into three maps
(`followShown`, `seedShown`, `browseShown`). This was the primary design risk: if `now={now}`
were absent from any render site, that mode's age stamps would be frozen.

**Verification result**: All three render sites pass `now={now}` to `EventRow` ✓. Seed rows
additionally receive `seed=true` which changes `rowClass` to `feed-item-seed` (opacity 0.6) but
does NOT affect the age span — `ageS` is computed from `event.occurred_at` (which seed DB events
always have), and the span rendering is unconditional on the `seed` prop. No design regression
from the merge resolution.

---

## Summary

| Category | DACs | Result |
|----------|------|--------|
| Schema Conformance | DAC-1..7 | ✅ 7/7 PASS |
| Accessibility | DAC-8..11 | ✅ 4/4 PASS |
| Responsive Breakpoints | DAC-12..14 | ✅ 3/3 PASS |
| User Flows | DAC-15..19 | ✅ 5/5 PASS |
| **Total** | **DAC-1..19** | **✅ 19/19 PASS** |

**Verdict: DESIGN APPROVED (r2)**

All 19 design acceptance criteria re-verified against the rebased implementation (`d6256253`).
The rebase conflict resolution (PILOT-36 seed-dimming + PILOT-35 age stamp co-location) is
correct from a design standpoint: `now={now}` propagated to all three render sites, age span
is unconditional on the `seed` prop, CSS rules are clean (`.feed-event-time` dropped,
`.feed-event-age` authoritative). No design defects introduced by the merge resolution.

Design-system-check: N/A (neutral profile, gate inert).
Failure classification: N/A (no failures).
DAC freeze: verified (DAC block unchanged from r1).

---

## Handoff

QAS-Design validation complete for PILOT-35 (r2). All 19 DACs PASSED. Evidence posted to ticket.
Design Approved — ready for Story Acceptance; functional gate already passed by QAS (r2).
