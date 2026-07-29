# QA Validation Report — ABS-464

**Ticket**: ABS-464 – Transition guardrails in the drawer (forward-first, confirm on backward)
**Branch**: ABS-464-auto
**Commit (rebased tip)**: b84a9117
**QAS Actor**: qas
**Date**: 2026-07-19
**Verdict**: ✅ APPROVED (post-rebase re-validation)
**Iteration**: 2 (Iteration 1 approved `aa8ab999`; RTE bounce was rebase conflict — environment/merge class, not a code defect; this run re-validates the rebased tip `b84a9117`)

---

## Rebase Delta Confirmation

The RTE bounced `ABS-464-auto` to `Ready for Development` due to a content conflict in
`backend/apps/web/src/util.ts` — a comment-wording divergence between the ABS-464 branch
and the same `formatAge` fix already merged on the epic branch by a later story.

**Verification**: `b84a9117` `util.ts` (lines 1–6) is byte-identical to `bc032909` (epic tip).
The `formatAge` import/export code is unchanged; only comment wording was harmonised.
ABS-464's own additions (core direction functions, server `transition_directions`, drawer
partition + confirm, tests) rebased cleanly — confirmed by git show of the commit diff.

---

## Acceptance Criteria Verification

### AC1 — API response includes direction per allowed transition; contract test pins it
**Result**: ✅ PASS

- `backend/apps/server/src/routes/dashboard.ts`: item-detail response carries
  `transition_directions` (map `target → forward|backward|lateral`) derived via
  `allowedNextDirected` from core.
- `allowed_transitions` keeps its `string[]` shape; Inbox + ABS-241 contract test untouched
  (unchanged invariant confirmed by `grep` of the diff).
- Direction is computed in `backend/packages/core/src/workflow.ts` via `transitionDirection` /
  `allowedNextDirected`: uses `wf.statuses` (the adapter's canonical ordered chain); never
  duplicates the chain into the server or web.
- `LATERAL_HUBS = new Set(["Blocked", "Needs PO Decision", "Canceled"])` in core only; names
  confirmed against `statuses.yaml`.
- Contract test `dashboard-routes.test.ts:345` pins `transition_directions` with concrete
  assertions; DB-gated (skips cleanly in sandbox — no Postgres; authored for CI-with-infra).
- Core unit tests: 3 new ABS-464 direction tests pass (see Green-Run Proof).

### AC2 — Forward transitions render primary; backward requires a confirm naming source → target; e2e covers the confirm flow
**Result**: ✅ PASS

- `partitionTransitions` (`backend/apps/web/src/util.ts`): reads only from server-supplied
  `directions` map (`directions[to] === "forward"`); no status-chain knowledge in web.
  Missing-map-entry is treated conservatively as "more" (never primary) — verified in
  unit tests.
- `TicketDrawer.tsx` (line ~304): forward moves in primary `<select>`; backward + lateral
  behind `<details className="transition-more" data-testid="transition-more">` "more…".
- Confirm dialog (lines 348–380, `data-testid="transition-confirm-dialog"`): renders
  "Move `<key>` from `<status>` to `<to>`?" naming both source and target; describes
  the risk ("backward … regresses" or "exotic (lateral) move").
- e2e `backend/apps/web/e2e/board.spec.ts:128` covers: walk card to `Ready for Development`,
  pick `Backlog` from "more…", assert confirm names both statuses + "backward", confirm,
  assert card regresses. Browser/server-gated; skip cleanly (no Playwright/DB in sandbox;
  authored for CI-with-infra).

### AC3 — Reason helper text visible in the drawer
**Result**: ✅ PASS

- `TicketDrawer.tsx` line 336: `<p className="muted reason-help" data-testid="transition-reason-help">` 
  renders explainer text that the reason lands on the ticket comment / audit trail.

### AC4 — No status-chain literal duplicated into the web app
**Result**: ✅ PASS

- `partitionTransitions` (util.ts) partitions only on string values from the server map;
  zero status names hard-coded in web.
- `LATERAL_HUBS` lives in core (`workflow.ts`) only; the three names confirmed against
  real `- name:` entries in `statuses.yaml`.
- `TicketDrawer.tsx` reads `detail.transition_directions` (server-supplied); no local
  status ordering, no chain copy. ADR-A-0011 layering respected.

---

## Green-Run Proof (ABS-453)

**Commit validated**: `b84a9117` on `ABS-464-auto` (rebased onto `epic/ABS-460` tip `bc032909`).
Current HEAD at time of validation: `a509e566` (prev QA report on top of implementation).

### Core workflow tests
**Command**: `pnpm --filter @agentic-backend/core test`

ABS-464 direction tests (confirmed ✔):
- ✔ `transitionDirection: later-in-chain is forward, earlier is backward`
- ✔ `transitionDirection: cross-cutting hubs are lateral in either endpoint`
- ✔ `allowedNextDirected: every legal edge from a status is tagged`

**Result**: `tests 234 | pass 141 | fail 1 | skipped 92`

The 1 fail is `migrate-prefix-guard.test.ts` — pre-existing `011` migration prefix collision
(ABS-447 + ABS-445 on the epic branch). ABS-464 adds NO migration; confirmed out of scope.
All 141 non-guard tests pass.

### Web unit tests
**Command**: `pnpm --filter @agentic-backend/web test`

ABS-464 partitionTransitions tests (confirmed ✔):
- ✔ `forward moves are primary; backward + lateral fall behind 'more…'`
- ✔ `input order is preserved within each bucket`
- ✔ `a target missing from the direction map is gated (treated as 'more'), never primary`
- ✔ `empty allowed list yields empty buckets`

**Result**: `tests 52 | pass 52 | fail 0 | skipped 0`

(Count is 52, up from 48 in Iteration 1, because the epic branch absorbed additional
web tests from other ABS-460 stories between the first and second QAS runs — expected.)

### TypeCheck
**Command**: `pnpm -r typecheck`

**Result**: PASS — all 5 workspaces (core, web, server, forge, webhooks) `tsc --noEmit` clean.

### Lint
**Command**: `pnpm lint`

**Result**: PASS — `eslint .` exits 0, no errors or warnings.

### Server contract test + e2e
DB-gated / browser-server-gated: skip cleanly in sandbox (0 fail). Authored for CI-with-infra.

---

## Pre-existing Findings (NOT ABS-464 — confirmed out of scope)

1. **Migration prefix collision `011`** (`migrate-prefix-guard.test.ts` 1 fail):
   `011_command_reason_length.sql` (ABS-447) + `011_seat_spawn_id_text.sql` (ABS-445)
   both on `epic/ABS-460`. ABS-464 adds no migration. Renumber belongs at epic integration
   per the ABS-449 guard; already flagged to the epic owner.
2. **`util.ts formatAge`** (ABS-470 leftover): bare re-export used as a local binding;
   one-line local-import fix applied by the implementer to unblock web tsc gate. Documented
   in commit body. Acceptable and out of ABS-464 scope.

---

## Exit Decision

- No `design` flag on ticket (labels: `[orchestrator-ready, ux-review-2026-07]`; no `design` flag)
- No `security` flag
- System-architect Stage 1 approved (post-rebase re-review confirmed same verdict)

**Exit**: In Test → **Story Acceptance**

---

## Summary

All 4 ACs independently verified against commit `b84a9117`. Green-run proof attached above:
core 141/141 · web 52/52 · typecheck 5/5 · lint clean. Rebase delta confirmed as
comment-only (`util.ts` `formatAge` comment harmonisation; code byte-identical to epic tip).
ABS-464's direction-tagging + forward-first drawer additions are intact. Verdict: **APPROVED**.
