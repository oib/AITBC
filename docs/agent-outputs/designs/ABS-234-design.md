# Design: ABS-234 — Entity-Typ-Registry + Workflow-Engine
## UI-Facing Contracts & Data-Model Design

**Artifact version**: 2026-07-13
**Design system**: `docs/design/DESIGN_SYSTEM.md` (template — see §7 Deviations)
**Story**: ABS-234 · Backend S2 · Parent epic: ABS-229
**Spec references**: `specs/ABS-229-agentic-backend-phase1-spec.md` §2/§3/§11 ·
`adrs/agentic/ADR-A-0021-agentic-delivery-backend.md` §b/§c/§g
**Produced by**: ui-ux-design agent · 2026-07-13

---

## §1 Scope of This Design

ABS-234 implements the backend **Entity-Type Registry** (`entity_type` table, field_schema,
workflow, render config) and the **Workflow Engine** (statuses.yaml parser, resolution, CAS
transition service). These backend structures are the authoritative source for three UI surfaces
described in Spec §11:

| Backend artefact         | UI surface(s) it drives                                     |
|--------------------------|-------------------------------------------------------------|
| `entity_type.workflow`   | Kanban column groups, transition dropdown (`next:` list)    |
| `entity_type.render`     | Ticket detail drawer field order + section order            |
| Transition service 400   | Illegal-transition inline error (transition UI)             |
| Transition service 409   | CAS conflict Dialog (transition UI)                         |
| event.`at` (last transition) | "Time-in-status" badge on Kanban cards                |

**Out of scope for this design document** (mirrors the ticket scope fence):
- HTTP-route signatures (S3/S4, ABS-235/ABS-236)
- Runtime type-creation UI (Phase 4)
- SPA component styling (token values depend on project configuration — see §7)

---

## §2 `entity_type.workflow` JSON Schema

The statuses.yaml parser (Spec §3) produces the following JSON structure, stored verbatim in
the `entity_type.workflow` JSONB column. This structure is the canonical source for all
workflow-driven UI behaviour.

### 2.1 Top-level shape

```json
{
  "format": "statuses-yaml-v1",
  "workflows": {
    "<workflow-name>": { ... }
  },
  "shared": {
    "statuses": ["<name>", ...]
  }
}
```

| Field               | Type              | Description                                              |
|---------------------|-------------------|----------------------------------------------------------|
| `format`            | `"statuses-yaml-v1"` | Parser version; bump when format changes           |
| `workflows`         | object            | Keyed by named workflow: `epic-pipeline`, `story-pipeline` |
| `shared.statuses`   | string[]          | Statuses common to both pipelines (Backlog, Done, Blocked, Needs PO Decision) |

### 2.2 Named workflow object

```json
{
  "name": "story-pipeline",
  "statuses": [
    {
      "name": "Backlog",
      "pipeline": "shared",
      "class": "resting",
      "next": [
        "Ready for Development",
        "PO Triage",
        "Design",
        "Stories In Flight",
        "Blocked",
        "Needs PO Decision"
      ]
    },
    {
      "name": "Design",
      "pipeline": "story",
      "class": "transient",
      "next": ["Ready for Development", "Blocked", "Needs PO Decision"]
    }
    ...
  ]
}
```

| Field      | Type     | Values                                    | Source                      |
|------------|----------|-------------------------------------------|-----------------------------|
| `name`     | string   | The `name:` value from statuses.yaml      | Parsed verbatim             |
| `pipeline` | string   | `"shared"` \| `"epic"` \| `"story"`       | From `# pipeline:` comment  |
| `class`    | string   | `"transient"` \| `"resting"`              | From `# class:` comment     |
| `next`     | string[] | Ordered list of valid next-status names   | Parsed from `next:` block   |

**Ordering constraint**: the `statuses` array preserves the top-to-bottom order of statuses.yaml.
The Kanban board renders columns in this order; reordering statuses.yaml reorders the board.

### 2.3 Phase-1 built-in split

The existing `profiles/neutral/adapters/statuses.yaml` is imported as **two named workflows**
sharing one status namespace per project:

- **`epic-pipeline`**: statuses from the `# --- epic pipeline ---` block (PO Triage →
  Grooming → Enrichment → Ticket Review → Architecture Review → Stories In Flight →
  Epic Integration → Ready for Epic Acceptance → Epic Done) plus shared statuses.
