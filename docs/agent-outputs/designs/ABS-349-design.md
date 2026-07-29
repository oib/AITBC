# Design: ABS-349 — Merge-from-Board (Audited HITL Merge)
## Human-only merge endpoint + ticket-drawer Merge control

**Artifact version**: 2026-07-17
**Design system**: `docs/design/DESIGN_SYSTEM.md` (starter template — placeholder tokens; see §7 Deviations)
**Story**: ABS-349 · Backend S2 (be-developer) · Parent epic: ABS-230
**Depends on**: ABS-345 (Story 1 — Bitbucket `ForgeProvider` + `forge.merge` + PR Mirror)
**Spec / ADR references**:
`specs/ABS-229-agentic-backend-phase1-spec.md` §11 (human actions) ·
`specs/DRAFT-agentic-backend-vision.md` §4 ·
`adrs/agentic/ADR-A-0005-human-approval-gates.md` ·
`adrs/agentic/ADR-A-0014-no-auto-merge.md` ·
`adrs/agentic/ADR-A-0004-human-approval-boundaries.md` (human-only boundary #2)
**Produced by**: ui-ux-design agent · 2026-07-17
**Flags**: `design`, `security` (security-sensitive — merge is human-only boundary #2)

---

## §1 Scope of This Design

ABS-349 adds a **new front door to the Stage-3 HITL merge act**: a human ≥ Maintainer
triggers a PR merge from the board. The board triggers, the human decides, every action
is audited. Merge authority stays **exclusively human** — no agent/automated path may reach
the merge handler (Guardrail 1, ADR-A-0005/0014).

This design specifies:

| Area | Section |
|---|---|
| Backend merge endpoint (`POST …/items/:key/merge`) — auth gates, side-effects, status codes | §2 |
| Authorization model — role gate + merge-gate-status gate + agent-token rejection | §3 |
| Detail-endpoint extension — mirrored-PR reference so the drawer can render/trigger merge | §4 |
| Ticket-drawer **Merge** control — visibility matrix, confirmation dialog, states | §5 |
| Audit event + optional configured auto-transition | §6 |
| Design-system deviations | §7 |
| Design Acceptance Criteria (testable, DAC-numbered — the Design Test contract) | §8 |

**Out of scope** (mirrors the ticket scope fence):
- Automated or agent-triggered merges (explicitly forbidden — the guardrail this story protects).
- The `ForgeProvider` / `forge.merge` implementation itself (ABS-345 / Story 1).
- Changing which statuses count as merge-gates (reuse Phase-1 workflow config, §3.2).
- Any change to the existing S9 human write path (`transition` / `comment` / `labels`).

---

## §2 Backend Merge Endpoint

### 2.1 Route

```
POST /api/v1/projects/:project/items/:key/merge
```

**Surface constraint (Implementation constraint, ticket):** the endpoint lives on the
`/api/v1/` human-session surface — the SAME surface as the S9 write actions in
`backend/apps/server/src/routes/dashboard.ts` — and **never** on `/agent/v1/`. This is
what makes the human-session cookie the only credential that can reach it (§3.3).

- **Request body**: none required. (The PR to merge is resolved server-side from the item's
  mirrored PR — §4 — so the client cannot target an arbitrary PR.)
- **Success response**: `200` `{ ok: true, pr: <pr-id>, commit: <sha>, transitioned_to: <status|null> }`.
- **Content type**: `application/json` (matches the S9 write endpoints, which return JSON;
  the `/agent/v1/` text-plain contract does not apply to the human dashboard surface).

### 2.2 Handler control flow

```
merge(project, key):
  1. requireHuman(principal)            → 403 if role ∉ WRITER_ROLES   (§3.1)
  2. resolve projectId (org-scoped)     → 404 if no such project
  3. resolveItemId(org, project, key)   → 404 if no such item
  4. load item; assert status ∈ MERGE_GATE_STATUSES → 409 otherwise    (§3.2)
  5. resolve mirrored PR for the item   → 409 if no open PR mirrored    (§4)
  6. commit = await forge.merge(pr)     ← ABS-345 provider (Story 1)
  7. append audit event: kind=merge, actor=human, pr, commit  (§6.1)
  8. IF workflow config declares a post-merge auto-transition for this
     status → transition(actor=human, reason="auto: post-merge") (§6.2)
  9. return { ok, pr, commit, transitioned_to }
```

Steps 1–4 are pure **gate** checks and MUST run **before** any `forge.merge` side-effect
(no partial merge on a failed gate). Step 6 is the only irreversible act; steps 7–8 record
and follow it.

### 2.3 Status-code contract

| Condition | Code | Body |
|---|---|---|
| Authorized, merge-gate status, PR merges | `200` | `{ ok:true, pr, commit, transitioned_to }` |
| Session role < Maintainer (`viewer`) | `403` | `{ error:"forbidden" }` |
| Agent / orchestrator token | `403` | `{ error:"forbidden" }` (role ∉ WRITER_ROLES) |
| No valid session at all | `401` | global bearer guard (server.ts) |
| Item not in a merge-gate status | `409` | `{ error:"not_mergeable", status:<current> }` |
| No open PR mirrored for the item | `409` | `{ error:"no_pr" }` |
| `forge.merge` fails (forge rejects / conflict) | `502` | `{ error:"merge_failed", detail }` |
| No such project / item | `404` | `{ error:"not_found" }` |

The ticket AC permits `409` **or** `422` for the not-in-gate case; this design pins **409
Conflict** (the current item state conflicts with the requested act — consistent with the
existing CAS-conflict semantics on the transition endpoint). QAS-Design verifies the chosen
code against §8 DAC-6.

---

## §3 Authorization Model (security-critical, ADR-A-0004/0005/0014)

Two **independent hard gates** must BOTH hold; either failing refuses the merge.

### 3.1 Gate A — human writer role ≥ Maintainer

Reuse the existing allowlist from `dashboard.ts` verbatim — do **not** introduce a second
role list:

```ts
const WRITER_ROLES = ["admin", "maintainer"] as const; // existing, dashboard.ts:51
requireHuman(principal, reply)  // 403 if principal.role ∉ WRITER_ROLES
```

`Role = "orchestrator" | "agent" | "admin" | "viewer" | "maintainer"` (core `auth.ts`).
"≥ Maintainer" therefore resolves to `role ∈ {maintainer, admin}`. `viewer` (read-only
human) is refused; `agent` and `orchestrator` (machine roles) are refused — this is the
allowlist that makes a newly-added role denied-by-default (ABS-241 security posture).

### 3.2 Gate B — item in a human-merge-gate status

```ts
const MERGE_GATE_STATUSES = ["Ready for Merge", "Ready for Epic Acceptance"] as const;
```

Both are `class: resting`, human-owned merge gates in
`backend/packages/core/src/workflows/statuses.yaml` (ADR-A-0004/0005 annotations there).
The set is derived from the Phase-1 workflow config, **not** hard-coded policy invented here
— which statuses count as merge-gates is out of scope to change (ticket scope fence).

### 3.3 Gate enforcement is server-side and authoritative

The drawer hides the Merge control when the gates do not hold (§5), but that is a
**convenience, not the security boundary**. The endpoint re-checks both gates on every
request (§2.2 steps 1–4). A hand-crafted `POST …/merge` with an agent token, or against an
item in `In Progress`, is refused by the handler regardless of any client. This is the
explicit guardrail test (ticket AC #5, §8 DAC-9).

**No agent invocation path exists.** There is no `/agent/v1/**/merge` route; the agent
route module (`items.ts`) registers no merge op. The only code path to `forge.merge` from an
HTTP surface is this human-session handler.

---

## §4 Detail-Endpoint Extension — mirrored-PR reference

To render and trigger the Merge control the drawer needs (a) the item status (already in the
detail payload) and (b) a reference to the item's open PR. Story 1 (ABS-345) introduces the
PR Mirror; this story surfaces it read-only on the existing detail endpoint
(`GET /api/v1/projects/:project/items/:key`):

```jsonc
{
  "frontmatter": { … , "status": "Ready for Merge" },
  "body": "…",
  "comments": [ … ],
  "allowed_transitions": [ … ],
  "pr": { "id": "42", "url": "https://…", "state": "open" }   // NEW — null when none mirrored
}
```

- `pr` is `null` when no PR is mirrored for the item → the drawer shows no Merge control and
  the endpoint returns `409 no_pr` if called anyway.
- `pr` is **read-only context**; the client never sends a PR id to the merge endpoint (§2.1).
- The `TicketDetail` type (`backend/apps/web/src/types.ts`) gains an optional `pr` field.

---

## §5 Ticket-Drawer Merge Control

The control lives in the `Actions` panel of `TicketDrawer.tsx`
(`backend/apps/web/src/components/`), a new `fieldset` alongside Transition / Comment /
Labels, styled consistently with them (`data-testid="actions"`).

### 5.1 Visibility matrix (ticket AC #4 — the 4-case matrix)

The Merge control renders **iff** `role ∈ WRITER_ROLES` **AND**
`status ∈ MERGE_GATE_STATUSES` (and a `pr` is present). Session role comes from the
`whoami()` session (`api.ts`), status from `detail.frontmatter.status`.

| # | Session role | Item status | Merge control |
|---|---|---|---|
| 1 | maintainer/admin | merge-gate | **shown** (enabled) |
| 2 | maintainer/admin | non-gate | hidden |
| 3 | viewer | merge-gate | hidden |
| 4 | viewer | non-gate | hidden |

The control is a `fieldset.action-merge` with `data-testid="action-merge"`; QAS-Design
asserts presence/absence per cell (§8 DAC-8).

### 5.2 Component anatomy & tokens

| Element | Design-system component | Token(s) |
|---|---|---|
| Merge trigger button | `Button` — **primary** variant | `color.primary`, `spacing.md` padding, `font.size.md` |
| Confirmation dialog | `Dialog` — **confirmation** variant (focus-trapped, ESC closes) | `color.surface` panel, `spacing.lg` section gap |
| Confirm button (in dialog) | `Button` — **destructive** variant (irreversible act) | `color.error` |
| Cancel button (in dialog) | `Button` — **secondary** variant | `color.secondary` |
| Post-merge success line | inline status text | `color.success`, `font.size.sm` |
| Failure line | `role="alert"` inline text (reuse `.err`) | `color.error`, `font.size.sm` |

Merge is **consequential and irreversible**, so it is **two-step**: the primary Merge button
opens a confirmation `Dialog` ("Merge PR #42 into the integration branch? This cannot be
undone."). Confirm (destructive) invokes the endpoint; Cancel dismisses. This matches the
design-system `Dialog/confirmation` contract (focus-trapped, ESC to close) and the existing
CAS-conflict `role="alert"` pattern in the drawer.

### 5.3 States

| State | Trigger | UI |
|---|---|---|
| idle | control shown | primary **Merge** button enabled |
| confirming | Merge clicked | confirmation `Dialog` open, focus on Cancel |
| busy | Confirm clicked | dialog buttons + fieldset `disabled` (reuse `busy` pattern, `run()` helper) |
| success | `200` | dialog closes; success line "Merged PR #42 @ `<sha>`"; drawer reloads (`onChanged`) |
| refused (403/409) | gate failed server-side | `role="alert"` line "Merge not permitted (`<status>`)"; no state change |
| failed (502) | forge rejected | `role="alert"` line "Merge failed — see PR"; no auto-transition |

The busy/`run()`/`onChanged` machinery already exists in `Actions` (dashboard write pattern);
the Merge action reuses it — one new `api.humanMerge(project, key)` helper posting to §2.1.

### 5.4 API client helper

```ts
// backend/apps/web/src/api.ts — new, mirrors humanTransition/humanComment
export function humanMerge(project: string, key: string): Promise<WriteResult> {
  return sendJSON("POST", `${itemUrl(project, key)}/merge`, {});
}
```

---

## §6 Audit + Optional Auto-Transition

### 6.1 Audit event (ticket AC #2)

On a successful `forge.merge`, append an event to the event log through the **same** event
path the S9 writes use (core event append + `bus.publish`), carrying:

- `kind: "merge"`
- `actor: "human"` (the `HUMAN_ACTOR` constant — the human-boundary audit trail)
- `pr`: the merged PR id
- `commit`: the merge commit SHA returned by `forge.merge`

This is the immutable proof that a human ≥ Maintainer performed the merge (ADR-A-0004 audit
requirement). The dashboard `EventFeed` surfaces it like any other event.

### 6.2 Optional configured auto-transition

If — and only if — the Phase-1 workflow config declares a post-merge target for the item's
current merge-gate status, the handler performs that transition (`actor=human`,
`reason="auto: post-merge"`) after the audit event. Reuse the existing workflow-config
resolution (`resolveWorkflowFor` / transition engine); introduce **no** new transition
logic (ADR-A-0010 minimal-change). When no post-merge target is configured,
`transitioned_to` is `null` and the item rests at its gate. The auto-transition is a
side-effect the integration test asserts alongside the merge call + audit event (§8 DAC-7).

---

## §7 Design-System Deviations

### Deviation 1 — Visual design tokens are unresolved (pre-existing; same as ABS-234/238)

`docs/design/DESIGN_SYSTEM.md` is a starter template: every `{{PLACEHOLDER}}` token
(`color.primary`, `spacing.md`, breakpoint widths, `{{UI_LIBRARY}}`, WCAG level) is
unresolved. This story adds a real UI surface (the Merge control), so it **references
concrete design-system components** (`Button/primary`, `Button/destructive`,
`Dialog/confirmation`) and tokens by name (§5.2) — but their concrete VALUES cannot be
verified until the template is resolved.

**Required action** (unchanged from ABS-234 §7 / ABS-238 §8): the System Architect resolves
the template tokens before contrast/spacing values can be checked numerically. Until then,
§8 DAC-2/DAC-3 are verified **structurally** (correct component + token *name* used) and
their numeric thresholds (contrast ≥ 4.5:1, breakpoint widths) are verified once values land
— QAS-Design records them as blocked-on-tokens, not failed.

### Deviation 2 — `Dialog/confirmation` is used for an irreversible action (design intent, no new variant)

The confirmation dialog uses the existing `Dialog` component's `confirmation` variant — no
new component variant is invented. The destructive-framed Confirm button uses the existing
`Button/destructive` variant. No deviation from the component inventory; noted only to record
that merge deliberately requires the confirmation step (not a bare button).

---

## §8 Design Acceptance Criteria (ABS-349)

> These ACs are the **Design Test contract** (QAS-Design seat). Each is verifiable against
> the running ABS-349 implementation without the designer present. Concrete tokens, status
> codes, and explicit steps only — no "looks good".

**Design artifact**: `docs/agent-outputs/designs/ABS-349-design.md`
**Design system**: `docs/design/DESIGN_SYSTEM.md` (template, placeholder tokens — see §7)

### Schema Conformance

- [ ] **DAC-1 — Merge endpoint surface**: A `POST` route exists at
  `/api/v1/projects/:project/items/:key/merge` and **no** merge route exists under
  `/agent/v1/`. Verify: `git grep -n "/merge" backend/apps/server/src/routes/` shows the
  route only in the dashboard (human) route module, never in `items.ts` (agent module).

- [ ] **DAC-2 — Merge trigger uses `Button/primary`; confirm uses `Button/destructive`**:
  The drawer Merge control renders a primary-variant `Button` (opens the dialog) and the
  confirmation `Dialog` renders a destructive-variant Confirm button + secondary Cancel,
  per `docs/design/DESIGN_SYSTEM.md` § Components. Verify: the rendered elements carry the
  design-system component classes/variants (structural check — numeric token values
  blocked on Deviation 1).

- [ ] **DAC-3 — Confirmation dialog matches `Dialog/confirmation`**: Triggering Merge opens a
  focus-trapped dialog that closes on `Escape` and on Cancel, naming the PR id in its prompt
  ("Merge PR #<id> …"). Verify: component/e2e test asserts the dialog opens, ESC closes it
  with no merge call fired, and Cancel closes it with no merge call fired.

### Accessibility

- [ ] **DAC-4 — Labels, focus, alert semantics**: The Merge button has an accessible name
  ("Merge"); on open, focus moves into the dialog and returns to the trigger on close;
  the failure line uses `role="alert"` (reusing the drawer's `.err` alert pattern). Verify:
  keyboard-only walkthrough completes the merge flow (Tab → Enter to open, Tab to Confirm,
  Enter) with a visible focus indicator at each step.

- [ ] **DAC-5 — Contrast (blocked on tokens, then numeric)**: Merge button text/background
  ≥ 4.5:1; destructive Confirm button ≥ 4.5:1; success/failure lines ≥ 4.5:1 (body). Verify:
  once `color.primary`/`color.error`/`color.success`/`color.text` are resolved (Deviation 1),
  compute the ratios; until then record as blocked-on-tokens (not failed).

### Authorization / Security (the guardrail contract — mandatory)

- [ ] **DAC-6 — Endpoint refuses non-Maintainer and non-gate status independently**:
  (a) A `viewer`-session `POST …/merge` returns `403`. (b) A `maintainer`-session
  `POST …/merge` against an item whose status ∉ {Ready for Merge, Ready for Epic Acceptance}
  returns `409` with `{ error:"not_mergeable" }`. Both refusals are asserted by separate
  tests, and in each refusal `forge.merge` is **not** called (spy asserts zero invocations).

- [ ] **DAC-7 — Authorized merge produces all three side-effects**: A maintainer merge on a
  merge-gate item with an open mirrored PR: (1) calls `forge.merge` once with the item's PR,
  (2) appends an event `kind=merge, actor=human, pr=<id>, commit=<sha>` to the event log,
  and (3) executes the configured post-merge auto-transition (when the workflow config
  declares one). Verify: one integration test asserts all three; a second variant with **no**
  configured post-merge target asserts `transitioned_to === null` and no transition event.

- [ ] **DAC-8 — Drawer visibility matrix (4 cases)**: The Merge control is present ONLY in
  cell 1 of §5.1 and absent in cells 2–4. Verify: component/e2e test drives all four
  (role × status) combinations and asserts `queryByTestId("action-merge")` is non-null in
  cell 1 and null in cells 2, 3, 4.

- [ ] **DAC-9 — No agent/automated path reaches the merge handler**: An **agent** token
  (role `agent`) and an **orchestrator** token both receive `403` on `POST …/merge`, and no
  route under `/agent/v1/` invokes `forge.merge`. Verify: a test asserts the agent-token 403
  AND `git grep -n "forge.merge\|\.merge(" backend/apps/server/src/routes/items.ts` returns
  nothing (Guardrail 1, ADR-A-0005/0014).

### Responsive / Integration

- [ ] **DAC-10 — Drawer usable at each breakpoint (blocked on widths, then behaviour)**: The
  Merge control and its confirmation dialog remain fully operable within the drawer at
  `mobile` / `tablet` / `desktop` breakpoints (no horizontal overflow, dialog centered and
  focus-trapped). Verify: once breakpoint widths are resolved (Deviation 1), drive the flow
  at each width; until then record as blocked-on-tokens.

- [ ] **DAC-11 — Existing dashboard tests unbroken**: All tests in
  `backend/apps/server/test/dashboard-routes.test.ts` and the web component tests pass with
  no new failures after adding the merge endpoint, the detail `pr` field, and the drawer
  control. Verify: the server + web test suites exit 0.

### Key User Flow

- [ ] **DAC-12 — Human merge flow in ≤ 4 steps**: A maintainer can merge a PR from the board
  in ≤ 4 interactions: (1) open the ticket drawer for a merge-gate item, (2) click **Merge**,
  (3) confirm in the dialog, (4) observe the success line + reloaded drawer showing the
  post-merge status (or the resting gate when no auto-transition is configured). Verify:
  e2e walkthrough completes the four steps and asserts the merge event appears in the
  `EventFeed`.

---

## §9 Summary Table

| Design area | Driven by artefact | AC |
|---|---|---|
| Merge endpoint on `/api/v1/`, none on `/agent/v1/` | §2.1, §3.3 | DAC-1, DAC-9 |
| `Button/primary` + `Button/destructive` + `Dialog/confirmation` | §5.2 | DAC-2, DAC-3 |
| Accessibility (labels/focus/alert/contrast) | §5.2–5.3 | DAC-4, DAC-5 |
| Role gate (≥ Maintainer) + status gate, independent refusals | §3.1, §3.2, §2.3 | DAC-6 |
| Audit event + optional auto-transition (3 side-effects) | §6.1, §6.2 | DAC-7 |
| Drawer visibility matrix (4 cases) | §5.1 | DAC-8 |
| Agent/automated path refused (guardrail) | §3.3 | DAC-9 |
| Responsive drawer + dialog | §5 | DAC-10 |
| Existing tests unbroken | §2, §4, §5 | DAC-11 |
| ≤ 4-step human merge flow | §5.3 | DAC-12 |

**Design-system deviations**: 2 (see §7) — Deviation 1 (unresolved template tokens,
pre-existing across ABS-234/238; blocks numeric contrast/breakpoint checks) and Deviation 2
(intentional use of `Dialog/confirmation` for the irreversible act; no new variant). Both
reported to the System Architect; neither invents an ad-hoc style.

**Next**: Ready for Development — be-developer implements the `/api/v1/**/merge` endpoint
(gates + audit + optional auto-transition), the detail-endpoint `pr` field, the drawer Merge
control, and the `humanMerge` API helper, invoking `forge.merge` from ABS-345. QAS-Design
verifies DAC-1 through DAC-12 against the running implementation.
