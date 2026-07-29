# Design: PILOT-34 — Mission Control Human-Override-Transitionen (Done/Rejected)

**Ticket**: PILOT-34 — Mission Control: Human-Override-Transitionen — Operator kann Tickets
auf Done/Rejected setzen
**Design by**: ui-ux-design
**Date**: 2026-07-25
**Design system**: `docs/design/DESIGN_SYSTEM.md`
**Token source**: `backend/apps/web/src/theme.css` + `backend/apps/web/src/styles.css`
(design-system file is a starter template with `{{PLACEHOLDER}}` tokens; real resolved
values live in the CSS files — same standing deviation as ABS-352/ABS-419/ABS-473/PILOT-33;
see §12)
**Related**: ABS-464 (Drawer-Transition-Guardrails — UNTOUCHED by this design),
ABS-478 (ReauthPrompt — reused), ADR-A-0026 (First-class orchestration state)

---

## 1. Design Goal

The operator (admin-session) cannot force a ticket to a terminal state in Mission Control.
This design adds a **Human-Override panel** inside the existing `TicketDrawer` that lets
the operator set any non-terminal ticket directly to **Done** or **Rejected (Won't Do)**
via an audited, confirm-dialog-gated action. Agent seats are blocked server-side (403).

Separately, this design resolves the `#PATH_DECISION` (§3) and specifies the schema
addition for the `Rejected` status (§4). The Architect must sign off on the `#PATH_DECISION`
before implementation starts.

---

## 2. Design Token Mapping

De-facto token source: `backend/apps/web/src/theme.css` (pre-existing deviation §12).

| Design token (DESIGN_SYSTEM.md) | CSS var | Light | Dark | Usage in this design |
|---|---|---|---|---|
| `color.background` | `var(--bg)` | `#f4f5f7` | `#0e1116` | Dialog scrim overlay |
| `color.surface` | `var(--panel)` | `#ffffff` | `#171b22` | Dialog background |
| `color.surface-2` | `var(--panel-2)` | `#eceef1` | `#1f242c` | Cancel button background |
| `color.text` | `var(--text)` | `#1b1f24` | `#e6e8eb` | Dialog body text |
| `color.muted` | `var(--muted)` | `#5c636e` | `#9aa4b2` | Override fieldset legend, help text |
| `color.primary` | `var(--accent)` | `#1d4ed8` | `#60a5fa` | "Set Done" confirm button (btn-primary) |
| `color.error` | `var(--stale)` | `#b91c1c` | `#f87171` | "Reject" confirm button (btn-destructive), Rejected badge |
| `color.border` | `var(--border)` | `#d6dae0` | `#2b313a` | Fieldset border, textarea |
| `color.on-danger` | `var(--on-danger)` | `#ffffff` | `#ffffff` | Destructive button text |

**Components used** (design system § Components):
- **Dialog/confirmation** → `.dialog-scrim` + `.dialog` (existing pattern, MergeAction)
- **Button/primary** → `.btn-primary` — "Set Done" confirm action
- **Button/secondary** → `.btn-secondary` — Cancel in dialog
- **Button/destructive** → `.btn-destructive` — "Reject (Won't Do)" and its confirm action
- **Input/text** → `<textarea>` — mandatory override reason
- **Card/default** → `<fieldset>` wrapper (existing pattern throughout `Actions`)

---

## 3. #PATH_DECISION: Rejected Status Schema

### 3.1 Options Considered

| Option | Description | Verdict |
|---|---|---|
| **A** | `Rejected` as a distinct `terminal: true` status in `statuses.yaml`, modeled after `Canceled` | **CHOSEN** |
| **B** | `Done` + `resolution` field (e.g. `resolution: "won't-do"`) | Rejected — see §3.2 |

### 3.2 Rationale for Option A

**Semantic clarity**: `Done` means "work is complete". A consciously-deferred ticket is not
done — it is actively rejected. Sharing a status conflates two meaningfully different outcomes
and makes board queries ambiguous ("how many stories were completed vs deferred?").

**Jira-parität**: Jira exposes `Won't Do` as a *Resolution* on a Canceled/Won't Do ticket,
NOT as a `Done` resolution. `Rejected` maps directly to that Jira concept; it would also
be easy to shadow-sync from the Jira `Won't Do` resolution to `Rejected` in the backend
mirror (Koexistenz, ABS-326).

**Runner compatibility**: The runner already handles terminal statuses data-drivenly via
`terminal: true` flag (`status_is_terminal`, `is_legit_rest_status`, `is_known_status`,
`first_live_claim`, `propagate_start_label terminal-skip`). Adding `Rejected` with
`terminal: true` and `next: []` requires only: (1) adding it to `statuses.yaml` and the
backend `statuses.yaml`, (2) adding it to the runner's explicit known/terminal name sets
where they are not file-driven (zero or few such locations). No structural change to the
runner logic.

**No schema sprawl**: A `resolution` field would need additions to `BoardTicket`, `TicketDetail`,
`InboxItem`, API payloads, database columns, and the board display — five or more surface
changes for a field used in exactly one code path (the override).

### 3.3 Rejected Status Specification

Add to BOTH `profiles/neutral/adapters/statuses.yaml` AND
`backend/packages/core/src/workflows/statuses.yaml`:

```yaml
  # pipeline: shared | class: resting (terminal — PILOT-34 Human-Override.
  # An operator has consciously decided this ticket will not be implemented
  # ("Won't Do"). Modeled after Canceled (ABS-338). Runner/sweeps treat
  # Rejected identically to Done and Epic Done: terminal: true exempts it
  # from the stall counter, respawn limiter, and all sweep escalations.
  # The Human-Override in Mission Control is the ONLY entry path (admin role,
  # audited, confirm-dialog + mandatory reason). Jira shadow-mirror maps
  # Jira Resolution 'Won't Do' to this status (Koexistenz, ABS-326).
  - name: Rejected
    terminal: true
    entered_when: Operator (admin) overrides the ticket via Mission Control
      Human-Override panel (confirm dialog + mandatory reason)
    triggers: None — terminal; runner and sweeps skip it (stall-counter exempt,
      respawn-limiter exempt, JOIN excluded)
    next: []
```

**Runner changes** (scope for be-developer to enumerate fully):
- Add `"Rejected"` to any explicit hardcoded terminal-status name sets (wherever `Canceled`
  appears but the list is NOT file-driven). The `status_is_terminal` function that reads
  `terminal: true` from the YAML covers it automatically; the concern is hardcoded name
  lists in `STUCK-DETECT`, `is_legit_rest_status`, `is_known_status`, `first_live_claim`,
  `propagate_start_label terminal-skip`, and the JOIN rule's terminal check.
- Sweep documentation: update any sweep docstrings that enumerate terminal statuses.

**Board column**: `Rejected` belongs in the same column group as `Canceled` (the "Closed" /
"Terminal" group, or however the server assigns it). The implementer must verify the board
column assignment with the backend's `GroupBy` logic.

---

## 4. Override Panel — Component Anatomy

### 4.1 Where it lives

Inside the existing `Actions` component (`TicketDrawer.tsx`), as a **new `<fieldset>`
appended AFTER the existing Labels fieldset** and BEFORE the `MergeAction`. This preserves
the existing content → timeline → actions reading order (ABS-463).

### 4.2 Visibility gate

```typescript
/** Admin-only: Human Override is MORE restrictive than the existing isWriter check. */
function isAdmin(role: string | null | undefined): boolean {
  return role === "admin";  // maintainer and agent tokens are excluded
}
```

The override panel renders ONLY when `isAdmin(role)` is true.
- `role === 'admin'` → panel visible
- `role === 'maintainer'` → panel hidden (maintainers use the normal transition flow)
- agent/orchestrator tokens → panel hidden (server also enforces 403)
- no session / read-only → already gated by existing `!isWriter` early return

**Rationale**: The ticket spec says "Operator (Admin-Session)". The Confirm dialog calls this
out visually too. This is stricter than the existing `isWriter` and intentional.

### 4.3 Non-terminal ticket requirement

The override is only meaningful for non-terminal tickets. The panel should check that
`status` is not already a terminal state (Done, Epic Done, Canceled, Rejected). If the
ticket is already terminal, render a read-only notice instead:

```
<p class="muted" data-testid="override-terminal-notice">
  This ticket is already in a terminal state ({status}) — no override available.
</p>
```

The server enforces this too (transition to Done/Rejected from Done/Rejected is not a valid
state-machine edge), so this is a UI guard for clarity.

### 4.4 Override panel HTML anatomy

```
fieldset.action-override[disabled={busy}]
  [data-testid="action-override"]

  legend "Admin Override"

  p.muted.override-help
    [data-testid="override-help"]
    "Terminate this ticket as Done or Rejected — bypasses the normal pipeline.
     A mandatory reason is posted as a comment and appears in the audit trail."

  textarea[aria-label="override reason"]
    [placeholder="Reason (required) — will be posted as a comment"]
    [data-testid="override-reason"]
    [value={overrideReason}]
    [onChange → setOverrideReason]

  div.override-actions
    button.btn-primary.override-btn-done
      [data-testid="override-btn-done"]
      [disabled={!overrideReason.trim() || busy}]
      [onClick → openOverrideConfirm("Done")]
      "✓ Set Done"

    button.btn-destructive.override-btn-reject
      [data-testid="override-btn-reject"]
      [disabled={!overrideReason.trim() || busy}]
      [onClick → openOverrideConfirm("Rejected")]
      "✕ Reject (Won't Do)"

  [if overrideNote]
  p.err[role="alert"][data-testid="override-note"]
    {overrideNote}
```

### 4.5 State additions to `Actions`

```typescript
// ---- PILOT-34: Admin Override ----
const [overrideReason, setOverrideReason] = useState("");
const [overrideTarget, setOverrideTarget] = useState<"Done" | "Rejected" | null>(null);
const [overrideConfirmOpen, setOverrideConfirmOpen] = useState(false);
const [overrideNote, setOverrideNote] = useState<string | null>(null);

const overrideTriggerRef = useRef<HTMLButtonElement>(null);  // for focus return after dialog
const overrideCancelRef = useRef<HTMLButtonElement>(null);   // focus target on dialog open

function openOverrideConfirm(target: "Done" | "Rejected") {
  setOverrideTarget(target);
  setOverrideConfirmOpen(true);
}
```

---

## 5. Confirm Dialog — Component Anatomy

Follows the existing `MergeAction` dialog pattern (ABS-349):
- Focus-trapped: Cancel button auto-focuses on open
- ESC closes the dialog and returns focus to the triggering button
- Scrim click closes the dialog
- The `aria-label` uses the canonical action name

```
div.dialog-scrim[onClick → closeOverrideConfirm]
  div.dialog[role="dialog"]
    [aria-modal="true"]
    [aria-labelledby="override-dialog-title"]
    [data-testid="override-confirm-dialog"]
    [onClick → e.stopPropagation()]

    h3#override-dialog-title
      [data-testid="override-confirm-title"]
      "⚠ Admin Override — {target === "Done" ? "Set Done" : "Reject (Won't Do)"}"

    p.override-confirm-msg
      [data-testid="override-confirm-message"]
      "Move {key} from {status} to {target}?
       This is an admin override that terminates the ticket and cannot be undone.
       The reason below will be posted as a kind:override comment on the ticket."

    blockquote.override-confirm-reason
      [data-testid="override-confirm-reason-preview"]
      {overrideReason}

    p.muted.override-confirm-note
      "Agent seats cannot perform this action — it is blocked server-side for
       non-admin tokens."

    div.dialog-actions
      button.btn-secondary
        [data-testid="override-confirm-cancel"]
        [onClick → closeOverrideConfirm]
        [ref → overrideCancelRef]
        [disabled={busy}]
        "Cancel"

      button[target === "Done" ? ".btn-primary" : ".btn-destructive"]
        [data-testid="override-confirm-submit"]
        [onClick → doOverride]
        [disabled={busy}]
        "{target === "Done" ? "✓ Set Done" : "✕ Reject (Won't Do)"}"
```

**Focus management** (same as `MergeAction`):
```typescript
useEffect(() => {
  if (!overrideConfirmOpen) return;
  overrideCancelRef.current?.focus();
  const onKey = (e: KeyboardEvent) => {
    if (e.key === "Escape") closeOverrideConfirm();
  };
  window.addEventListener("keydown", onKey);
  return () => window.removeEventListener("keydown", onKey);
}, [overrideConfirmOpen, closeOverrideConfirm]);
```

---

## 6. API Contract

### 6.1 New endpoint: human override

```
POST /api/v1/projects/:project/items/:key/override
Body: {
  to: "Done" | "Rejected",
  reason: string,     // non-empty; validated server-side
  expect_from: string // CAS: the current status when the drawer opened (AC2 of ABS-464)
}

Response 200: { ok: true }
Response 400: { error: "invalid_target" | "empty_reason" }
Response 403: { error: "forbidden" }   ← any non-admin role (maintainer, agent, anon)
Response 409: { error: "cas_conflict", actual: string }  ← ticket moved since drawer opened
Response 422: { error: "already_terminal" }  ← ticket is already Done/Rejected/Canceled/Epic Done
```

**Server behaviour** (design contract for be-developer):
1. Validate the session role is `admin` — else 403.
2. Validate `to` ∈ `{"Done", "Rejected"}` — else 400.
3. Validate `reason` is non-empty — else 400.
4. CAS check: current status MUST equal `expect_from` — else 409 with `actual`.
5. Validate current status is not already terminal — else 422.
6. In a single atomic transaction:
   a. Write the status transition (from current → `to`), actor=human.
   b. Write a `kind: override` comment:
      body = `"Admin override: {from} → {to}. Reason: {reason}"`.
7. Return 200.

**Note on `withReauth`**: The new `humanOverride` API function should route through
`withReauth` (the 401/403 reauth interceptor in `api.ts`) for session-lapse scenarios.
A genuine admin 403 (returned when the session is valid but role is not admin) would
trigger the reauth prompt — this is acceptable: after re-auth with an admin token the
retry will succeed; after re-auth with a non-admin token the retry returns 403 and the
`withReauth` path returns that result unchanged (since reauthed → false → original result
returned). No infinite loop.

### 6.2 api.ts addition

```typescript
// ---- PILOT-34: Admin Override ----

/**
 * Admin override transition — moves a ticket directly to Done or Rejected
 * from any non-terminal status. Admin role required (403 for all others).
 * Atomic: transition + kind:override comment in one write.
 * `expectFrom` is the CAS guard (current status at drawer render).
 */
export function humanOverride(
  project: string,
  key: string,
  to: "Done" | "Rejected",
  reason: string,
  expectFrom: string,
): Promise<WriteResult> {
  return sendJSON("POST", `${itemUrl(project, key)}/override`, {
    to,
    reason,
    expect_from: expectFrom,
  });
}
```

### 6.3 doOverride handler in Actions

```typescript
const doOverride = () =>
  run(async () => {
    if (!overrideTarget) return;
    const res = await api.humanOverride(project, key, overrideTarget, overrideReason, status);
    if (res.status === 409) {
      setConflict(res.body?.actual ?? "(unknown)");
      setOverrideConfirmOpen(false);
      return;
    }
    if (res.status === 422) {
      setOverrideNote(`Ticket is already in a terminal state — no override needed.`);
      setOverrideConfirmOpen(false);
      return;
    }
    if (!res.ok) {
      setOverrideNote(`Override failed (${res.status}): ${res.body?.error ?? "unknown"}`);
      setOverrideConfirmOpen(false);
      return;
    }
    setOverrideReason("");
    setOverrideTarget(null);
    setOverrideConfirmOpen(false);
    await onChanged();
  });
```

---

## 7. Conflict Handling

The `409 CAS conflict` path reuses the existing `conflict` state already in `Actions`:

```typescript
if (res.status === 409) {
  setConflict(res.body?.actual ?? "(unknown)");
  setOverrideConfirmOpen(false);
  return;
}
```

The existing `conflict !== null` block renders:
```
"This ticket moved to {conflict} since you opened it. Nothing was changed."
[Reload button]
```

This covers the override conflict case without new UI. If the ticket moved to a terminal
state (e.g., another admin set it to Done first), the conflict message reveals that — the
operator can reload and see the resolved state.

---

## 8. Responsive Behaviour

Breakpoints (from styles.css authoritative comment: sm=600px, md=768px, lg=1024px):

| Breakpoint | Override panel | Confirm dialog |
|---|---|---|
| `desktop` (≥1024px) | Full-width fieldset inside the 400px drawer; "✓ Set Done" and "✕ Reject" side by side in `.override-actions` flex row | Dialog centred, max-width 420px |
| `tablet` (768–1023px) | Full-width fieldset; `.override-actions` wraps to two rows | Dialog centred, 90vw max-width |
| `mobile` (<768px) | Full-width; buttons stack vertically (flex-wrap) | Dialog full-width (minus 24px margin), no horizontal scroll |

The `.override-actions` wrapper uses `flex-wrap: wrap; gap: 8px` — identical to
`.attention-actions` (PILOT-33) so buttons wrap naturally at narrow widths.

The confirm dialog uses the existing `.dialog-scrim` / `.dialog` CSS that already handles
responsive centering via `margin: auto`. No new breakpoint rules needed.

---

## 9. Accessibility Specification

Per design system WCAG 2.1 AA (existing standard, carried from ABS-417/ABS-464).

### 9.1 Override panel

- `<fieldset>` with `<legend>Admin Override</legend>` provides group labelling.
- Override reason `<textarea>` has `aria-label="override reason"`.
- Both action buttons have descriptive text labels (not icon-only): "✓ Set Done" and
  "✕ Reject (Won't Do)". The `aria-label` is not needed because the visible text is
  already descriptive.
- Buttons disabled when reason is empty — `disabled` attribute prevents activation
  by keyboard and pointer.
- Error note: `role="alert"` on `p.err[data-testid="override-note"]` announces errors
  to screen readers.
- Admin-only notice: when the session is `maintainer` and the panel is hidden, NO
  "you don't have access" message is shown (the panel is simply absent — same as
  non-writer sessions for the merge control). Only admins see it.

### 9.2 Confirm dialog

- `role="dialog"` + `aria-modal="true"` + `aria-labelledby="override-dialog-title"`.
- Focus moves to Cancel button on open (defensive UX — user can dismiss ESC without
  clicking, and the default focus prevents accidental submit).
- Focus returns to the triggering button (`overrideTriggerRef`) on close — the last
  clicked button ("Set Done" or "Reject") receives focus so the operator knows where
  they are.
- ESC closes via `keydown` listener (same as existing `MergeAction` pattern).
- Scrim background: clicking outside the `.dialog` div closes it — same as
  `MergeAction` and the ABS-464 transition confirm dialog.
- "⚠ Admin Override" in the dialog title is text (not icon-only).

### 9.3 Focus order (addition to ABS-464 order)

Within the Actions section, after the Labels fieldset:
```
Override fieldset legend →
  Override reason textarea →
  "✓ Set Done" button →
  "✕ Reject (Won't Do)" button

When dialog open (modal, focus-trapped):
  Dialog heading (sr-only: dialog label) →
  Confirm message →
  Reason preview blockquote →
  Cancel button [auto-focus] →
  Confirm button
```

### 9.4 Contrast calculations (light mode)

- `var(--text)` `#1b1f24` on `var(--panel)` `#ffffff` (dialog body): ~14:1 ✓
- `var(--on-danger)` `#ffffff` on `var(--stale)` `#b91c1c` (btn-destructive): ~5.9:1 ✓
- `var(--on-danger)` `#ffffff` on `var(--accent)` `#1d4ed8` (btn-primary): ~5.3:1 ✓
- `var(--muted)` `#5c636e` on `var(--panel)` `#ffffff` (help text): ~8.6:1 ✓

All dark-mode equivalents symmetric via `theme.css` dark variant (same ratio class as
ABS-475 established for `--muted`/`--stale`/`--accent` on dark backgrounds).

---

## 10. CSS Additions (scope for FE developer)

```css
/* ---- PILOT-34: Admin Override panel ---- */

/* Override fieldset — same padding and border pattern as action-comment/action-labels */
.action-override {
  margin-top: 12px;
  padding: 8px 10px;
  border: 1px solid var(--border);
  border-radius: 6px;
}

.action-override legend {
  font-size: 12px;
  font-weight: 600;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: .03em;
  padding: 0 4px;
}

/* Help text below legend — same muted style as .reason-help (ABS-464) */
.override-help {
  font-size: 12px;
  color: var(--muted);
  margin: 4px 0 8px;
  line-height: 1.45;
}

/* Reason textarea — same sizing as existing transition reason textarea */
.action-override textarea {
  width: 100%;
  box-sizing: border-box;
  min-height: 64px;
  resize: vertical;
  font-size: 13px;
  margin-bottom: 8px;
}

/* Two-button row: wraps to stacked at narrow widths */
.override-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

/* Reason preview inside the confirm dialog — indented blockquote */
.override-confirm-reason {
  margin: 8px 0;
  padding: 6px 12px;
  border-left: 3px solid var(--border);
  font-size: 13px;
  color: var(--muted);
  background: var(--panel-2);
  border-radius: 0 4px 4px 0;
  white-space: pre-wrap;
  word-break: break-word;
}

/* Sub-note inside dialog — "agent seats cannot perform..." */
.override-confirm-note {
  font-size: 11px;
  color: var(--muted);
  margin-top: 6px;
}

/* Terminal notice (when ticket is already terminal and admin opens drawer) */
.override-terminal-notice {
  font-size: 12px;
  color: var(--muted);
  font-style: italic;
}
```

---

## 11. New Files / Modifications for Implementer

| File | Change |
|---|---|
| `profiles/neutral/adapters/statuses.yaml` | Add `Rejected` terminal status per §3.3 |
| `backend/packages/core/src/workflows/statuses.yaml` | Same addition |
| `backend/packages/core/src/` (state machine) | Add `Rejected` to any hardcoded terminal/known-status name sets (wherever `Canceled` appears); add `POST /items/:key/override` endpoint with role=admin gate + atomic write |
| `backend/apps/web/src/api.ts` | Add `humanOverride(...)` function (§6.2) |
| `backend/apps/web/src/types.ts` | No new types required (uses existing `WriteResult`) |
| `backend/apps/web/src/components/TicketDrawer.tsx` | Add `isAdmin()` helper; add override state variables + refs; add `openOverrideConfirm`, `closeOverrideConfirm`, `doOverride` handlers; add `action-override` fieldset and confirm dialog inside `Actions` (§4, §5) |
| `backend/apps/web/src/styles.css` | Append PILOT-34 Admin Override CSS block (§10) |

**Backend scope — atomic write**: The override endpoint MUST write the transition and the
`kind: override` comment in a single database transaction. If either write fails, both
must roll back. This prevents partial state (ticket moved but no audit comment, or
comment without transition).

**e2e scope**: The ticket ACs require `Backlog → Rejected` override with reason (writer
verifies audit comment) AND agent-token attempt on the same endpoint → 403. The FE
developer should confirm e2e test scope — the design contracts both paths.

---

## 12. Design System Deviation Report

**Deviation 1** (Critical — pre-existing, ongoing): `docs/design/DESIGN_SYSTEM.md`
contains only `{{PLACEHOLDER}}` tokens. Real tokens are in `backend/apps/web/src/theme.css`
and `backend/apps/web/src/styles.css`. Escalated to System Architect in ABS-352, ABS-419,
ABS-473, PILOT-33; no new escalation required.

**Deviation 2** (Minor, new): The `Rejected` status badge color in the board/drawer needs
a semantic color treatment distinct from both `Done` (which currently uses the standard
status badge) and `Canceled`. Proposal: use `var(--stale)` border on the badge (red, same
as the destructive button) to signal "not proceeding" — consistent with the error/warning
color semantics already established in the codebase. If the design-system formalises a
`color.rejected` token, it maps to `var(--stale)`. No new token added here — `var(--stale)`
is used directly, same as the `btn-destructive` uses it. If the team wants a distinct
`color.rejected-badge`, that addition should be proposed to System Architect for inclusion
in `DESIGN_SYSTEM.md` and `theme.css`.

---

## 13. Out of Scope

- Normal-flow transition guardrails (ABS-464) — UNCHANGED by this design.
- Maintainer-level override (design explicitly limits to admin role).
- Bulk override (multiple tickets at once) — out of scope.
- Restoring a Rejected ticket (Rejected is terminal, `next: []`; restore = new ticket).
- Agent-initiated Rejected (rejected by server-side role gate, not in scope for any UI).
- Jira shadow-mirror of `Rejected` ↔ Jira `Won't Do` resolution — Koexistenz scope (ABS-326).

---

## 14. Design Acceptance Criteria (DACs)

```markdown
## Design Acceptance Criteria [PILOT-34]

**Design artifact**: docs/agent-outputs/designs/PILOT-34-design.md
**Design system**: docs/design/DESIGN_SYSTEM.md → de-facto tokens: backend/apps/web/src/theme.css + styles.css

### Schema Conformance

- [ ] DAC-1: The `Rejected` status entry is present in BOTH
  `profiles/neutral/adapters/statuses.yaml` AND
  `backend/packages/core/src/workflows/statuses.yaml` with `terminal: true` and
  `next: []`. Verify by running: `grep -A3 "name: Rejected" <file>` on both files
  and confirming `terminal: true` and `next: \[\]`.

- [ ] DAC-2: The "Admin Override" fieldset (`data-testid="action-override"`) is rendered
  ONLY when the session role is `admin`. Verify by loading the drawer with (a) role=admin
  → fieldset present; (b) role=maintainer → fieldset absent; (c) no session/read-only →
  fieldset absent.

- [ ] DAC-3: Both override buttons ("✓ Set Done" `data-testid="override-btn-done"` and
  "✕ Reject (Won't Do)" `data-testid="override-btn-reject"`) are `disabled` when the
  reason textarea is empty. Type any non-whitespace character → both become enabled.
  Clear the textarea → both return to disabled. (Verify with `aria-disabled` check or
  DOM `disabled` attribute inspection.)

- [ ] DAC-4: The confirm dialog (`data-testid="override-confirm-dialog"`) carries
  `role="dialog"`, `aria-modal="true"`, and `aria-labelledby="override-dialog-title"`.
  Verify by DOM inspection.

- [ ] DAC-5: The override fieldset uses `.btn-primary` for "Set Done" confirm button and
  `.btn-destructive` for "Reject (Won't Do)" confirm button. Confirm by inspecting
  `data-testid="override-confirm-submit"` class list for each path.

- [ ] DAC-6: The `.action-override` fieldset appends AFTER the Labels fieldset
  and BEFORE the MergeAction control (if present). Verify DOM order in drawer.

### Accessibility

- [ ] DAC-7: On confirm dialog open, focus moves to `data-testid="override-confirm-cancel"`
  (the Cancel button). Verify with a focus-tracking assertion or accessibility audit.

- [ ] DAC-8: ESC key closes the confirm dialog without submitting. After close, focus
  returns to the button that opened the dialog ("Set Done" or "Reject"). Verify by
  keyboard-only walkthrough: Tab to "Reject" → Enter → dialog opens → ESC → dialog
  closes → focus on "Reject" button.

- [ ] DAC-9: The override reason textarea has `aria-label="override reason"`. Verify by
  `document.querySelector('[data-testid="override-reason"]').getAttribute('aria-label')`.

- [ ] DAC-10: Contrast (light mode):
  - `var(--on-danger)` `#ffffff` on `var(--stale)` `#b91c1c` (btn-destructive "Reject"):
    measured ≥4.5:1 ✓ (ABS-464 established this pair).
  - `var(--on-danger)` `#ffffff` on `var(--accent)` `#1d4ed8` (btn-primary "Set Done"):
    measured ≥4.5:1.
  - `var(--muted)` on `var(--panel)` (override help text): measured ≥4.5:1.
  All three verified in dark mode equivalents.

- [ ] DAC-11: A non-admin session (e.g., role=maintainer) DOES NOT see the override
  fieldset. No "you don't have access" text is shown — the panel is simply absent.
  Verify by loading drawer as maintainer: `data-testid="action-override"` is NOT in DOM.

### Responsive

- [ ] DAC-12: At viewport ≥1024px (desktop), "✓ Set Done" and "✕ Reject (Won't Do)"
  render on the same horizontal row inside `.override-actions`.

- [ ] DAC-13: At viewport <768px (mobile), `.override-actions` wraps so both buttons
  stack vertically. Neither button is horizontally clipped or overflows the drawer.

### User Flows

- [ ] DAC-14: **Admin Done override e2e flow**: with an admin session and a ticket in a
  non-terminal status (e.g., Backlog), admin enters a reason and clicks "✓ Set Done" →
  confirm dialog opens → dialog title contains "Set Done" and "admin override" text →
  admin clicks confirm → ticket status updates to "Done" → a `kind:override` comment
  appears in the timeline starting with "Admin override: Backlog → Done. Reason:" followed
  by the entered reason text → drawer updated status badge reads "Done". Steps:
  1. Open drawer for a Backlog ticket as admin.
  2. Locate `data-testid="action-override"`, enter non-empty reason in
     `data-testid="override-reason"`.
  3. Click `data-testid="override-btn-done"`.
  4. Assert `data-testid="override-confirm-dialog"` is visible; title includes "Set Done".
  5. Click `data-testid="override-confirm-submit"`.
  6. Assert drawer status (`data-testid="drawer"` → `.drawer-status`) reads "Done".
  7. Assert timeline (`data-testid="timeline"`) first comment has `data-testid="comment-override"`.

- [ ] DAC-15: **Admin Reject override e2e flow**: same as DAC-14 but via "✕ Reject
  (Won't Do)" → confirm dialog title contains "Reject (Won't Do)" → after confirm, status
  reads "Rejected" → timeline shows `kind:override` comment with "→ Rejected".

- [ ] DAC-16: **Agent-token 403 gate**: using an agent/orchestrator token (non-admin
  session), attempt `POST /api/v1/projects/:p/items/:key/override` with a valid body →
  server returns 403 `{ error: "forbidden" }`. No transition occurs; the ticket status
  is unchanged. (UI guard: `data-testid="action-override"` is not rendered for agent
  sessions.)

- [ ] DAC-17: **CAS conflict path**: admin opens the drawer for ticket at status S1 →
  meanwhile another process moves the ticket to S2 → admin enters a reason and confirms
  the override → server returns 409 `{ error: "cas_conflict", actual: "S2" }` → the
  conflict banner (`data-testid="cas-conflict"`) appears reading "This ticket moved to
  S2 since you opened it. Nothing was changed." → a Reload button is visible. The ticket
  status was NOT changed.

- [ ] DAC-18: **Terminal ticket guard**: load the drawer for a ticket whose status is
  already `Done`, `Rejected`, `Canceled`, or `Epic Done` as an admin → the override
  fieldset shows the terminal notice (`data-testid="override-terminal-notice"`) instead
  of the action buttons. No "Set Done" or "Reject" buttons are in the DOM.

- [ ] DAC-19: **Reason required guard**: admin opens drawer for a non-terminal ticket →
  both "✓ Set Done" and "✕ Reject" are `disabled` (DOM `disabled` attribute present) →
  admin types a space into the reason textarea → buttons remain disabled (whitespace-only
  is rejected client-side, i.e. `reason.trim() === ""`) → admin types "a" → buttons
  become enabled.
```

---

## 15. Notes for Architect

The `#PATH_DECISION` documented in §3 must be signed off by the System Architect before
implementation begins. The design recommends **Option A (Rejected as distinct terminal
status)**. Specifically, the Architect should confirm:

1. Whether `next: []` for `Rejected` is correct (no reopen edge), or if there is an
   operational need for a `Rejected → Backlog` reopen edge (same question that was
   asked for `Canceled` in ABS-338 — concluded with `next: []`).
2. The board column assignment for `Rejected` (which `BoardColumn.group` it joins).
3. Whether the runner's terminal-status detection is fully file-driven (covering
   `Rejected` automatically via `terminal: true`) or whether explicit name-list
   additions are needed beyond what this design's §3.3 enumerates.
4. Whether an Jira shadow-mirror mapping (`Won't Do` resolution → `Rejected`) should
   be in scope for this story or deferred to ABS-326.
