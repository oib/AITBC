# ABS-119 Design Spec — depends_on Release at Docs Entry + Epic-Branch Worktree Basing

**Ticket**: ABS-119 (epic ABS-114) · **Status**: accepted (architect review 2026-07-07:
CHANGES REQUESTED → `#PATH_DECISION` escalated to the operator, who **revised the release point
from Merging entry to DOCS entry** (HITL decision 2026-07-07); findings F1–F7 resolved by that
choice or incorporated below) · **Date**: 2026-07-07

## 0. Goal

Epic-internal dependent stories start when their dependency is MERGED onto the epic integration
branch (enters `Docs`) instead of waiting for `Done`. The tech-writer Docs seat and the Done
transition still run in parallel with the dependent's implementation — one seat duration saved
per chain link. Scope: SAME-EPIC dependencies only; cross-epic and parentless dependencies keep
waiting for `Done`/main.

`#PATH_DECISION` — release point (operator-decided 2026-07-07, revising the refinement):
- **Chosen: Docs entry** (`entered_when: Story merged`, statuses.yaml). The RTE has rebased,
  CI-greened and merged the story onto `epic/<parent>-*`; a worktree based on that tip is
  GUARANTEED to contain the accepted code, and the epic branch is guaranteed to exist.
- **Rejected: Merging entry** (the original refinement). At Merging ENTRY the RTE seat has only
  just spawned — the merge has not happened; the dependent would base on a tip WITHOUT the
  accepted code (for the epic's first story the branch may not exist at all), and a dependency
  that never completes its merge (Merging → bounce) would let the dependent integrate without
  its prerequisite. Correctness beats the marginal extra parallelism of the RTE-merge window.
- **Rejected: basing waits for the merge** — blocks `ensure_worktree` (worktree lock, dispatch
  slot) on a minutes-long external step; the state machine delivers the merged signal for free
  as the Docs transition.

Consequences: the entire pause-on-Merging-bounce machinery from the original draft is YAGNI and
DROPPED — a dep released at Docs is merged and frozen; `Docs.next = {Done, Blocked, Needs PO
Decision}` has no backward edge into implementation, so post-release bounces of the dep cannot
happen. A later `Docs → Blocked` (tech-writer blocked) is genuinely neutral (the code already
sits on the epic branch). The only reopen of a Docs/Done story is the Epic-Integration bisect
(`Done → Ready for Development`, ABS-90) — a different phase (JOIN fired, ALL stories incl.
dependents already Done), explicitly out of scope. This also closes architect F1 (the
Blocked-after-acceptance snapshot gap) without any history parsing.

## 1. Release rule (depends_unmet)

For each entry in `depends_on`:
- **Epic-internal** (dep's `parent` equals the ticket's `parent`, both non-empty): satisfied when
  the dep's status is `Docs` or `Done` (canonical state machine only — no comment parsing).
- **Everything else** (different/no parent, unreadable parent or dep): `Done` only — unchanged,
  including the unreadable-dep = WAIT discipline (ABS-111 hotfix).

## 2. Worktree basing on the epic integration branch

When `ensure_worktree` creates a BRAND-NEW `<ticket>-auto` branch (no existing work branch — the
existing-branch preference stays first), it resolves the ticket's `parent` through the adapter
(one `get` per fresh worktree — cost noted) and prefers the epic integration branch tip as the
base. Multiple `epic/<parent>-*` matches are resolved deterministically (lexicographically first)
with a `log` warning — canonically one epic branch per epic exists (created by the RTE on the
first Merging→Docs). Fallback = current HEAD exactly as today (non-epic tickets, no epic branch).

## 3. Test plan (architect F7, adapted to Docs release)

- dep in `Merging` → dependent still waits (DEPENDS-WAIT); dep enters `Docs` → dependent
  dispatches AND its provisioned worktree contains the file that exists only on the epic branch
  (the release/basing coupling in one test)
- dep in `Docs` → `Blocked` (tech-writer blocked) → dependent keeps running (no silent revert)
- cross-epic dep in `Docs` → dependent still waits for Done (regression); parentless likewise
- multi-dep: one dep Docs, one In Test → still waits
- multiple `epic/<parent>-*` branches → deterministic pick + warning
- no epic branch → fallback to HEAD (regression for non-epic tickets)