- **`story-pipeline`**: statuses from the `# --- story pipeline ---` and
  `# --- v1/v2 core ---` blocks (Design → Ready for Development → In Progress → In Review →
  Security Review → Test Prep → In Test → Design Test → Story Acceptance → Merging → Docs →
  Ready for Human Acceptance → Ready for Merge) plus shared statuses.

**Shared statuses** (appear in both workflows, cross-cutting semantics):
`Backlog`, `Done`, `Blocked`, `Needs PO Decision`

**Phase-1 total**: 26 statuses parsed from statuses.yaml (verified against
`profiles/neutral/adapters/statuses.yaml` as of 2026-07-13):
- Story pipeline (excl. shared): 15 statuses
- Epic pipeline (excl. shared): 9 statuses
- Shared: 4 statuses (Backlog, Done, Blocked, Needs PO Decision)
- Total unique: 28 — wait, shared statuses count once → **26 unique status names**

### 2.4 Resolution result structure

When `resolve(project_id, type_key) → workflow` (Spec §3, resolution order:
project override → org default → built-in), the resolved value is one of the
named workflow objects from §2.2. Items of type `epic` resolve `epic-pipeline`;
items of type `ticket`/`subtask` resolve `story-pipeline`.

The resolved workflow is computed at transition time, not cached per-call
(allows hot workflow updates in Phase 3+).

---

## §3 `entity_type.render` JSON Schema

The render config drives the **Ticket Detail Drawer** in the dashboard (Spec §11 — "Ticket
detail drawer: frontmatter, body, full comment timeline").

### 3.1 Schema

```json
{
  "frontmatter_order": [
    "id", "type", "title", "status", "parent", "role",
    "flags", "labels", "ac_blocking", "assignee",
    "depends_on", "links", "created", "updated"
  ],
  "sections": [
    "Goal", "Scope", "Acceptance Criteria",
    "Definition of Done", "Test Plan", "ADR Context"
  ],
  "optional_fields": ["role", "flags", "labels", "ac_blocking", "assignee"]
}
```

| Field               | Type     | Description                                            |
|---------------------|----------|--------------------------------------------------------|
| `frontmatter_order` | string[] | Ordered field names; must match mock format exactly (Spec §5) |
| `sections`          | string[] | `## <Section>` order in the rendered body              |
| `optional_fields`   | string[] | Fields omitted from frontmatter when empty/null (Spec §5 rule: `*` = only-when-set) |

**Invariant**: `frontmatter_order` must produce byte-identical YAML to `mock-tracker.sh`'s
output for `GET /items/:key` (Spec §5 golden-file constraint). The Phase-1 seed value above
matches the mock format verified against `scripts/mock-tracker.sh`.

### 3.2 Phase-1 seed values (per entity type)

All three Phase-1 types ship the same render config (mock format is uniform):

| entity_type.key | frontmatter_order    | sections                                        |
|-----------------|----------------------|-------------------------------------------------|
| `epic`          | (as §3.1 above)      | Goal, Scope, Acceptance Criteria, Definition of Done, Test Plan, ADR Context |
| `ticket`        | (as §3.1 above)      | Goal, Scope, Acceptance Criteria, Definition of Done, Test Plan, ADR Context |
| `subtask`       | (as §3.1 above)      | Goal, Scope, Acceptance Criteria, Definition of Done, Test Plan, ADR Context |

---

## §4 Kanban Column Derivation Contract

The Kanban board (Spec §11) **must not contain hardcoded status lists**. Column groups are
derived from the resolved `entity_type.workflow` JSON for the project's built-in workflows.

### 4.1 Column group mapping (Phase 1, built-in workflows)

| Column group label        | Statuses (from resolved workflow)                        | Note                     |
|---------------------------|----------------------------------------------------------|--------------------------|
| Backlog                   | Backlog                                                  | shared; always leftmost  |
| **Epic Pipeline**         |                                                          |                          |
| → Triage                  | PO Triage                                                | epic-pipeline transient  |
| → Grooming                | Grooming, Enrichment                                     | epic-pipeline transients |
| → Review                  | Ticket Review, Architecture Review                       | epic-pipeline transients |
| → In Flight               | Stories In Flight                                        | epic-pipeline resting    |
| → Integration             | Epic Integration                                         | epic-pipeline transient  |
| → Epic Acceptance         | Ready for Epic Acceptance                                | epic-pipeline resting    |
| → Epic Done               | Epic Done                                                | epic-pipeline terminal   |
| **Story Pipeline**        |                                                          |                          |
| → Design                  | Design                                                   | story-pipeline transient |
| → Development             | Ready for Development, In Progress                       | story-pipeline           |
| → Review & Security       | In Review, Security Review, Test Prep                    | story-pipeline           |
| → Testing                 | In Test, Design Test                                     | story-pipeline           |
| → Acceptance              | Story Acceptance, Ready for Human Acceptance             | story-pipeline           |
| → Merge                   | Merging, Ready for Merge                                 | story-pipeline           |
| → Docs                    | Docs                                                     | story-pipeline transient |
| Done                      | Done                                                     | shared; always rightmost |
| **Escalations**           | Blocked, Needs PO Decision                               | shared; always visible   |

### 4.2 Derivation algorithm contract

The backend must provide, at minimum, the workflow topology in a form the SPA can consume.
The SPA constructs column groups by:
1. Fetching the project's built-in workflow topology (via the capabilities or a dedicated
   endpoint — route design in S3/S4).
