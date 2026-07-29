# QA Validation Report — ABS-466

**Ticket:** ABS-466 — Responsive parity II — board, timeline, tables reflow + column visibility
**Branch:** `ABS-466-auto` (off epic/ABS-460 integration branch)
**Commits:** `3ccc393c` (util.ts unblock), `df18975c` (responsive parity II)
**QAS run date:** 2026-07-19
**Verdict:** ✅ APPROVED

---

## Gate Results Summary

| Check | Result |
|---|---|
| `pnpm typecheck` | ✅ PASS (exit 0) |
| `pnpm test` (unit) | ✅ PASS (44/44 passed) |
| `pnpm test:e2e board-responsive.spec.ts mobile.spec.ts` | ✅ PASS (9/9 passed) |
| `pnpm test:e2e` (full suite) | ✅ PASS (78 passed, 1 skipped — pre-existing skip in knowledge.spec.ts) |

---

## ABS-453 Green-Run Proof (changed test files)

**Command:** `DATABASE_URL="postgres://postgres:postgres@localhost:5432/agentic" pnpm test:e2e board-responsive.spec.ts mobile.spec.ts`

**Commit hash:** `df18975c6cfe5fea11fdc53bea443edadde24a41`

**Result:**
```
Running 9 tests using 1 worker
  ✓ [desktop] › e2e/board-responsive.spec.ts:48 › AC2: a Backlog-status epic renders in the Epic Pipeline column, not Backlog (211ms)
  ✓ [desktop] › e2e/board-responsive.spec.ts:67 › AC1: the right-edge more-columns affordance is visible at 1280px (178ms)
  ✓ [desktop] › e2e/board-responsive.spec.ts:73 › AC4: no page-level horizontal scrollbar at 1280px and 768px (390ms)
  ✓ [mobile] › e2e/mobile.spec.ts:69 › AC1: all nav entries are reachable through the burger menu (864ms)
  ✓ [mobile] › e2e/mobile.spec.ts:96 › AC2: opening Live Spawns does not shift the content below (783ms)
  ✓ [mobile] › e2e/mobile.spec.ts:115 › AC3: ticker is a hidden drawer that opens to a full-width panel (825ms)
  ✓ [mobile] › e2e/mobile.spec.ts:137 › smoke: the shell has no horizontal overflow at 375px (750ms)
  ✓ [mobile] › e2e/mobile.spec.ts:148 › AC3: board columns stack full-width and every column is reachable at 375px (1.0s)
  ✓ [mobile] › e2e/mobile.spec.ts:177 › AC4: the board view has no page-level horizontal scrollbar at 375px (823ms)
9 passed (8.2s)
```

---

## Acceptance Criteria Verification

### AC1 — At 1280px, board "more columns" visually signalled (peek/fade) — e2e screenshot assertion
**Verdict: PASS**
- Implementation: `.board-edge-fade` (`data-testid="board-more"`) pinned to the right edge of the `.board` shell with a `linear-gradient(to right, transparent, var(--bg))` fade.
- e2e: `board-responsive.spec.ts` asserts `page.getByTestId("board-more")` is visible at 1280px desktop viewport. ✅

### AC2 — Seeded Backlog-status epic appears in Epic Pipeline, not Backlog — e2e
**Verdict: PASS**
- Implementation: `isEpicColumn = col.group === "Epic Pipeline"` routes all `type === "epic"` items to Epic Pipeline; all other columns exclude epics via `.filter((t) => t.type !== "epic")`. Constant `EPIC_COLUMN_GROUP = "Epic Pipeline"` matches `board.ts:82`.
- e2e: Seeds one story + one epic; asserts `card-{project}-2` present in `[data-group="Epic Pipeline"]` and absent from `[data-group="Backlog"]`. ✅

### AC3 — At 375px every board column reachable, cards full-width readable — e2e
**Verdict: PASS**
- Implementation: `@media (max-width: 767px)` stacks `.main` vertically (`flex-direction: column`), sets `.board-track` to `flex-direction: column; overflow-x: visible`, and forces `.column` to `width: 100%; min-width: 0`.
- e2e: `mobile.spec.ts` navigates to board via burger nav, asserts column count > 1, scrolls each column into view, asserts `box.width > 300`. ✅

### AC4 — No page-level horizontal scrollbar at 375/768/1280 widths — e2e
**Verdict: PASS**
- Implementation: Board scroll is internal to `.board-track` (`overflow-x: auto`); stacked layout removes h-scroll under md. Timeline and Usage use internal overflow containers.
- e2e: `board-responsive.spec.ts` checks `scrollWidth - clientWidth <= 1` at 1280px and 768px; `mobile.spec.ts` checks same at 375px. ✅

---

## In-Scope Extras Verified

- **Timeline sticky-left column:** `.tl-lane-label` now has `position: sticky; left: 0; z-index: 1; background: var(--bg)` — pins role/ticket column while lanes scroll horizontally.
- **Usage table `tabular-nums`:** `font-variant-numeric: tabular-nums` applied to `.usage-table` — cost/token columns align digit-for-digit.
- **Usage column priority under md:** `col-secondary` on `Tokens in`/`Tokens out` cells drops those columns under 767px, keeping Key/Spawns/Cost/Budget readable.

---

## Out-of-Scope Unblock (3ccc393c)

Pre-existing TS2552 in `util.ts` (ABS-470 made `formatAge` a pure re-export while `humanizeTimestamp` still called it locally). The one-line fix (import + re-export) was minimal, necessary to unblock typecheck/build for the epic branch, and transparently flagged by the implementer. Accepted by architecture review. QAS concurs — not a scope violation.

---

## Design Token Compliance

Unit test `AC4: no hardcoded hex color outside the theme.css token file` — **44/44 passed**. All new CSS uses `var(--bg/--border/--panel/--accent)` only.

---

## Flags Check

Ticket labels: `orchestrator-ready`, `ux-review-2026-07` — **no `design` flag**. Exit target: `Story Acceptance`.

---

## Iteration Count

This is the **first and only** QAS review pass. No prior bounce comments on this ticket.
