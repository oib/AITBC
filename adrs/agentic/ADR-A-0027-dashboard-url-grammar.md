---
id: ADR-A-0027
title: Dashboard URL grammar v2 — view routes + drawer params (supersedes the ABS-420 hash contract)
status: accepted
accepted_by: Raphael Sahann (POPM)
accepted_date: "2026-07-20"
scope: agentic
date: "2026-07-20"
---

# ADR-A-0027: Dashboard URL grammar v2 — view routes + drawer params (supersedes the ABS-420 hash contract)

- **Status:** accepted (ratified 2026-07-20 by the human merge of epic MR !142 to main per
  ADR-A-0004; authored operator-signed under the ABS-460 epic decisions)
- **Date:** 2026-07-20
- **Origin:** ABS-473 (deep links), #PATH_DECISION required before build; blocker triage
  2026-07-20 01:27Z (tdm) — story blocked on this ADR's absence
- **Relates to:** ABS-420 (drawer hash, superseded), ABS-469 (/report redirect), ABS-479
  (notification deep links)

## Context

ABS-420 gave the web dashboard its first URL contract: the drawer owns the entire location
hash (`#/ticket/<key>`, `#/seat/<id>`), written with `history.replaceState` so drawer
open/close never creates history entries. `parseHash` ignores slash-less fragments.

ABS-473 requires routable views (`#/board`, `#/usage`, …), URL-serialized global filter
state, and "browser back closes the drawer". These requirements are unsatisfiable inside
the ABS-420 grammar: the drawer monopolizes the hash, and `replaceState` makes
back-navigation a no-op by design. Two hash owners (view router + drawer) would collide.

## Decision

One URL grammar, one owner (a single router module evolving out of `useDrawerURL.ts`):

1. **View path in the hash path segment:** `#/<view>` with
   `view ∈ {home, board, usage, adrs, policies, timeline}`. Unknown or empty view falls
   back to `home`. `#/report` stays parseable and redirects to `#/usage` (ABS-469).
2. **Drawer target in a hash query param:** `#/<view>?item=<kind>:<id>` where
   `kind ∈ {ticket, seat}` (e.g. `#/board?item=ticket:ABS-473`, `#/usage?item=seat:spawn-1`).
   A single `item` param carries the drawer and composes onto any view; absent means no
   drawer. Global filter state (`epic`, `run`, `role`, `timeRange`) stays in the top-level
   **search params** owned by `useFilterState` (design §2/§9) — not the hash query — so
   existing filter deep-links and their e2e keep working; the router seam leaves that
   layer untouched.
3. **History semantics:**
   - Opening a drawer **pushes** a history entry (`pushState`) — browser back closes the
     drawer, a second back leaves the view. This intentionally reverses the ABS-420
     `replaceState` choice for drawer *open*.
   - Filter changes and drawer *close* use `replaceState` (no history spam).
4. **Migration/compat:** old links `#/ticket/<key>` and `#/seat/<id>` are recognized by a
   shim and open the drawer on cold load with the view defaulting to `home` (a legacy link
   does not encode the intended view). They are rewritten to the new grammar
   (`#/<view>?item=<kind>:<id>`) on the first navigation — not at mount — so a pasted legacy
   link round-trips until the user acts. The ABS-420 tests are updated to the new grammar
   (round-trip semantics preserved: open/close cleanup, no hash leftovers); they are not
   kept byte-identical.

## Consequences

- `useDrawerURL.ts` becomes the single router seam; no component reads/writes
  `location.hash` directly.
- Deep links become stable operational artifacts (runbooks, alerts, ABS-479 notification
  clicks) — a pasted link restores view + filters + drawer.
- The drawer-open history entry is a deliberate UX change: back-button behavior now
  matches user expectation on mobile (persona finding), at the cost of one extra history
  entry per drawer open.
- ABS-420's contract is formally superseded; its AC semantics (cleanup, round-trip)
  survive as tests against the new grammar.
- Prose reconciled to the shipped grammar during ABS-473 Stage-1 review (2026-07-20,
  system-architect): the drawer is a single `item=<kind>:<id>` param, global filters remain
  in the search params (design §9), and legacy links default to the `home` view — matching
  the design doc and the merged implementation. Human ratification occurred at the epic merge
  of MR !142 to `main` on 2026-07-20 (ADR-A-0004); the frontmatter `status:` is accordingly
  `accepted` — this paragraph is reconciled to that state (PILOT-52/ABS-561), resolving the
  prior `proposed`-vs-`accepted` self-contradiction.