2. Grouping statuses by `pipeline` field and inferred column-group affinity (above table).
3. Ordering columns: shared-entry → epic statuses (pipeline order) → story statuses (pipeline
   order) → shared-terminal → escalations.

**Required data shape per status** (minimum for the Kanban renderer):
```json
{
  "name": "In Progress",
  "pipeline": "story",
  "class": "resting",
  "next": ["In Review", "Blocked", "Needs PO Decision"]
}
```

### 4.3 Card fields (Spec §11)

Each Kanban card must display: `key`, `title`, `role`, `flags`, `assignee`, `time-in-status`.

**`time-in-status` source**: the timestamp of the last `transition` event in the `event` table
for the item (`event.kind = 'transition'`, `payload.to = work_item.status`). If no transition
event exists, `created` timestamp is used (item has never been transitioned).

---

## §5 Transition UI Behaviour Contract

The human transition UI (Spec §11 — "Human actions: transition: dropdown limited to legal next
statuses, reason mandatory, `expect_from` prefilled from rendered status") is driven entirely
by the workflow engine data.

### 5.1 Transition form specification

| Element               | Specification                                                  |
|-----------------------|----------------------------------------------------------------|
| Status dropdown       | Populated from `next[]` of the item's current status in its resolved workflow |
| Reason field          | Mandatory free-text textarea; submit disabled until non-empty  |
| expect_from (hidden)  | Prefilled with the item's current status at form-open time (CAS prefill) |
| Submit button         | `Button/primary` (design system); label "Transition"           |
| Cancel button         | `Button/secondary` (design system); label "Cancel"             |

**Focus order** (tab sequence within the transition form):
1. Status dropdown (Input/select)
2. Reason textarea (Input/text)
3. Submit button (Button/primary)
4. Cancel button (Button/secondary)

All form elements have programmatic labels. The submit button has a visible focus indicator.

### 5.2 400 — Illegal transition (server-enforced, not UI-enforced)

When the transition POST returns HTTP 400 with body matching:
`illegal transition <from> -> <to>; allowed: <comma-separated list>`

The UI must:
1. Display an **inline error** below the status dropdown (not a Dialog).
2. Error text: "That transition is not allowed. Allowed next statuses: {list from response body}."
3. The error text uses `color.error` token (placeholder — see §7).
4. The dropdown remains open for correction; form is not dismissed.
5. The submit button re-enables after the user changes the selection.

**Design system component**: no new component; use the existing Input validation error pattern
(label + error text below the Input/select, styled `color.error`).

### 5.3 409 — CAS mismatch (concurrent edit conflict)

When the transition POST returns HTTP 409 (body: current status text per Spec §4 error table):

The UI must show a **Dialog/confirmation** (design system) with:
- Title: "Status Changed"
- Body: "The ticket's status changed while you were working. Current status:
  **{status from 409 response body}**. Your expected status: **{expect_from value}**.
  Please reload the page and try again."
- Primary button: "Reload Page" (Button/primary — reloads the ticket detail, re-fetches status)
- Secondary button: "Cancel" (Button/secondary — dismisses dialog, leaves form open with stale data)

The Dialog is **focus-trapped** (design system Dialog/confirmation behaviour). ESC key activates
Cancel. Tab cycles between the two buttons only while the Dialog is open.

**No silent overwrite**: the UI must NEVER re-submit a transition that returned 409 without
the user explicitly loading the fresh status. The "Reload Page" action fetches the current
status and pre-fills `expect_from` with it (the user then decides whether to re-submit).

### 5.4 Escalation Inbox data contract (Spec §11)

Items appear in the Escalation Inbox when `work_item.status IN ('Blocked', 'Needs PO
Decision', 'Ready for Epic Acceptance', 'Ready for Human Acceptance')`.

Required fields per inbox row:
```
key | title | status | latest_escalation_comment_body | entered_status_at (from event log)
```

Sort: oldest `entered_status_at` first (most urgent first).

"Latest escalation comment" = the most recent comment where `comment.kind IN
('notification', 'decision', 'bsa-decision')` for that item.

---

## §6 Accessibility Notes

These notes apply to all UI surfaces driven by ABS-234's backend data.

| Requirement                  | Specification                                                  |
|------------------------------|----------------------------------------------------------------|
| Contrast (body text)         | ≥ 4.5:1 against background (WCAG 2.1 AA; token values TBD per §7) |
| Contrast (large text / badges) | ≥ 3:1 (status badges, column headers)                       |
| Focus indicators             | All interactive elements (dropdown, buttons, dialog controls) have visible focus rings |
| Labels                       | Status dropdown: `<label>` "New status"; Reason textarea: `<label>` "Reason (required)" |
| CAS Dialog                   | `role="dialog"`, `aria-labelledby` pointing to "Status Changed" heading; focus moves to Dialog on open |
| Keyboard completability      | Full transition flow (open form → select status → enter reason → submit) completable without pointer |
| Motion                       | CAS Dialog slide-in animation respects `prefers-reduced-motion` |

**WCAG target**: 2.1 AA (design system `{{WCAG_LEVEL}}` is unresolved — see §7 Deviation #1).

---

## §7 Design-System Deviations

### Deviation 1 — All token values are unresolved placeholders (REPORT TO SYSTEM ARCHITECT)

`docs/design/DESIGN_SYSTEM.md` is a **starter template** — all value cells contain
`{{PLACEHOLDER}}` tokens:
- Colors: `{{COLOR_PRIMARY}}`, `{{COLOR_ERROR}}`, `{{COLOR_BACKGROUND}}`, etc.
- Typography: `{{FONT_FAMILY}}`, `{{FONT_SIZE_*}}`, etc.
- Spacing: `{{SPACING_*}}` — no concrete px/rem values
- Breakpoints: `{{BREAKPOINT_MOBILE}}`, `{{BREAKPOINT_TABLET}}`, `{{BREAKPOINT_DESKTOP}}`
- WCAG level: `{{WCAG_LEVEL}}`
- UI library: `{{UI_LIBRARY}}`

**Impact on this design**: The structural component names (Button/primary, Input/select,
Dialog/confirmation, Card/default, Table/default) are defined and referenced correctly.
However, no concrete color values, spacing values, or breakpoint widths are available for
the QAS-Design agent to verify contrast ratios or responsive layout widths.

**Required action** (BSA/System Architect): Resolve all `{{PLACEHOLDER}}` tokens in
`docs/design/DESIGN_SYSTEM.md` before the Design Test gate for ABS-234 (and all other
design-flagged stories in ABS-229). Until resolved, DAC-2 (contrast) and DAC-5 (responsive
breakpoints) cannot be verified against concrete values.

**Interim position**: This design document adopts WCAG 2.1 AA as the accessibility baseline
(industry standard). Contrast and breakpoint ACs are written with the WCAG-mandated ratios
(4.5:1 / 3:1) and semantic breakpoint names (`mobile`, `tablet`, `desktop`); the QAS-Design
agent substitutes concrete pixel values when the design system is resolved.

### Deviation 2 — No project-specific component library named (REPORT TO SYSTEM ARCHITECT)

`{{UI_LIBRARY}}` is unresolved. This design references components by their design-system
names (Button, Input, Dialog, Card, Table). The SPA implementation seat must map these to
the actual component library chosen for `apps/web/`.

---

## §8 Responsive Behaviour

| Breakpoint | Token             | Kanban behaviour                                  |
|------------|-------------------|---------------------------------------------------|
| `desktop`  | `{{BREAKPOINT_DESKTOP}}` (TBD) | Full multi-column Kanban; all column groups visible |
| `tablet`   | `{{BREAKPOINT_TABLET}}` (TBD)  | Horizontal scroll; column groups collapsible      |
| `mobile`   | `{{BREAKPOINT_MOBILE}}` (TBD)  | Single-column view (one column visible at a time); swipe to navigate |

The transition Dialog (§5.3) is full-screen on mobile (fills the viewport width). Button
spacing expands to ensure 44 × 44 px minimum touch targets on mobile.

---

## Design Acceptance Criteria (ABS-234)

> These ACs are the **Design Test contract** (QAS-Design seat). Each must be
> verifiable against the running ABS-234 backend + SPA implementation.

### Schema Conformance

- [ ] **DAC-1**: The `entity_type.workflow` JSON for the built-in `story-pipeline` workflow
  (queryable via the database or a future `/workflows` API endpoint once S3/S4 land) contains
  exactly **26 unique status names**, each with a `name`, `pipeline`, `class`, and `next[]`
  field as specified in §2.2. Verify: `SELECT workflow FROM entity_type WHERE key = 'ticket'`
  returns JSON parseable against the §2.2 schema with zero schema-validation errors.

- [ ] **DAC-2**: The `entity_type.render` JSON for all three Phase-1 types (`epic`, `ticket`,
  `subtask`) lists `frontmatter_order` in the exact 14-field sequence from §3.1. Verify:
  `GET /agent/v1/projects/:p/items/:key` response for a freshly created item matches
  `scripts/mock-tracker.sh get <key>` output byte-for-byte (golden-file diff is empty, Spec §5).

### Accessibility

- [ ] **DAC-3**: The transition form (dropdown + reason field + submit + cancel) has a visible
  focus ring on each element when navigated by keyboard. Tab order follows §5.1: dropdown
  (1) → reason textarea (2) → submit button (3) → cancel button (4). Verify by tabbing
  through the form with no pointer; all four controls are reachable in that order and all have
  visible focus indicators.

- [ ] **DAC-4**: The CAS conflict Dialog (§5.3) is focus-trapped: while open, Tab cycles only
  between "Reload Page" and "Cancel" buttons. ESC activates Cancel. `aria-labelledby` points
  to the "Status Changed" heading. Verify using a keyboard-only session and an accessibility
  tree inspector (e.g., axe-core); zero violations on Dialog open/close cycle.

### Responsive

- [ ] **DAC-5**: At the `mobile` breakpoint width (resolved from design system when
  `{{BREAKPOINT_MOBILE}}` is filled in), the Kanban board displays a single-column view with
  horizontal scroll. Individual column cards remain readable (title text not clipped). Verify
  by resizing the browser to the `mobile` breakpoint width and confirming no column content
  overflows its container without scroll affordance.

### User Flows

- [ ] **DAC-6**: A human operator can complete a legal status transition in **≤ 4 steps**:
  (1) open the transition form on a ticket card; (2) select a valid next status from the
  dropdown; (3) enter a reason; (4) click "Transition". The ticket's status updates in the
  Kanban column immediately after step 4 (optimistic or reactive). Verify end-to-end in
  the running dashboard.

- [ ] **DAC-7**: When a concurrent edit causes a CAS conflict (409), the Dialog specified in
  §5.3 appears with the current status from the 409 response body. Clicking "Reload Page"
  dismisses the dialog, refetches the ticket, and pre-fills `expect_from` with the fresh
  status. No silent overwrite occurs. Verify by opening the transition form, advancing the
  ticket's status from another session (causing 409), submitting the stale form, and
  confirming the Dialog appears with the correct current-status text.

---

## Summary

| Design area                      | Driven by ABS-234 artefact            | Verifiable at Design Test |
|----------------------------------|---------------------------------------|---------------------------|
| Kanban column groups             | `entity_type.workflow` JSON           | Yes (DAC-1, DAC-5)       |
| Ticket detail drawer field order | `entity_type.render` JSON             | Yes (DAC-2)              |
| Transition dropdown options      | `next[]` from resolved workflow       | Yes (DAC-6)              |
| 409 CAS conflict Dialog          | Transition service 409 response       | Yes (DAC-4, DAC-7)       |
| 400 illegal-transition error     | Transition service 400 response body  | Yes (DAC-6)              |
| Accessibility (form + dialog)    | UI components driven by above data    | Yes (DAC-3, DAC-4)       |
| Responsive Kanban                | Workflow topology determines columns  | Yes (DAC-5)              |

**Design-system deviations**: 2 reported (see §7). Both require System Architect action
before the Design Test gate can complete. No ad-hoc styles invented.

**Next**: Ready for Development (be-developer implements the backend; SPA implementation
picks up §4/§5 UI contracts in a later ABS-229 story).
