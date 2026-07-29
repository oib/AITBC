# ABS-348 Design — Board Stop-run / Abort-spawn Controls

**Ticket**: ABS-230 S9 — Command Queue + Control Endpoint + Board Stop/Abort Controls
**Design artifact**: `docs/agent-outputs/designs/ABS-348-design.md`
**Design system**: `docs/design/DESIGN_SYSTEM.md` (starter template — see *Deviations*)
**De-facto token source**: `backend/apps/web/src/styles.css` `:root` custom properties (light + `prefers-color-scheme: dark`)
**Author**: ui-ux-design · 2026-07-16 · **Revision 2 (2026-07-17): DAC-4 contrast fix**
**Scope note**: This story is backend-heavy (command queue + control/enqueue endpoints). The
**UI surface** this design governs is the board **Stop-run** and **Abort-spawn** controls plus
their delivery/execution status feedback (AC #5). Backend ACs (#1–#4) carry no visual surface and
are out of design scope — they are the data contract this UI consumes.

> **Revision 2 (2026-07-17) — DAC-4 (WCAG AA contrast) fix.** QAS-Design's Design Test
> (`docs/agent-outputs/qa-validations/ABS-348-design-validation.md`) verified the implemented
> board and passed DAC-1..3, DAC-5..12 but **failed DAC-4**: six white-text-on-solid-fill
> pairings measured < 4.5:1 (e.g. `.btn-danger` dark `#fff`/`--stale #f87171` = 2.77:1; pill
> executed light `#fff`/`--live #16a34a` = 3.30:1 — failing even in light). Root cause was
> Rev-1's own §4/§5 spec (white text on solid state fills). This revision **re-specifies the
> failing pairings with measured, theme-correct foregrounds** (see §4 destructive button + §4.1
> status pill + §5). No behavioural or layout change — only the token/foreground pairings move.
> Implementer applies the CSS in §4/§4.1 to `styles.css`; component markup gains a leading state
> **dot** per pill (§4.1). QAS-Design re-verifies DAC-4 against these numbers.

---

## 1. Context & Constraints

- The board SPA (`backend/apps/web`) already authenticates via an HttpOnly session cookie. The
  session probe `api.whoami()` returns `{ authenticated: boolean, role: string }`
  (`backend/apps/web/src/api.ts:56`). **Role is already available client-side** but `App.tsx`
  currently discards it (only maps to `auth = "in" | "out"`).
- Human roles rank `viewer < maintainer < admin` (`role text CHECK (... 'viewer','maintainer','admin')`,
  `backend/packages/core/src/migrations/001_init.sql:85`). "role ≥ Maintainer" ≡ `role ∈ {maintainer, admin}`,
  exactly the server's `WRITER_ROLES = ["admin","maintainer"]` (`routes/dashboard.ts:51`).
- Registered orchestrator instances already render in the topbar via `<Orchestrators>`
  (`components/Orchestrators.tsx`, classes `.orchestrators`/`.orch`/`.dot`, live/stale colour).
- Existing write-action vocabulary lives in the `TicketDrawer` `Actions` panel
  (`.actions fieldset`/`legend`, `data-testid="actions"`) — the design reuses its structure and
  its `busy`-disable + `role="alert"` note pattern.

**Auth split (given by the ticket's implementation constraint):**
- **Enqueue** (Stop-run / Abort-spawn) → `POST /api/v1/…` (human session, gated ≥ Maintainer).
- **Poll** (shipper picks up commands) → `GET /agent/v1/orchestrators/:id/commands` (orchestrator token).
The UI only ever touches the **enqueue** surface; it never sees the poll surface.

---

## 2. Layout & Placement

Both controls attach to the **orchestrator they act on**, so they live in the topbar
`.orchestrators` cluster (next to the live/stale chip), NOT on individual Kanban cards.

```
┌ topbar ─────────────────────────────────────────────────────────────────────┐
│ Agentic Board Monitor  [project▾]  ● live   ⟨orchestrators⟩          Log out  │
│                                             │                                 │
│                              orch-1 · live  [⏹ Stop run ▾]   ← maintainer+ only│
│                              orch-2 · stale                  ← no live run     │
└───────────────────────────────────────────────────────────────────────────────┘
```

### 2.1 Stop-run control (run-level)

- Rendered as a button **appended to each live orchestrator chip** in `.orchestrators`, ONLY when
  `session.role ∈ {maintainer, admin}` AND `orch.status === "live"`. Absent (not just disabled) for
  `viewer`, for agent/orchestrator token sessions, and for stale instances.
- Label: `⏹ Stop run`. Destructive styling (see §4 `.btn-danger`).
- Click → **confirmation dialog** (design-system `Dialog/confirmation`, focus-trapped, ESC to close):
  > "Stop run on **orch-1**? Queued spawns finish; no new spawns start. This is an audited human action."
  Buttons: `Cancel` (secondary) / `Stop run` (destructive, default focus = Cancel).
- Confirm → `POST /api/v1/projects/:p/orchestrators/:id/commands { kind: "stop-run", idempotency_key }`.

### 2.2 Abort-spawn control (spawn-level)

- The orchestrator chip carries a **disclosure caret** (`▾`, `aria-expanded`) that expands a small
  **control popover** listing that instance's active spawns. Each row:
  `⟨ledger-id⟩ · ⟨role⟩ · ⟨ticket-key⟩            [⏹ Abort]`
- The `Abort` button is rendered per spawn, maintainer+ only; click → confirmation dialog
  ("Abort spawn `⟨ledger-id⟩` (`⟨ticket-key⟩`)? The in-flight agent is killed. Audited human action.")
  → `POST /api/v1/projects/:p/orchestrators/:id/commands { kind: "abort-spawn", ledger_id, idempotency_key }`.
- If the instance has no active spawns, the popover shows `.muted` "no active spawns".

> **Data dependency (flagged to implementer/SA):** the `Orchestrator` type
> (`web/src/types.ts:71`) carries no active-spawn list today. Abort-spawn needs each instance's
> active ledger entries (`ledger_id`, `role`, `ticket key`) surfaced on the orchestrators payload
> (or a sibling `GET …/orchestrators/:id/spawns`). This is a backend/type addition the implementer
> must land; the design assumes it exists.

### 2.3 Command status feedback (delivery/execution receipts — AC #5 surface)

Each enqueued command renders an inline **status pill** next to the control that spawned it, driven
by the command's state machine (pending → delivered → executed | failed). **The pill is an
outline/tinted chip** (Rev 2 — mirrors the existing `.badge`): its text is always `var(--text)`
(legible in both themes) and the command **state is conveyed by the border colour + a leading
state dot + the label word — never by the text colour** (setting the label to `var(--live)` is the
Rev-1 mistake that failed 4.5:1). See §4.1 for the CSS and §5 for measured contrast.

| Command state | Pill label   | Border + dot token | Class            |
| ------------- | ------------ | ------------------ | ---------------- |
| pending       | `queued`     | `--muted`          | `.cmd-pending`   |
| delivered     | `delivered`  | `--accent`         | `.cmd-delivered` |
| executed      | `executed`   | `--live`           | `.cmd-executed`  |
| failed        | `failed`     | `--stale`          | `.cmd-failed`, `role="alert"` |

The pill is a live region (`aria-live="polite"`, `failed` → `role="alert"`) so a receipt update is
announced. State advances as the SPA refetches on the existing SSE tick (`App.tsx` `useSSE` → `refresh`).

---

## 3. States

| State                     | Visual                                                                 |
| ------------------------- | ---------------------------------------------------------------------- |
| default (maintainer+)     | `⏹ Stop run` button visible on each live orchestrator chip; caret present |
| viewer / agent session    | **No** Stop/Abort buttons, **no** caret — controls entirely absent (AC #5) |
| stale orchestrator        | chip only, no Stop-run button (nothing to stop)                        |
| confirm pending           | modal dialog open, focus trapped, background inert                     |
| submitting (`busy`)       | control disabled (`button:disabled` → `opacity:.5`), pill = `queued`   |
| delivered                 | pill `delivered` (`--accent`)                                          |
| executed                  | pill `executed` (`--live`); control returns to idle                    |
| failed                    | pill `failed` (`--stale`), `role="alert"`, retry offered               |
| 403 (role lost mid-session)| inline `.err` "Not permitted — maintainer role required."; controls hide on next probe |

**Idempotency in the UI:** each control generates ONE `idempotency_key` per user intent (per confirm
click) and reuses it across retries of the same intent, so a retry of a failed submit does not
enqueue a duplicate (mirrors AC #3 server semantics; the key is a client-generated UUID).

---

## 4. Tokens & Components Used

All values reference `styles.css` `:root` custom properties (the live token layer). None invented.

| Element                       | Token / existing class                                   |
| ----------------------------- | -------------------------------------------------------- |
| Topbar container              | `.topbar` (`--panel` bg, `--border` bottom)              |
| Orchestrator chip             | `.orch` / `.orch-live`/`.orch-stale`, `.dot` (existing)  |
| Control popover surface       | `--panel` bg, `1px solid var(--border)`, `border-radius:8px` (matches `.inbox-row`/`.column`) |
| Primary/secondary button      | `button` (`--accent`), `.linkbtn` (transparent, `--muted`) — existing |
| **Destructive button** (new)  | `.btn-danger` — filled `var(--stale)`, foreground **per theme** for WCAG AA (§4 CSS) |
| Confirmation dialog           | design-system `Dialog/confirmation` (focus-trapped, ESC) |
| Spawn row                     | `.actions fieldset`-style grouping; `.chip` for `role`/`ledger-id` |
| Status pill                   | `.cmd-pill` (new) — **outline** chip mirroring `.badge`; shape `font-size:10px; padding:1px 6px; border-radius:10px` (§4.1 CSS) |
| Error/alert note              | `.err` (`--stale`), `role="alert"` (existing pattern)    |

**New classes introduced** (reported as deviations, §6): `.btn-danger`, `.cmd-pill` (+ `.cmd-pending/.cmd-delivered/.cmd-executed/.cmd-failed` and the leading `.dot`), `.orch-controls` (popover).

### 4.1 DAC-4 contrast-safe CSS (Rev 2 — implementer applies verbatim to `styles.css`)

Rev-1's `#fff`-on-solid-fill pairings failed WCAG AA in the dark theme (all pills + button) and
even in the light theme for `--live` (executed). The corrected pairings, with **measured sRGB
ratios** (WCAG 2.1; 10px pill text = normal text, so 4.5:1 applies), are:

```css
/* Destructive button: filled --stale; foreground chosen PER THEME so both clear >=4.5:1.
   No single foreground passes both --stale values (dark-red wants white, light-red wants ink). */
.btn-danger {
  background: var(--stale);
  color: #fff;                 /* light: #fff on --stale #b91c1c = 6.47:1  PASS */
  border: 1px solid var(--stale);
}
@media (prefers-color-scheme: dark) {
  .btn-danger { color: #1b1f24; } /* dark: #1b1f24 on --stale #f87171 = 5.99:1  PASS */
}

/* Status pill: OUTLINE/tinted (mirrors .badge). Text is ALWAYS --text (state-independent),
   so it passes in both themes; state is shown by the border colour + a leading dot + the
   label word. Do NOT set the label text to the state token (that is the Rev-1 failure). */
.cmd-pill {
  display: inline-flex; align-items: center; gap: 4px;
  font-size: 10px; padding: 1px 6px; border-radius: 10px;
  background: var(--panel);
  color: var(--text);          /* label: light 16.56:1 / dark 14.06:1  PASS (all states) */
  border: 1px solid var(--border);
}
.cmd-pill .dot { width: 6px; height: 6px; border-radius: 50%; }  /* state dot: non-text, >=3:1 */
.cmd-pending   { border-color: var(--muted);  }  .cmd-pending  .dot { background: var(--muted);  }
.cmd-delivered { border-color: var(--accent); }  .cmd-delivered .dot { background: var(--accent); }
.cmd-executed  { border-color: var(--live);   }  .cmd-executed .dot { background: var(--live);   }
.cmd-failed    { border-color: var(--stale);  }  .cmd-failed   .dot { background: var(--stale);  }
```

The pill markup gains one element — a leading `<span class="dot">` before the label
(`<span class="cmd-pill cmd-executed"><span class="dot"></span>executed</span>`). No other markup
or behavioural change. `--text`/`--panel`/`--border`/the four state tokens are all existing
`styles.css` `:root` custom properties; the only literals are the two `.btn-danger` foregrounds
(`#fff`, `#1b1f24`), confined to `styles.css` (never in TSX).

---

## 5. Accessibility (WCAG 2.1 AA)

- **Contrast (Rev 2 — measured sRGB, WCAG 2.1, both themes; §4.1 is the source of truth):**
  - Destructive button `.btn-danger`: light `#fff` on `--stale #b91c1c` = **6.47:1** ✓; dark
    `#1b1f24` on `--stale #f87171` = **5.99:1** ✓ (per-theme foreground; no single colour passes
    both `--stale` values).
  - Status-pill **label** is `var(--text)` on `var(--panel)` for every state → light **16.56:1** /
    dark **14.06:1** ✓ (state-independent, so all four states pass identically).
  - Status-pill **state dot** (non-text indicator, ≥3:1 bar) on `--panel`: light muted 4.83 /
    accent 5.17 / live 3.30 / stale 6.47 — dark muted 6.85 / accent 6.79 / live 9.91 / stale 6.24;
    all ≥ 3:1 ✓. State is never conveyed by colour alone (label word + border + dot), satisfying
    WCAG 1.4.1.
- **Keyboard**: Stop-run/Abort reachable by Tab in DOM order (chip → Stop → caret → popover rows);
  caret toggles on Enter/Space; dialog is focus-trapped with ESC-to-close and returns focus to the
  invoking control on close.
- **Labels**: each button has an explicit accessible name naming its target
  (`aria-label="Stop run on orch-1"`, `aria-label="Abort spawn ⟨ledger-id⟩"`); the caret uses
  `aria-expanded` + `aria-controls`.
- **Confirmation focus**: default focus lands on **Cancel** (non-destructive default), per
  destructive-action safety.
- **Live regions**: status pill `aria-live="polite"`; `failed` escalates to `role="alert"`.
- **Reduced motion**: popover expand respects `prefers-reduced-motion` (no transition when set).

---

## 6. Design-System Deviations (reported to System Architect)

1. **`DESIGN_SYSTEM.md` is an unfilled placeholder template** (`{{COLOR_PRIMARY}}` etc.). The board's
   real token layer is the CSS custom properties in `backend/apps/web/src/styles.css`. This design
   cites those. **Recommendation:** populate `DESIGN_SYSTEM.md` from `styles.css`, or point the DS file
   at `styles.css` as the source of truth so `design-system-check` has real tokens to verify.
2. **No destructive `Button` variant exists in-app.** Existing `button` is primary (`--accent`); the
   DS lists a `destructive` Button variant but the app has no class for it. Design introduces
   `.btn-danger` (`--stale`), matching the DS `Button/destructive` intent. Confirm token/naming with SA.
3. **`Orchestrator` payload lacks active-spawn data** (needed for Abort-spawn ledger-ids) — see §2.2.
   Backend/type addition required before this UI is buildable.
4. **`role` is fetched but dropped** in `App.tsx`. Thread the `whoami()` `role` into App state and pass
   to `<Orchestrators>` so controls can gate on `role ∈ {maintainer, admin}` (client-side visibility;
   server enforces the real boundary — client gating is defence-in-depth, not the security control).
5. **Advisory (Rev 2, from QAS-Design DAC-8):** `.topbar` has no `flex-wrap` and no width media
   queries; `.orchestrators` already wraps and the popover is viewport-clamped (DAC-8 passes), but on
   a very narrow viewport the topbar row can overflow horizontally. Recommend adding
   `flex-wrap: wrap` to `.topbar` in the same pass. Not a DAC-4 blocker — hardening only.

---

## 7. Design Acceptance Criteria (Design Test contract)

See the `handoff` comment posted to ABS-348 for the DAC-numbered block. These ACs are verifiable by
QAS-Design against a running board without the designer present.
